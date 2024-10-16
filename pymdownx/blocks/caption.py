"""
Captions.

Captions should be placed after a block, that block will be wrapped in a `figure`
and captions will be inserted either at the end of the figure or at the beginning.
If the preceding block happens to be a `figure`, if no `figcaption` is detected
within, the caption will be injected into that figure instead of wrapping.
Keep in mind that when `md_in_html` is used and raw HTML is used, if `markdown=1`
is not present on the caption, the caption will be invisible to this extension.

Class, IDs, or other attributes will be attached to the figure, not the caption.

`types`:
    A dictionary with figure type names and prefix templates. A template will be
    used depending on whether the current type is assumed or directly specified.
`prepend`:
    Will prepend `figcaption` at the start of a `figure` instead of the end.
`auto`:
    Will generate IDs and prefixes via the provided template for all figures of
    a given type as long as they also define a prefix template.
`auto_level`:
    Auto number will not be shown below the given level depth. A value of 0, the
    default, disables the feature, 1 would show only auto-generate IDs and
    prefixes for the outermost figures with prefixes, etc. This level is only
    considered for each figure type individually.

"""
import xml.etree.ElementTree as etree
from .block import Block, type_html_identifier
from .. blocks import BlocksExtension
from markdown.treeprocessors import Treeprocessor
import re

RE_FIG_NUM = re.compile(r'^(\^)?([1-9][0-9]*(?:.[1-9][0-9]*)*)(?= |$)')
RE_SEP = re.compile(r'[_-]+')


def update_tag(el, fig_type, fig_num, template, prepend):
    """Update tag ID and caption prefix."""

    # Auto add an ID
    if 'id' not in el.attrib:
        el.attrib['id'] = f'__{fig_type}_' + '_'.join(str(x) for x in fig_num.split('.'))

    # Prefix the caption with a given numbered prefix
    if template:
        for child in list(el) if prepend else reversed(el):
            if child.tag == 'figcaption':
                children = list(child)
                value = template.format(fig_num)
                if not len(children) or children[0].tag != 'p':
                    p = etree.Element('p')
                    span = etree.SubElement(p, 'span', {'class': 'caption-prefix'})
                    span.text = value
                    p.tail = child.text
                    child.text = None
                    child.insert(0, p)
                else:
                    p = children[0]
                    span = etree.Element('span', {'class': 'caption-prefix'})
                    span.text = value
                    span.tail = (' ' + p.text) if p.text is not None else p.text
                    p.text = None
                    p.insert(0, span)


class CaptionTreeprocessor(Treeprocessor):
    """Caption tree processor."""

    def __init__(self, md, types, config):
        """Initialize."""

        super().__init__(md)

        self.auto = config['auto']
        self.prepend = config['prepend']
        self.type = ''
        self.auto_level = max(0, config['auto_level'])
        self.fig_types = types

    def run(self, doc):
        """Update caption IDs and prefixes."""

        parent_map = {c: p for p in doc.iter() for c in p}
        last = {k: 0 for k in self.fig_types}
        counters = {k: [0] for k in self.fig_types}
        fig_type = last_type = self.type
        figs = []
        fig_num = ''

        # Calculate the depth and iteration at that depth of the given figure.
        for el in doc.iter():
            fig_num = ''
            stack = -1
            if el.tag == 'figure':
                fig_type = last_type
                prepend = False
                skip = False

                # Find caption appended or prepended
                if '__figure_prepend' in el.attrib:
                    prepend = True
                    del el.attrib['__figure_prepend']

                # Determine figure type
                if '__figure_type' in el.attrib:
                    fig_type = el.attrib['__figure_type']
                    figs.append(el)
                    # See if we have an unknown type or the type has no prefix template.
                    if fig_type not in self.fig_types or not self.fig_types[fig_type]:
                        continue
                else:
                    # Found a figure that was not generated by this plugin.
                    continue

                # Handle a manual number
                if '__figure_num' in el.attrib:
                    fig_num = [int(x) for x in el.attrib['__figure_num'].split('.')]
                    del el.attrib['__figure_num']
                    el.attrib['__figure_level'] = str(len(fig_num))
                    stack = len(fig_num) - 1

                # Determine depth
                else:
                    # Handle a specified relative nesting depth
                    if '__figure_level' in el.attrib:
                        stack += int(el.attrib['__figure_level']) + 1
                        if self.auto_level and stack >= (self.auto_level - 1):
                            continue
                    else:
                        stack += 1

                    current = el
                    while True:
                        parent = parent_map.get(current, None)

                        # No more parents
                        if parent is None:
                            break

                        # Check if parent element is a figure of the current type
                        if parent.tag == 'figure' and parent.attrib['__figure_type'] == fig_type:
                            # See if position in stack is manually specified
                            level = '__figure_level' in parent.attrib
                            if level:
                                stack += int(parent.attrib['__figure_level']) + 1
                            else:
                                stack += 1
                            if level:
                                el.attrib['__figure_level'] = str(stack + 1)
                            # Ensure position in stack is not deeper than the specified level
                            if self.auto_level and stack >= self.auto_level:
                                skip = True
                                break
                            if level:
                                break

                        current = parent

                    if skip:
                        # Parent has been skipped so all children are also skipped
                        continue

            # Found an appropriate figure at an acceptable depth
            if stack > -1:
                # Increment counter
                l = last[fig_type]
                counter = counters[fig_type]
                if stack > l:
                    counter.extend([1] * (stack - l))
                elif stack == l:
                    counter[stack] += 1
                else:
                    del counter[stack + 1:]
                    counter[-1] += 1
                last[fig_type] = stack
                last_type = fig_type

                # Determine if manual number is not smaller than existing figure numbers at that depth
                if fig_num and all(a <= b for a, b in zip(counter, fig_num)):
                    counter[:] = fig_num[:]

                # Apply prefix and ID
                update_tag(
                    el,
                    fig_type,
                    '.'.join(str(x) for x in counter[:stack + 1]),
                    self.fig_types.get(fig_type, ''),
                    prepend
                )

        # Clean up attributes
        for fig in figs:
            del fig.attrib['__figure_type']
            if '__figure_level' in fig.attrib:
                del fig.attrib['__figure_level']


