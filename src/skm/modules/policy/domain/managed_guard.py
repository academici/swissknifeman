"""Pure guards for reserved state and managed projection files (policy §5.9)."""

from __future__ import annotations

import json
import posixpath
import re

from skm.kernel.json_types import JsonValue

_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)


def candidate_paths(tool_input: JsonValue) -> tuple[str, ...]:
    paths: list[str] = []

    def visit(value: JsonValue) -> None:
        if isinstance(value, str):
            if value and "\n" not in value and "\r" not in value and len(value) <= 500:
                paths.append(value)
            paths.extend(_PATCH_PATH.findall(value))
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(tool_input)
    return tuple(dict.fromkeys(paths))


def managed_hit(
    tool_input: JsonValue, cwd: str, managed: frozenset[str], *, protected_dirs: tuple[str, ...]
) -> str | None:
    def absolute(path: str) -> str:
        return posixpath.normpath(posixpath.join(cwd, path))

    files = frozenset(absolute(path) for path in managed)
    directories = tuple(absolute(path).rstrip("/") for path in protected_dirs)
    for candidate in candidate_paths(tool_input):
        path = absolute(candidate)
        if path in files or any(path == root or path.startswith(root + "/") for root in directories):
            return path
    serialized = json.dumps(tool_input, ensure_ascii=False)
    for path in sorted(files):
        relative = posixpath.relpath(path, cwd)
        if re.search(re.escape(relative), serialized) or path in serialized:
            return path
    for root in directories:
        relative = posixpath.relpath(root, cwd)
        if re.search(r"(?<![\w.-])" + re.escape(relative) + r"(?:/|[\"'\s;&|<>]|$)", serialized):
            return root
    return None
