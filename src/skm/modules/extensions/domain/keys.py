"""Identifiers and version values of packs and resources (extensions §4.1).

``SemVer`` is strict SemVer 2.0.0 without build metadata and orders by its precedence rules, prerelease
identifiers included. ``VersionConstraint`` has no ``^``/``~``: ``">=1.2.0,<2"``, ``"1.2.3"`` (exact) or
``"latest"`` (no clauses); a partial version in a clause fills the missing parts with zero.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, NewType, override
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

__all__ = [
    "LATEST",
    "PackId",
    "PackSlug",
    "PackVersionId",
    "ResourceId",
    "ResourceKey",
    "SemVer",
    "VersionConstraint",
    "is_digest",
    "parse_pack_slug",
    "parse_resource_key",
]

PackId = NewType("PackId", UUID)
PackVersionId = NewType("PackVersionId", UUID)
ResourceId = NewType("ResourceId", UUID)
type PackSlug = str
type ResourceKey = str

_SLUG: Final = re.compile(r"[a-z0-9][a-z0-9-]{1,62}")
_KEY: Final = re.compile(r"[a-z0-9][a-z0-9-]{1,80}")
_PROMPT_KEY: Final = re.compile(r"[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-_]*")
_DIGEST: Final = re.compile(r"sha256:[0-9a-f]{64}")
# SemVer §9: a numeric prerelease identifier has no leading zero, so one precedence is one spelling
_PRERELEASE_ID: Final = r"(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
_PRERELEASE: Final = rf"{_PRERELEASE_ID}(?:\.{_PRERELEASE_ID})*"
_SEMVER: Final = re.compile(rf"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-({_PRERELEASE}))?")
_CLAUSE: Final = re.compile(rf"(=|>=|<=|>|<)?([0-9]+)(?:\.([0-9]+))?(?:\.([0-9]+))?(?:-({_PRERELEASE}))?")
_COMPARE: Final[Mapping[str, Callable[[int], bool]]] = {
    "=": lambda order: order == 0,
    ">": lambda order: order > 0,
    ">=": lambda order: order >= 0,
    "<": lambda order: order < 0,
    "<=": lambda order: order <= 0,
}


def _invalid(what: str, value: object) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.SCHEMA_INVALID,
        f"invalid {what}",
        details={"reason": f"invalid_{what}", "value": str(value)},
    )


def parse_pack_slug(text: str) -> PackSlug:
    if _SLUG.fullmatch(text) is None:
        raise _invalid("pack_slug", text)
    return text


def parse_resource_key(text: str, *, prompt_block: bool) -> ResourceKey:
    if (_PROMPT_KEY if prompt_block else _KEY).fullmatch(text) is None:
        raise _invalid("resource_key", text)
    return text


def is_digest(text: object) -> bool:
    return isinstance(text, str) and _DIGEST.fullmatch(text) is not None


def _identifier_key(identifier: str) -> tuple[int, int, str]:
    # SemVer §11: numeric identifiers compare numerically and rank below alphanumeric ones
    return (0, int(identifier), "") if identifier.isdigit() else (1, 0, identifier)


@dataclass(frozen=True, slots=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    @classmethod
    def parse(cls, text: str) -> SemVer:
        found = _SEMVER.fullmatch(text)
        if found is None:
            raise _invalid("semver", text)
        return cls(int(found[1]), int(found[2]), int(found[3]), found[4])

    @override
    def __str__(self) -> str:
        suffix = "" if self.prerelease is None else f"-{self.prerelease}"
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"

    def _order(self) -> tuple[int, int, int, int, tuple[tuple[int, int, str], ...]]:
        release = self.prerelease is None  # a release ranks above every prerelease of the same triple
        identifiers = () if self.prerelease is None else self.prerelease.split(".")
        return (
            self.major,
            self.minor,
            self.patch,
            int(release),
            tuple(_identifier_key(identifier) for identifier in identifiers),
        )

    def __lt__(self, other: SemVer) -> bool:
        return self._order() < other._order()

    def __le__(self, other: SemVer) -> bool:
        return self._order() <= other._order()

    def __gt__(self, other: SemVer) -> bool:
        return self._order() > other._order()

    def __ge__(self, other: SemVer) -> bool:
        return self._order() >= other._order()


@dataclass(frozen=True, slots=True)
class VersionConstraint:
    clauses: tuple[tuple[str, SemVer], ...]

    @classmethod
    def parse(cls, text: str) -> VersionConstraint:
        if text == "latest":
            return LATEST
        clauses: list[tuple[str, SemVer]] = []
        for part in text.split(","):
            found = _CLAUSE.fullmatch(part.strip())
            if found is None:
                raise _invalid("version_constraint", text)
            version = SemVer(int(found[2]), int(found[3] or 0), int(found[4] or 0), found[5])
            clauses.append((found[1] or "=", version))
        return cls(tuple(clauses))

    def matches(self, version: SemVer) -> bool:
        for operator, bound in self.clauses:
            order = (version > bound) - (version < bound)
            if not _COMPARE[operator](order):
                return False
        return True

    @override
    def __str__(self) -> str:
        if not self.clauses:
            return "latest"
        return ",".join(f"{operator}{version}" for operator, version in self.clauses)


LATEST: Final = VersionConstraint(())
