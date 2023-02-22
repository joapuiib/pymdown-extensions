"""Admonitions."""
import xml.etree.ElementTree as etree
from .block import Block, type_html_identifier
from .. blocks import BlocksExtension
import re

RE_SEP = re.compile(r'[_-]+')
RE_VALID_NAME = re.compile(r'[\w-]+')


class Admonition(Block):
    """
    Admonition.

    Arguments (1 optional):
    - A title.

    Options:
    - `type` (string): Attach a single special class for styling purposes. If more are needed,
      use the built-in `attributes` options to apply as many classes as desired.

    Content:
    Detail body.
    """

    NAME = 'admonition'
    ARGUMENT = None
    OPTIONS = {
        'type': ['', type_html_identifier],
    }

    def on_parse(self):
        """Handle on parse event."""

        if self.NAME != 'admonition':
            self.options['type'] = self.NAME
        return True

    def on_create(self, parent):
        """Create the element."""

        # Set classes
        classes = ['admonition']
        atype = self.options['type']
        if atype and atype != 'admonition':
            classes.append(atype)

        # Create the admonition
        el = etree.SubElement(parent, 'div', {'class': ' '.join(classes)})

        # Create the title
        if not self.argument:
            if not atype:
                title = None
            else:
                title = atype.capitalize()
        else:
            title = self.argument

        if title is not None:
            ad_title = etree.SubElement(el, 'p', {'class': 'admonition-title'})
            ad_title.text = title

        return el


class AdmonitionExtension(BlocksExtension):
    """Admonition Blocks Extension."""

    def __init__(self, *args, **kwargs):
        """Initialize."""

        self.config = {
            "types": [
                ['note', 'attention', 'caution', 'danger', 'error', 'tip', 'hint', 'warning'],
                "Generate Admonition block extensions for the given types."
            ]
        }

        super().__init__(*args, **kwargs)

    def extendMarkdownBlocks(self, md, block_mgr):
        """Extend Markdown blocks."""

        block_mgr.register(Admonition, self.getConfigs())

        # Generate an admonition subclass based on the given names.
        for b in self.getConfig('types', []):
            subclass = RE_SEP.sub('', b.title())
            block_mgr.register(type(subclass, (Admonition,), {'OPTIONS': {}, 'NAME': b, 'CONFIG': {}}), {})


def makeExtension(*args, **kwargs):
    """Return extension."""

    return AdmonitionExtension(*args, **kwargs)