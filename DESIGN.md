# Design notes: snippet filters and overridable snippet steps

Working notes for future sessions. Branch: `snippets-overridable-steps`.
Not meant to be part of an upstream PR (drop this file before opening one).

## Goal

Transform snippet content at include time, e.g. turn an abbreviations file into a
glossary list:

```markdown
--8<-- "includes/abbreviations.md | sed s/^\*/* /"
--8<-- "includes/abbreviations.md:abbr | sed /CSS/d | sed s/^\*\[(\w+)\]: /- **\1**: /"
```

## Upstream context

- Issue [#2726](https://github.com/facelessuser/pymdown-extensions/issues/2726)
  ("Expose a post-process hook for snippets"), open.
  - The maintainer (facelessuser) **won't extend the snippet syntax**.
  - Concern with a simple `(lines, path)` hook: not enough context (file type,
    Markdown object, ...).
  - Preferred direction: a **config option taking a function** (like `emoji_generator`
    or `slugify`) receiving path/URL, buffer and the Markdown object. "Needs to be
    planned more."
  - Glossary pages were considered a job for a docs plugin, not a Markdown extension.
- PR [#2727](https://github.com/facelessuser/pymdown-extensions/pull/2727) (by the
  issue author), open and unreviewed: adds `post_process_snippet(self, s_lines, snippet)`
  to override in a subclass. It only receives the lines and the resolved path, so a
  transform would apply to **every** include of a file (e.g. it would break
  `auto_append` abbreviations). No access to the section name or the raw include string.

## Options considered

| Option | Verdict |
|---|---|
| Fork pymdown-extensions to add the syntax | Works, but upstream rejects syntax changes |
| Run real `sed` from the snippet string | **Rejected**: GNU sed can execute commands (`e`, `s///e`) and write files (`w`); with `url_download`, remote content could trigger it |
| `--8<-- "file.md"; args` (args outside the quotes) | **Rejected**: `RE_ALL_SNIPPETS` requires the line to end right after the closing quote, so the line is printed verbatim; `parse_snippets` only reads `group('snippet')`. Workable only with a pre-pass preprocessor, which doesn't see nested includes |
| Pre-generate the file (`sed ... > glossary.md`) | Zero code, needs a build step |
| MkDocs hook (`on_page_markdown`) | Works for pages, not for nested includes |
| **Subclass `SnippetExtension`, filters inside the quotes** | **Chosen** (see below) |

## Implementation in `mkdocs-material-joapuiib`

File: `../mkdocs-material-joapuiib/material_joapuiib/extensions/snippets.py`,
tests in `tests/test_snippets.py`. Committed on branch `feat/snippet-filters`
of that repo (`aa0575c`).

It is built on the extension points of this branch (`parse_snippet_target`,
`process_snippet_lines`), so it **requires an unreleased pymdown-extensions**. On a
release without them it raises a `RuntimeError` naming the missing methods.

Use it instead of `pymdownx.snippets` (same options). Never load both: they register the
same preprocessor name (`snippet`) and the last one wins silently.

```yaml
markdown_extensions:
  - material_joapuiib.extensions.snippets:
      filters:
        upper: !!python/name:my_module.upper
```

### Syntax

- `path[:section] | name args | name args | ...`
- The first `|` after the path always separates. Between filters, a `|` only separates
  when it has whitespace on both sides, so `sed s|a|b|` and `sed /a|b/d` work. Match a
  spaced pipe in a regex with ` [|] `.
- `args` is a raw string; surrounding whitespace is lost (upstream strips the whole
  quoted string).
- Use single quotes around the include to put `"` in the args.
- Filters apply to whole files, sections and line ranges, in nested includes and in
  `-8<-` blocks.
- In whole-file and line-range mode, filters see the `--8<-- [start/end:x]` marker
  lines; upstream removes them afterwards (when nested snippets are parsed).

### Filter API

- `def filter(lines: list[str], args: str) -> list[str]`, registered by name in the
  `filters` option. `sed` is built in and can be overridden.
- Errors (`SnippetFilterError`) stop the build: unknown filter, empty step in a chain,
  invalid sed script, non-callable filter, wrong return type.

### Built-in `sed` (Python, no subprocess)

- `[addr]s/re/repl/[g|i|I|N]`, `[addr]d`; `addr` is `/re/` or `\cREc`, `!` negates.
- Commands separated by `;` or newlines; any `s` delimiter.
- Python `re` syntax, not POSIX BRE (`s/^*/x/` is invalid, write `s/^\*/x/`).
- Replacement: `&` whole match, `\&` literal, `\1`.., `\n` splits the line.

### How it hooks into pymdown-extensions

- `parse_snippet_target(path)`: splits off `| ...`, calls `super()` on the path part and
  stores the parsed chain as `target['filters']`.
- `process_snippet_lines(lines, target)`: applies the chain.

Earlier version (before this branch, against 10.21.3), kept for reference: only
`extract_section()` runs between reading a snippet and parsing nested ones, so it
replaced `RE_SNIPPET_FILE` with a wrapper returning a fake match whose group 3 was an
opaque key, resolved the key in `extract_section()`, and stripped section markers
itself in whole-file mode (upstream then passed `is_section=True`). Line ranges could
not be filtered without copying upstream's slicing logic.

## Upstream refactor (this branch, "option B")

Pure refactor of `SnippetPreprocessor.parse_snippets`, no behavior change. New methods:

| Method | Role |
|---|---|
| `parse_snippet_target(path)` | `file.md:1:5` / `file.md:section` → `{'path', 'start', 'end', 'section'}` or `None`. Subclasses may add keys |
| `extract_lines(start, end, lines)` | Line-range slicing, moved out of the loop (mirrors `extract_section`) |
| `select_snippet_lines(lines, target)` | Dispatches to `extract_lines` / `extract_section` |
| `process_snippet_lines(lines, target)` | No-op hook after selection, before nested parsing. `target` also has `snippet` (resolved path/URL) and `is_url` |

`is_section` is derived from `target['section']`.

Why this shape:

- Gives a hook the **full parsed include**, answering the "not enough context" concern
  in #2726, and stays extensible (dict keys).
- The maintainer's preferred config function could later be called from the default
  `process_snippet_lines(lines, target)` with `self.md`.
- Public methods instead of internals.

The joapuiib extension now uses it, essentially:

```python
def parse_snippet_target(self, path):
    path, sep, spec = path.partition('|')
    target = super().parse_snippet_target(path.strip())
    if target is not None and sep:
        target['filters'] = self.parse_filters(spec, path)
    return target

def process_snippet_lines(self, lines, target):
    for name, args in target.get('filters', ()):
        lines = self.filter_funcs[name](lines, args)
    return lines
```

No regex wrapper, fake keys or marker stripping, and line ranges work too.

Alternative considered ("option A"): only extract `extract_lines()`. Smaller (~10 lines)
but keeps all workarounds and needs extra state to carry filters into `extract_lines`
(group 2 is parsed into ints, so it can't hold a key).

Tests: `TestSnippetsExtensionPoints` in `tests/test_extensions/test_snippets.py`.

## Next steps

1. Propose the design in #2726 before opening a PR (the maintainer wants to plan it).
   Key argument: a hook needs the section/raw include, not only the path, or any
   transform applies to every include of that file.
2. If accepted: add docs (`docs/src/markdown/extensions/snippets.md`) and a changelog
   entry, drop this file, open the PR.
3. Once released: raise the joapuiib `pymdown-extensions` minimum version
   (`material_joapuiib/requirements.txt`). Until then, that branch can't be released
   (or needs a git dependency on a pushed fork branch).
4. joapuiib pending: docs page (`docs/extensions/snippets.md` + card in
   `docs/extensions/index.md`, written with the `apunts:redaccio` skill), optionally
   switch its `properdocs.yml` to the new extension.

## Testing notes

No local venv in this repo. Run with the joapuiib venv, which picks up this repo's
`pymdownx` when run from here:

```bash
../mkdocs-material-joapuiib/.venv/bin/python -m pytest -q tests
../mkdocs-material-joapuiib/.venv/bin/python -m ruff check pymdownx tests
```

Joapuiib tests need this repo's `pymdownx` (the venv has the released one):

```bash
cd ../mkdocs-material-joapuiib
PYTHONPATH=../pymdown-extensions .venv/bin/python -m pytest -q
```
