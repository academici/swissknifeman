"""Stable schema findings: validation issues and registry load problems (kernel-platform §3.3)."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, override

from skm.kernel.json_types import JsonObject

__all__ = [
    "ELLIPSIS",
    "MESSAGE_LIMIT",
    "VALUE_LIMIT",
    "SchemaIssue",
    "SchemaLoadError",
    "SchemaLoadProblem",
    "json_pointer",
    "truncate",
]

MESSAGE_LIMIT: Final = 300
VALUE_LIMIT: Final = 80
ELLIPSIS: Final = "…"


def truncate(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` characters, marking the cut with an ellipsis."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + ELLIPSIS


def json_pointer(parts: Iterable[object]) -> str:
    """RFC 6901 pointer for ``parts``: ``""`` for the document root, ``/items/0/title`` below it."""
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


@dataclass(frozen=True, slots=True)
class SchemaIssue:
    """One validation finding; ``message`` is bounded to ``MESSAGE_LIMIT`` characters."""

    pointer: str
    schema_pointer: str
    code: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", truncate(self.message, MESSAGE_LIMIT))

    def to_json(self) -> JsonObject:
        return {
            "pointer": self.pointer,
            "schema_pointer": self.schema_pointer,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class SchemaLoadProblem:
    """A defect of one schema file; ``issue.pointer`` points into that file's document."""

    path: str
    issue: SchemaIssue

    def render(self) -> str:
        return f"{self.path}{self.issue.pointer}: [{self.issue.code}] {self.issue.message}"


def _problem_key(problem: SchemaLoadProblem) -> tuple[str, str, str, str]:
    issue = problem.issue
    return (problem.path, issue.pointer, issue.code, issue.message)


class SchemaLoadError(ValueError):
    """Registry load failed; ``problems`` holds every defect found, ordered by file and pointer."""

    problems: tuple[SchemaLoadProblem, ...]

    @override
    def __init__(self, problems: Iterable[SchemaLoadProblem]) -> None:
        ordered = tuple(sorted(problems, key=_problem_key))
        self.problems = ordered
        lines = [f"{len(ordered)} schema problem(s):", *(problem.render() for problem in ordered)]
        super().__init__("\n".join(lines))
