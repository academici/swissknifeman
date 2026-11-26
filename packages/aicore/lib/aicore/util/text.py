"""Shared text helpers."""
import re

SLUG_RE = re.compile(r"[^a-z0-9-]")


def sanitize(name):
    """Normalize a value into a lowercase hyphenated slug."""
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = SLUG_RE.sub("", name)
    return re.sub(r"-{2,}", "-", name).strip("-")


def parse_frontmatter(text):
    """Parse the first YAML-frontmatter block without external dependencies.

    Scalars, block scalars, inline lists, and indented lists are supported.
    """
    if text.startswith("\ufeff"):  # Strip a BOM received through plain UTF-8.
        text = text[1:]
    lines = text.replace("\r\n", "\n").splitlines()
    fm = {}
    if not lines or lines[0].strip() != "---":
        return fm
    i, cur = 1, None
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            break
        # Continuation of an indented ``- item`` list for the current key.
        if cur is not None and line[:1] in (" ", "\t") and line.strip().startswith("-"):
            if not isinstance(fm.get(cur), list):
                fm[cur] = []  # The first item converts an empty scalar to a list.
            fm[cur].append(line.strip()[1:].strip().strip('"').strip("'"))
            i += 1
            continue
        cur = None
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            # Accept a block scalar only for a complete ``|``/``>`` header.
            if value[:1] in ("|", ">") and all(c in "+-0123456789" for c in value[1:]):
                block, i = _collect_block_scalar(lines, i + 1)
                fm[key] = (" " if value[0] == ">" else "\n").join(block)
                continue
            if value.startswith("[") and value.endswith("]"):
                fm[key] = [x.strip().strip('"').strip("'")
                           for x in value[1:-1].split(",") if x.strip()]
            elif value == "":
                fm[key] = ""  # Becomes a list if an indented item follows.
                cur = key
            else:
                fm[key] = value.strip('"').strip("'")
        i += 1
    return fm


def _collect_block_scalar(lines, start):
    """Collect an indented YAML block scalar and return ``(lines, next_index)``."""
    block = []
    i = start
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "---":
            break
        if ln.strip() == "":
            block.append("")
        elif ln.startswith((" ", "\t")):
            block.append(ln.strip())
        else:
            break
        i += 1
    while block and block[-1] == "":
        block.pop()
    return block, i


def parse_inline_list(value):
    """Normalize a parsed or inline frontmatter list to nonempty strings."""
    if isinstance(value, list):
        return [str(i).strip().strip('"').strip("'")
                for i in value if str(i).strip()]
    value = (value or "").strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    items = [i.strip().strip('"').strip("'") for i in value[1:-1].split(",")]
    return [i for i in items if i]
