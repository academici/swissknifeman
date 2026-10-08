"""Command-source primitives: strict frontmatter, the description, the fence split, runtime provenance.

What every projection of a canonical command file into a provider runtime shares. The command catalog,
routing and wrapper texts stay with the projecting module; only the parsing of the canonical file and the
generated-file header live here.
"""
from __future__ import annotations

import json
import re


def strict_frontmatter_fields(content: bytes) -> dict[str, str]:
    """Read the ``key: value`` lines between the fences; any malformed or repeated line is an error."""
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("command source is not UTF-8") from error
    if not lines or lines[0] != "---":
        raise ValueError("opening delimiter is missing")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("closing delimiter is missing") from error
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            raise ValueError("frontmatter field is malformed")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if not key or key in fields:
            raise ValueError("frontmatter field is empty or duplicated")
        fields[key] = value
    return fields


def frontmatter_description(content: bytes, *, code: str = "CMD_SOURCE_DRIFT") -> str:
    """The ``description`` line of a command; ``code`` prefixes every error message."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{code}: command source is not UTF-8") from error
    match = re.search(r"^description:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        raise ValueError(f"{code}: command description is missing")
    value = match.group(1)
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError(f"{code}: command description is malformed") from error
        return _required_string(parsed, "description")
    return _required_string(value, "description")


def split_command(content: bytes) -> tuple[str, str]:
    """Split a canonical command into ``(frontmatter_text, body)`` at its two ``---`` fences."""
    text = content.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError("canonical frontmatter opening fence is missing")
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1)
         if line.rstrip("\r\n") == "---"),
        None,
    )
    if closing is None:
        raise ValueError("canonical frontmatter closing fence is missing")
    return "".join(lines[1:closing]), "".join(lines[closing + 1:])


def runtime_provenance(provider_title: str, source_path: str, source_sha256: str,
                       adapter_ref: str) -> str:
    """The header comment of a generated runtime projection of one canonical command."""
    return (
        f"<!-- Generated {provider_title} runtime projection; do not edit as source.\n"
        f"Canonical source: {source_path}\n"
        f"Canonical SHA-256: {source_sha256}\n"
        f"Adapter: {adapter_ref}\n"
        "-->\n"
    )


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value