class Caption(Block):
    """Figure captions."""

    NAME = ''
    PREFIX = ''
    ARGUMENT = None
    OPTIONS = {
        'type': ['', type_html_identifier]
    }

    def on_init(self):
        """Initialize."""

        self.auto = self.config['auto']
        self.prepend = self.config['prepend']
        self.caption = None
        self.fig_num = ''
        self.level = ''

    def on_validate(self, parent):
        """Handle on validate event."""

        argument = self.argument
        if argument:
            if argument.startswith('>'):
                self.prepend = False
                argument = argument[1:].lstrip()
            elif argument.startswith('<'):
                self.prepend = True
                argument = argument[1:].lstrip()

            m = RE_FIG_NUM.match(argument)
            if m:
                if m.group(1):
                    self.level = m.group(2)
                else:
                    self.fig_num = m.group(2)
                argument = argument[m.end():].lstrip()

        if argument:
            return False
        return True

    def on_create(self, parent):
        """Create the element."""

        # Find sibling to add caption to.
        fig = None
        child = None
        children = list(parent)
        if children:
            child = children[-1]
            # Do we have a figure with no caption?
            if child.tag == 'figure':
                fig = child
                for c in list(child):
                    if c.tag == 'figcaption':
                        fig = None
                        break

        # Create a new figure if sibling is not a figure or already has a caption.
        # Add sibling to the new figure.
        if fig is None:
            fig = etree.SubElement(parent, 'figure')
            if child is not None:
                fig.append(child)
                parent.remove(child)

        if self.auto:
            fig.attrib['__figure_type'] = self.NAME
            if self.level:
                fig.attrib['__figure_level'] = self.level
            if self.fig_num:
                fig.attrib['__figure_num'] = self.fig_num

        # Add caption to the target figure.
        if self.prepend:
            if self.auto:
                fig.attrib['__figure_prepend'] = "1"
            self.caption = etree.Element('figcaption')
            fig.insert(0, self.caption)
        else:
            self.caption = etree.SubElement(fig, 'figcaption')

        return fig

    def on_add(self, block):
        """Return caption as the target container for content."""

        return self.caption

    def on_end(self, block):
        """Handle explicit, manual prefixes on block end."""

        prefix = self.PREFIX
        if prefix and not self.auto:
            # Levels should not be used in manual mode, but if they are, give a generic result.
            if self.level:
                self.fig_num = '.'.join(['1'] * int(self.level))
            if self.fig_num:
                update_tag(
                    block,
                    self.NAME,
                    self.fig_num,
                    prefix,
                    self.prepend
                )


class CaptionExtension(BlocksExtension):
    """Caption Extension."""

    def __init__(self, *args, **kwargs):
        """Initialize."""

        self.config = {
            "types": [
                [
                    'caption',
                    {
                        'name': 'figure-caption',
                        'prefix': 'Figure {}.'
                    },
                    {
                        'name': 'table-caption',
                        'prefix': 'Table {}.'
                    }
                ],
                "Configure types a list of types, each type is a dictionary that defines a 'name' and 'prefix' "
                "A template must contain '{}' for numerical insertions unless the template is an empty string "
                "which will assume no prefix should be used."
            ],
            "auto_level": [
                0,
                "Depth of children to add prefixes to - Default: 0"
            ],
            "auto": [
                True,
                "Auto add IDs with prefixes (prefixes are only added if prefix template is defined) - Default: False"
            ],
            "prepend": [
                False,
                "Prepend captions opposed to appending - Default: False"
            ]
        }

        super().__init__(*args, **kwargs)

    def extendMarkdownBlocks(self, md, block_mgr):
        """Extend Markdown blocks."""

        config = self.getConfigs()

        # Generate an details subclass based on the given names.
        types = {}
        for obj in config['types']:
            if isinstance(obj, dict):
                name = obj['name']
                prefix = obj.get('prefix', '')
            else:
                name = obj
                prefix = ''
            types[name] = prefix
            subclass = RE_SEP.sub('', name).title()
            block_mgr.register(
                type(
                    subclass,
                    (Caption,),
                    {
                        'OPTIONS': {},
                        'NAME': name,
                        'PREFIX': prefix
                    }
                ),
                {'auto_level': config['auto_level'], 'auto': config['auto'], 'prepend': config['prepend']}
            )

        if config['auto']:
            md.treeprocessors.register(CaptionTreeprocessor(md, types, config), 'caption-auto', 4)


def makeExtension(*args, **kwargs):
    """Return extension."""

    return CaptionExtension(*args, **kwargs)
