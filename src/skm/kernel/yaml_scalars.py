"""Pure parsing helpers for the quoted scalar subset used in Markdown frontmatter."""

import json
import re

_QUOTED_STRING = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')(?:[ \t]+#.*)?""")


def parse_quoted_yaml_string(value: str) -> str | None:
    """Read a quoted string, allowing a trailing YAML comment."""
    match = _QUOTED_STRING.fullmatch(value)
    if match is None:
        return None
    literal = match[1]
    if literal.startswith("'"):
        return literal[1:-1].replace("''", "'")
    try:
        decoded = json.loads(literal)
    except ValueError:
        return None
    return decoded if isinstance(decoded, str) else None
