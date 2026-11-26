"""POSIX glob matching shared by context planning and checkout enumeration."""

from __future__ import annotations

import re


def glob_regex(pattern: str) -> str:
    """Translate *, ?, ** and character classes without crossing segments for *."""
    out: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index : index + 2] == "**":
                index += 1
                if pattern[index + 1 : index + 2] == "/":
                    out.append("(?:.*/)?")
                    index += 1
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = pattern.find("]", index + 2 if pattern[index + 1 : index + 2] == "!" else index + 1)
            if end == -1:
                out.append(r"\[")
            else:
                group = pattern[index + 1 : end]
                negate = group.startswith("!")
                group = group.removeprefix("!").replace("\\", r"\\").replace("^", r"\^")
                out.append("(?!/)[" + ("^" if negate else "") + group + "]")
                index = end
        else:
            out.append(re.escape(char))
        index += 1
    return "".join(out) + "$"


def path_matches(path: str, pattern: str) -> bool:
    """A pattern without / applies to the basename at any depth."""
    candidate = path.rsplit("/", 1)[-1] if "/" not in pattern else path
    try:
        return re.fullmatch(glob_regex(pattern), candidate) is not None
    except re.error:
        return False
