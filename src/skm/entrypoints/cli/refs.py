"""CLI reference grammar (cli §5.1) and scope selectors (cli §5.3); parsing only, lookups belong to commands.

``parse_ref(kind, text)`` accepts the documented spellings of one object kind and says which form it saw; a
text that matches none is ``INVALID_REFERENCE`` (exit 1) with the expected forms. Resolving a slug, alias or
prefix to an id is a bus query of the owning group; there is no "first match" heuristic here.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind

__all__ = [
    "PLAN_PREFIX_MIN",
    "PREFIX_MIN",
    "RUN_PREFIX_MIN",
    "CliRef",
    "RefForm",
    "RefKind",
    "ScopeSelector",
    "as_uuid",
    "default_scope_kind",
    "parse_ref",
    "parse_scope",
]

PLAN_PREFIX_MIN: Final = 12
RUN_PREFIX_MIN: Final = 12  # cli §1.1 resolve_run and the §5.1 table (not example 09's 8 hex)
PREFIX_MIN: Final = 8

_HEX = r"[0-9a-fA-F]"
_SLUG = r"[a-z0-9][a-z0-9-]*"
_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"
_KEY = r"[A-Z]\d+(?:\.\d+)*(?:/[A-Z]\d+)?"
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class RefKind(StrEnum):
    WORKSPACE = "workspace"
    PROJECT = "project"
    PLAN = "plan"
    REVISION = "revision"
    DRAFT = "draft"
    ENTITY = "entity"
    RUN = "run"
    TASK = "task"
    ATTEMPT = "attempt"
    STEP = "step"
    REQUEST = "request"
    FILE = "file"
    FILE_VERSION = "file_version"
    HOST = "host"
    TOKEN = "token"


class RefForm(StrEnum):
    UUID = "uuid"  # "<prefix>:<uuid>"
    SLUG = "slug"  # workspace/project slug, host or token name
    QUALIFIED_SLUG = "qualified_slug"  # "<workspace>/<project>"
    ALIAS = "alias"  # PLAN<n>
    NUMBER = "number"  # revision "3" | "r3"
    DISPLAY_KEY = "display_key"  # P2.4/U1, D3, V1@P2.4
    PREFIX = "prefix"  # hex prefix of a uuid
    LAST = "last"  # "last"
    CURRENT = "current"  # absent -> the context's current / single open object


@dataclass(frozen=True, slots=True)
class CliRef:
    kind: RefKind
    form: RefForm
    text: str
    uuid: UUID | None = None
    number: int | None = None
    qualifier: str | None = None  # workspace slug of "<ws>/<slug>"


# kind -> (explicit prefix, accepted forms as human text)
_PREFIX: Final[dict[RefKind, str]] = {
    RefKind.WORKSPACE: "workspace",
    RefKind.PROJECT: "project",
    RefKind.PLAN: "plan",
    RefKind.REVISION: "revision",
    RefKind.DRAFT: "draft",
    RefKind.ENTITY: "entity",
    RefKind.RUN: "run",
    RefKind.TASK: "task",
    RefKind.ATTEMPT: "attempt",
    RefKind.STEP: "step",
    RefKind.REQUEST: "req",
    RefKind.FILE: "file",
    RefKind.FILE_VERSION: "fv",
    RefKind.HOST: "host",
    RefKind.TOKEN: "token",
}
_EXPECTED: Final[dict[RefKind, str]] = {
    RefKind.WORKSPACE: "a slug or workspace:<uuid>",
    RefKind.PROJECT: "a slug, <workspace>/<slug> or project:<uuid>",
    RefKind.PLAN: f"PLAN<n>, plan:<uuid> or a uuid prefix of ≥ {PLAN_PREFIX_MIN} hex",
    RefKind.REVISION: "N, rN or revision:<uuid>",
    RefKind.DRAFT: "draft:<uuid>",
    RefKind.ENTITY: "a display key (P2, P2.4, P2.4/U1, D3, V1@P2.4) or entity:<uuid>",
    RefKind.RUN: f"run:<uuid>, a uuid prefix of ≥ {RUN_PREFIX_MIN} hex or last",
    RefKind.TASK: "task:<uuid> or a display key such as P2.4/U1",
    RefKind.ATTEMPT: f"attempt:<uuid> or a uuid prefix of ≥ {PREFIX_MIN} hex",
    RefKind.STEP: f"step:<uuid> or a uuid prefix of ≥ {PREFIX_MIN} hex",
    RefKind.REQUEST: f"req:<uuid> or a uuid prefix of ≥ {PREFIX_MIN} hex",
    RefKind.FILE: f"file:<uuid> or a uuid prefix of ≥ {PREFIX_MIN} hex",
    RefKind.FILE_VERSION: f"fv:<uuid> or a uuid prefix of ≥ {PREFIX_MIN} hex",
    RefKind.HOST: "a name or host:<uuid>",
    RefKind.TOKEN: "a token name or token:<uuid>",
}
_ALIAS: Final = re.compile(r"PLAN([1-9]\d*)")
_REVISION_NUMBER: Final = re.compile(r"r?([1-9]\d*)")
_DISPLAY_KEY: Final = re.compile(rf"{_KEY}(?:@{_KEY})?")
_PREFIX_TEXT: Final = re.compile(rf"{_HEX}[0-9a-fA-F-]*")


def _invalid(kind: RefKind, text: str) -> ValidationFailed:
    label = kind.value.replace("_", " ")
    shown = text.replace('"', "'")
    return ValidationFailed(
        ErrorCode.INVALID_REFERENCE,
        f'"{shown}" is not a {label} reference (expected {_EXPECTED[kind]})',
        details={"kind": kind.value, "ref": text, "expected": _EXPECTED[kind]},
    )


def as_uuid(text: str) -> UUID | None:
    """``text`` as a full canonical UUID, else ``None`` (a scope selector may name its object by id)."""
    return UUID(text) if _UUID.fullmatch(text) else None


def _hex_digits(text: str) -> str:
    return text.replace("-", "")


def _uuid_after(prefix: str, text: str) -> UUID | None:
    head, separator, tail = text.partition(":")
    if separator and head == prefix and _UUID.fullmatch(tail):
        return UUID(tail)
    return None


def _name_forms(kind: RefKind, text: str) -> CliRef | None:
    slug = _NAME if kind in {RefKind.HOST, RefKind.TOKEN} else _SLUG
    if re.fullmatch(slug, text):
        return CliRef(kind, RefForm.SLUG, text)
    return None


def _prefix_form(kind: RefKind, text: str, minimum: int) -> CliRef | None:
    if _PREFIX_TEXT.fullmatch(text) and len(_hex_digits(text)) >= minimum and len(_hex_digits(text)) <= 32:
        return CliRef(kind, RefForm.PREFIX, text.lower())
    return None


def _project(kind: RefKind, text: str) -> CliRef | None:
    workspace, slash, slug = text.partition("/")
    if not slash:
        return _name_forms(kind, text)
    if re.fullmatch(_SLUG, workspace) and re.fullmatch(_SLUG, slug):
        return CliRef(kind, RefForm.QUALIFIED_SLUG, text, qualifier=workspace)
    return None


def _plan(kind: RefKind, text: str) -> CliRef | None:
    alias = _ALIAS.fullmatch(text)
    if alias is not None:
        return CliRef(kind, RefForm.ALIAS, text, number=int(alias.group(1)))
    return _prefix_form(kind, text, PLAN_PREFIX_MIN)


def _revision(kind: RefKind, text: str) -> CliRef | None:
    number = _REVISION_NUMBER.fullmatch(text)
    return None if number is None else CliRef(kind, RefForm.NUMBER, text, number=int(number.group(1)))


def _run(kind: RefKind, text: str) -> CliRef | None:
    return CliRef(kind, RefForm.LAST, text) if text == "last" else _prefix_form(kind, text, RUN_PREFIX_MIN)


def _display_key(kind: RefKind, text: str) -> CliRef | None:
    return CliRef(kind, RefForm.DISPLAY_KEY, text) if _DISPLAY_KEY.fullmatch(text) else None


def _short_prefix(kind: RefKind, text: str) -> CliRef | None:
    return _prefix_form(kind, text, PREFIX_MIN)


def _only_explicit(kind: RefKind, text: str) -> CliRef | None:  # noqa: ARG001 - sibling parser shape
    return None


_PARSERS: Final[dict[RefKind, Callable[[RefKind, str], CliRef | None]]] = {
    RefKind.WORKSPACE: _name_forms,
    RefKind.PROJECT: _project,
    RefKind.PLAN: _plan,
    RefKind.REVISION: _revision,
    RefKind.DRAFT: _only_explicit,
    RefKind.ENTITY: _display_key,
    RefKind.RUN: _run,
    RefKind.TASK: _display_key,
    RefKind.ATTEMPT: _short_prefix,
    RefKind.STEP: _short_prefix,
    RefKind.REQUEST: _short_prefix,
    RefKind.FILE: _short_prefix,
    RefKind.FILE_VERSION: _short_prefix,
    RefKind.HOST: _name_forms,
    RefKind.TOKEN: _name_forms,
}


def parse_ref(kind: RefKind, text: str | None) -> CliRef:
    """Parse ``text`` as a ``kind`` reference; ``None`` is the "current/only" form some kinds allow."""
    if text is None:
        return CliRef(kind, RefForm.CURRENT, "")
    explicit = _uuid_after(_PREFIX[kind], text)
    if explicit is not None:
        return CliRef(kind, RefForm.UUID, text, uuid=explicit)
    found = _PARSERS[kind](kind, text)
    if found is None:
        raise _invalid(kind, text)
    return found


@dataclass(frozen=True, slots=True)
class ScopeSelector:
    """``--scope`` text: the level and, when given, the reference text of its object (not yet resolved)."""

    kind: ScopeKind
    ref: str | None = None

    def to_json(self) -> JsonObject:
        return {"kind": self.kind.value, "ref": self.ref}


_NEEDS_REF: Final = frozenset({ScopeKind.PLAN, ScopeKind.RUN})


def parse_scope(text: str) -> ScopeSelector:
    """``instance | workspace[:ref] | project[:ref] | plan:ref | run:ref | host[:ref]`` (cli §5.3)."""
    level, separator, ref = text.partition(":")
    try:
        kind = ScopeKind(level)
    except ValueError:
        kind = None
    problem = None
    if kind is None:
        problem = "unknown scope level"
    elif kind is ScopeKind.INSTANCE and separator:
        problem = "instance takes no reference"
    elif separator and not ref:
        problem = "empty reference"
    elif kind in _NEEDS_REF and not separator:
        problem = f"{level} needs a reference"
    if problem is not None or kind is None:
        raise ValidationFailed(
            ErrorCode.INVALID_REFERENCE,
            f'"{text}" is not a scope ({problem}; expected instance, workspace[:ref], project[:ref], '
            "plan:ref, run:ref or host[:ref])",
            details={"kind": "scope", "ref": text, "reason": problem or "unknown scope level"},
        )
    return ScopeSelector(kind, ref if separator else None)


def default_scope_kind(*, project: bool, workspace: bool) -> ScopeKind:
    """No ``--scope``: the context's project, else its workspace, else the instance (cli §5.3)."""
    if project:
        return ScopeKind.PROJECT
    return ScopeKind.WORKSPACE if workspace else ScopeKind.INSTANCE
