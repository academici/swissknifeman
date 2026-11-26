"""Domain rules of a config write (settings §A.5): R1-R13 and R16, in the normative order.

The rules are pure: they read only ``WriteRequest`` and ``WriteContext``. R14 (section validators on the
candidate config) and R15 (no-op) belong to the handler. Domain code may not import ``platform``
(conventions §2), so the engine types are read structurally: ``KeySpecView`` is satisfied by
``platform.config.keys.KeySpec`` and ``ResolutionView`` by ``platform.config.merge.KeyResolution``; the
operations that need the engine (schema validation, ``deep_merge``, ``narrow_value``) arrive as
``ValueChecks``, built by the application from the registry. Without them a value write fails closed.

Which rules run depends on the action (§A.7.1-A.7.5):

* ``write`` (set/unset/append): R1-R11, R13 when the lock flag changes, R16;
* ``remove``: R1, R3, R10, R11, R12, R13 when the entry is locked, R16;
* ``lock``: R1, R3, R9, R10, R11, R12, R13, R16; ``unlock``: the same without R9.

``check_write`` raises the first violation; ``collect_write_problems`` returns all of them (ImportConfig).
Value rules R5, R6 and R8 are skipped when R4 already refused the operation, and R8 when the value is
invalid: their findings would only restate the earlier problem. No message quotes a secret value. A value
that cannot be stored (``entry.value_issue``: a lone surrogate, more than 64 KiB of canonical JSON) is an R5
problem of any key, a secret one included, so the planner and the rules never fail on it with a raw
exception. Integers of any width within the size are values like any other; when the schema engine cannot
write a finding about one as text (``_engine_issues``), the finding is still a structured R5 problem.
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, SkmError, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef

from .entry import VALUE_MAX_BYTES, ConfigEntry, EntryOp, copy_value, value_issue, version_conflict

__all__ = [
    "CHAIN_OPEN_LEVELS",
    "LOCK_LEVELS",
    "SHARED_LEVELS",
    "STORED_LEVELS",
    "VALUE_MAX_BYTES",
    "DeprecationView",
    "IssueView",
    "KeySpecView",
    "LayerRefView",
    "Problem",
    "ResolutionView",
    "ValueChecks",
    "WriteAction",
    "WriteContext",
    "WriteRequest",
    "check_write",
    "collect_write_problems",
    "required_permissions",
]

type WriteAction = Literal["write", "remove", "lock", "unlock"]

# Level vocabulary of platform.config.keys, as plain values (a test pins them to the engine's sets).
STORED_LEVELS: Final = frozenset(kind.value for kind in ScopeKind)
SHARED_LEVELS: Final = frozenset({"instance", "workspace", "host"})  # right config.write_shared
LOCK_LEVELS: Final = frozenset({"instance", "workspace"})
CHAIN_OPEN_LEVELS: Final = SHARED_LEVELS | {"invocation"}  # may open a narrow chain wider than the base
_BASE_LEVELS: Final = frozenset({"default", "pack"})  # base value of narrow, never a ceiling of its own
# Below it an integer is text under any int-to-text limit (sys.int_info.str_digits_check_threshold)
_TEXT_SAFE_INT: Final = 10**640

_ACTIONS: Final = frozenset({"write", "remove", "lock", "unlock"})
_EXISTING_ACTIONS: Final = frozenset({"remove", "lock", "unlock"})
_LOCK: Final = "config.lock"


class LayerRefView(Protocol):
    @property
    def level(self) -> str: ...
    @property
    def scope_id(self) -> UUID | None: ...
    def to_json(self) -> dict[str, JsonValue]: ...


class DeprecationView(Protocol):
    @property
    def replacement(self) -> str | None: ...


class KeySpecView(Protocol):
    """The fields of ``KeySpec`` the rules read."""

    @property
    def key(self) -> str: ...
    @property
    def levels(self) -> AbstractSet[str]: ...
    @property
    def merge(self) -> str: ...
    @property
    def sensitivity(self) -> str: ...
    @property
    def lockable(self) -> bool: ...
    @property
    def confirm(self) -> bool: ...
    @property
    def write_permission(self) -> str | None: ...
    @property
    def deprecated(self) -> DeprecationView | None: ...
    @property
    def value_type(self) -> str: ...  # ValueError when the schema has no single type


class ResolutionView(Protocol):
    """The fields of ``KeyResolution`` (farther levels without the target scope, §A.7.0) the rules read."""

    @property
    def value(self) -> object: ...  # MISSING when not present
    @property
    def present(self) -> bool: ...
    @property
    def winner(self) -> LayerRefView | None: ...
    @property
    def base(self) -> LayerRefView | None: ...
    @property
    def locked_by(self) -> LayerRefView | None: ...


class IssueView(Protocol):
    @property
    def pointer(self) -> str: ...
    @property
    def code(self) -> str: ...
    @property
    def message(self) -> str: ...


class ValueChecks(Protocol):
    """Engine operations for the key of the request (registry schema, ``deep_merge``, ``narrow_value``)."""

    def schema_issues(self, value: JsonValue, *, partial: bool = False) -> Sequence[IssueView]:
        """Findings against the key schema; ``partial``: the schema with ``required`` removed recursively."""
        ...

    def item_issues(self, item: JsonValue) -> Sequence[IssueView]:
        """Findings of one array element against ``items`` of the key schema."""
        ...

    def deep_merge(self, base: JsonValue, overlay: JsonValue) -> JsonValue: ...

    def narrow_value(self, current: JsonValue, candidate: JsonValue) -> JsonValue:
        """The stricter combination; ``ValueError`` when the values cannot be compared."""
        ...


@dataclass(frozen=True, slots=True)
class WriteRequest:
    scope: ScopeRef
    key: str
    op: EntryOp | None  # None for lock/unlock/remove
    value: JsonValue | None
    locked: bool | None  # None = keep the flag
    expected_row_version: int | None  # 0 = "there must be no entry"
    confirmed: bool
    action: WriteAction

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError(f"action must be one of {sorted(_ACTIONS)}, not {self.action!r}")
        if not isinstance(cast("object", self.scope), ScopeRef):
            raise TypeError("scope must be a ScopeRef")
        if self.action == "write":
            if self.op is None:
                raise ValueError("a write carries an operation")
            op = EntryOp(self.op)
            if op is EntryOp.UNSET and self.value is not None:
                raise ValueError("op=unset carries no value")
            object.__setattr__(self, "op", op)
        elif self.op is not None or self.value is not None or self.locked is not None:
            raise ValueError(f"{self.action} carries no operation, value or lock flag")
        if self.locked is not None and not isinstance(cast("object", self.locked), bool):
            raise TypeError("locked must be a bool or None")
        expected = self.expected_row_version
        if expected is not None and (
            isinstance(expected, bool) or not isinstance(cast("object", expected), int) or expected < 0
        ):
            raise ValueError("expected_row_version must be None or an integer >= 0")
        if not isinstance(cast("object", self.confirmed), bool):
            raise TypeError("confirmed must be a bool")
        object.__setattr__(self, "value", copy_value(self.value))


@dataclass(frozen=True, slots=True)
class WriteContext:
    spec: KeySpecView | None  # registry.find(key); None = unknown key (R1)
    existing: ConfigEntry | None  # entry of this scope and key (read FOR UPDATE)
    farther: ResolutionView | None  # resolution by the farther levels without this scope (§A.7.0)
    granted: frozenset[str]  # permissions of the actor in this scope
    checks: ValueChecks | None = None  # required for action="write" of a known key
    # reason_code of the decision that refused a permission (same actor and scope as ``granted``); R13/R16
    # report it as given and never make one up: a permission without one is refused without a reason
    refused: Mapping[str, str] = field(default_factory=lambda: {})

    def __post_init__(self) -> None:
        refused = dict(self.refused)
        for permission, reason in refused.items():
            if not isinstance(cast("object", reason), str) or not reason:
                raise ValueError(f"the refusal of {permission!r} carries no reason_code")
            if permission in self.granted:
                raise ValueError(f"{permission!r} is both granted and refused")
        object.__setattr__(self, "refused", MappingProxyType(refused))


@dataclass(frozen=True, slots=True)
class Problem:
    """One violation for ``ImportConfig.problems``; ``rule`` is ``R1``…``R16``."""

    rule: str
    code: str
    message: str
    key: str | None = None
    pointer: str | None = None
    details: Mapping[str, JsonValue] = field(default_factory=lambda: {})


@dataclass(frozen=True, slots=True)
class _Issue:
    pointer: str
    code: str
    message: str


def required_permissions(level: str, spec: KeySpecView | None, *, lock_change: bool) -> frozenset[str]:
    """Every permission a write at ``level`` needs (bus ``permissions_of``; all of the set are required).

    ``config.write_shared`` on instance/workspace/host, else ``config.write``; plus ``config.lock`` when a
    lock is set or cleared; plus ``spec.write_permission`` (for example ``hook.manage``).
    """
    value = str(level)
    if value not in STORED_LEVELS:
        raise ValueError(f"{value!r} is not a stored level")
    needed = {"config.write_shared" if value in SHARED_LEVELS else "config.write"}
    if lock_change:
        needed.add(_LOCK)
    if spec is not None and spec.write_permission:
        needed.add(spec.write_permission)
    return frozenset(needed)


def check_write(req: WriteRequest, ctx: WriteContext) -> None:
    """Raise the first violated rule in the normative order."""
    for _rule, error in _violations(req, ctx):
        raise error


def collect_write_problems(req: WriteRequest, ctx: WriteContext) -> tuple[Problem, ...]:
    """Every violation (ImportConfig); a value violation yields one problem per schema finding."""
    problems: list[Problem] = []
    for rule, error in _violations(req, ctx):
        issues = cast("list[Mapping[str, JsonValue]]", error.details.get("issues") or [])
        if rule == "R5" and issues:
            problems.extend(
                Problem(
                    rule,
                    error.code.value,
                    cast("str", issue["message"]),
                    key=req.key,
                    pointer=cast("str", issue["pointer"]),
                    details={"code": issue["code"]},
                )
                for issue in issues
            )
        else:
            problems.append(
                Problem(rule, error.code.value, error.message, key=req.key, details=dict(error.details))
            )
    return tuple(problems)


# ---------------------------------------------------------------------------------------------------------


def _violations(req: WriteRequest, ctx: WriteContext) -> Iterator[tuple[str, SkmError]]:
    spec, key = ctx.spec, req.key
    if spec is None:  # R1
        yield (
            "R1",
            ValidationFailed(
                ErrorCode.CONFIG_UNKNOWN_KEY, f"unknown settings key {key!r}", details={"key": key}
            ),
        )
        return
    _check_context(req, ctx, spec)
    level = req.scope.kind.value
    write = req.action == "write"
    existing = ctx.existing
    if write and spec.deprecated is not None:  # R2
        yield (
            "R2",
            ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"settings key {key!r} is deprecated",
                details={"key": key, "reason": "deprecated", "replacement": spec.deprecated.replacement},
            ),
        )
    if level not in STORED_LEVELS or level not in spec.levels:  # R3
        yield (
            "R3",
            ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"settings key {key!r} cannot be stored at level {level!r}",
                details={"key": key, "level": level, "allowed": _allowed_levels(spec)},
            ),
        )
    if write:
        yield from _value_rules(req, ctx, spec, level)
    if (req.locked is True or req.action == "lock") and (  # R9
        level not in LOCK_LEVELS or not spec.lockable
    ):
        yield (
            "R9",
            ValidationFailed(
                ErrorCode.CONFIG_SCOPE_NOT_ALLOWED,
                f"settings key {key!r} cannot be locked at level {level!r}",
                details={"key": key, "reason": "lock_level"},
            ),
        )
    if spec.confirm and not req.confirmed:  # R10
        yield (
            "R10",
            PreconditionFailed(
                ErrorCode.CONFIRMATION_REQUIRED,
                f"changing settings key {key!r} requires confirmation",
                details={"key": key, "reasons": ["key_requires_confirmation"]},
            ),
        )
    expected = req.expected_row_version
    if expected is not None:  # R11
        actual = 0 if existing is None else existing.row_version
        if expected != actual:
            yield "R11", version_conflict(expected, actual)
    if req.action in _EXISTING_ACTIONS and existing is None:  # R12
        yield (
            "R12",
            NotFound(
                ErrorCode.NOT_FOUND,
                f"no config entry for {key!r} in this scope",
                details={"kind": "config_entry", "scope_id": str(req.scope.id), "key": key},
            ),
        )
    if _needs_lock_right(req, existing) and _LOCK not in ctx.granted:  # R13
        yield (
            "R13",
            Forbidden(
                ErrorCode.FORBIDDEN,
                "setting, clearing or removing a lock requires config.lock",
                details=_denial_details(ctx, _LOCK),
            ),
        )
    permission = spec.write_permission
    if permission and permission not in ctx.granted:  # R16
        yield (
            "R16",
            Forbidden(
                ErrorCode.FORBIDDEN,
                f"writing settings key {key!r} requires {permission}",
                details=_denial_details(ctx, permission),
            ),
        )


def _denial_details(ctx: WriteContext, permission: str) -> dict[str, JsonValue]:
    """``FORBIDDEN`` details of a missing right: the permission and, when known, the refusing decision's
    ``reason_code`` (conventions §5)."""
    details: dict[str, JsonValue] = {"permission": permission}
    reason = ctx.refused.get(permission)
    if reason is not None:
        details["reason_code"] = reason
    return details


def _check_context(req: WriteRequest, ctx: WriteContext, spec: KeySpecView) -> None:
    """Programming errors of the caller, never user input."""
    if spec.key != req.key:
        raise ValueError(f"spec of {spec.key!r} given for {req.key!r}")
    existing = ctx.existing
    if existing is not None and (existing.key != req.key or existing.scope != req.scope):
        raise ValueError("the existing entry belongs to another scope or key")
    if req.action == "write" and (ctx.farther is None or ctx.checks is None):
        raise ValueError("a value write needs the farther resolution and value checks")


def _needs_lock_right(req: WriteRequest, existing: ConfigEntry | None) -> bool:
    if req.action in ("lock", "unlock"):
        return True
    if req.action == "remove":
        return existing is not None and existing.locked
    current = existing is not None and existing.locked
    return req.locked is not None and req.locked != current


def _value_rules(
    req: WriteRequest, ctx: WriteContext, spec: KeySpecView, level: str
) -> Iterator[tuple[str, SkmError]]:
    key, op, value = req.key, cast("EntryOp", req.op), req.value
    farther = cast("ResolutionView", ctx.farther)
    checks = cast("ValueChecks", ctx.checks)
    merge = str(spec.merge)
    allowed = True
    if op is EntryOp.APPEND:  # R4
        allowed = merge == "replace" and _value_type(spec) == "array"
    elif op is EntryOp.UNSET:
        allowed = merge not in ("narrow", "union")
    if not allowed:
        yield (
            "R4",
            ValidationFailed(
                ErrorCode.CONFIG_OP_NOT_ALLOWED,
                f"operation {op.value!r} is not allowed for settings key {key!r}",
                details={"key": key, "op": op.value, "merge": merge},
            ),
        )
    secret = str(spec.sensitivity) == "secret"
    valid = True
    if allowed and not secret:  # R5; a secret value's schema is R6's, so its text never reaches a message
        issues = _value_issues(op, value, merge, farther, checks)
        if issues:
            valid = False
            yield (
                "R5",
                ValidationFailed(
                    ErrorCode.CONFIG_INVALID,
                    f"invalid value for settings key {key!r}",
                    details={
                        "key": key,
                        "issues": [
                            {"pointer": i.pointer, "code": i.code, "message": i.message} for i in issues
                        ],
                    },
                ),
            )
    found = value_issue(value) if allowed and secret else None
    if found is not None:  # R5 of a secret value that cannot be stored; neither its text nor a pointer shown
        valid = False
        yield (
            "R5",
            ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"invalid value for settings key {key!r} (value not shown)",
                details={"key": key, "issues": [{"pointer": "", "code": found[1], "message": found[2]}]},
            ),
        )
    if allowed and secret and valid and op is EntryOp.SET and not _secret_ref(value, checks):  # R6
        valid = False
        yield (
            "R6",
            ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"settings key {key!r} takes a secret reference, not a secret value (value not shown)",
                details={"key": key, "reason": "secret_ref_required"},
            ),
        )
    locked_by = farther.locked_by
    if locked_by is not None:  # R7
        yield (
            "R7",
            PreconditionFailed(
                ErrorCode.CONFIG_LOCKED,
                f"settings key {key!r} is locked at {locked_by.level}",
                details={
                    "key": key,
                    "locked_by": {
                        "level": str(locked_by.level),
                        "scope_id": None if locked_by.scope_id is None else str(locked_by.scope_id),
                    },
                },
            ),
        )
    if allowed and valid and merge == "narrow" and op is EntryOp.SET:  # R8
        violation = _narrowing(key, level, value, farther, checks)
        if violation is not None:
            yield "R8", violation


def _allowed_levels(spec: KeySpecView) -> list[JsonValue]:
    return [str(item) for item in sorted(spec.levels)]


def _value_type(spec: KeySpecView) -> str | None:
    try:
        return spec.value_type
    except ValueError:
        return None


def _value_issues(  # noqa: PLR0911 -- one early answer per operation shape
    op: EntryOp, value: JsonValue | None, merge: str, farther: ResolutionView, checks: ValueChecks
) -> list[IssueView]:
    if op is EntryOp.UNSET:
        return []
    if value is None:
        return [_Issue("", "required", "a value is required; use unset to reset the key")]
    found = value_issue(value)  # a lone surrogate, then the size (VALUE_MAX_BYTES), before the schema
    if found is not None:
        return [_Issue(*found)]
    if op is EntryOp.APPEND and not isinstance(value, list):
        return [_Issue("", "type", "append takes an array of items")]
    if merge != "deep_merge":  # append is allowed only with merge=replace, so it is checked here too
        marker = _marker_pointer(value, "")
        if marker is not None:
            return [_Issue(marker, "unset_marker", '{"$unset": true} is allowed only in deep_merge maps')]
    if op is EntryOp.APPEND:
        return [
            _Issue(f"/{index}{issue.pointer}", issue.code, issue.message)
            for index, item in enumerate(cast("list[JsonValue]", value))
            for issue in _engine_issues(lambda item=item: checks.item_issues(item), item)
        ]
    if merge != "deep_merge":
        return _engine_issues(lambda: checks.schema_issues(value), value)
    stripped = _without_markers(value)
    partial = _engine_issues(lambda: checks.schema_issues(stripped, partial=True), stripped)
    if partial:
        return partial
    current = farther.value
    mapping = farther.present and isinstance(current, dict)
    below = copy_value(cast("Mapping[str, JsonValue]", current)) if mapping else {}
    merged = checks.deep_merge(below, value)
    return _engine_issues(lambda: checks.schema_issues(merged), merged)


def _engine_issues(find: Callable[[], Sequence[IssueView]], value: JsonValue) -> list[IssueView]:
    """Schema findings of ``value``. A finding quotes the value it is about, and the interpreter may refuse to
    write an integer of more than 640 digits as text (``sys.set_int_max_str_digits``): that ``ValueError`` of
    the engine is one R5 issue at the first such integer, not a raw exception. Any other error propagates."""
    try:
        return list(find())
    except ValueError:
        pointer = _wide_int_pointer(value, "")
        if pointer is None:
            raise
        return [_Issue(pointer, "integer_text", "the schema check cannot describe an integer this wide")]


def _wide_int_pointer(value: JsonValue, pointer: str) -> str | None:
    """Pointer of the first integer the interpreter may refuse to write as text."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return pointer if not -_TEXT_SAFE_INT < value < _TEXT_SAFE_INT else None
    if isinstance(value, dict):
        children = ((name.replace("~", "~0").replace("/", "~1"), item) for name, item in value.items())
    elif isinstance(value, list):
        children = ((str(index), item) for index, item in enumerate(value))
    else:
        return None
    for name, item in children:
        found = _wide_int_pointer(item, f"{pointer}/{name}")
        if found is not None:
            return found
    return None


def _is_marker(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and len(cast("Mapping[str, object]", value)) == 1
        and (cast("Mapping[str, object]", value).get("$unset") is True)
    )


def _marker_pointer(value: JsonValue, pointer: str) -> str | None:
    if _is_marker(value):
        return pointer
    if isinstance(value, dict):
        children = ((name.replace("~", "~0").replace("/", "~1"), item) for name, item in value.items())
    elif isinstance(value, list):
        children = ((str(index), item) for index, item in enumerate(value))
    else:
        return None
    for name, item in children:
        found = _marker_pointer(item, f"{pointer}/{name}")
        if found is not None:
            return found
    return None


def _without_markers(value: JsonValue) -> JsonValue:
    """The contribution as the partial schema sees it: entries holding an unset marker are dropped."""
    if isinstance(value, dict):
        return {name: _without_markers(item) for name, item in value.items() if not _is_marker(item)}
    if isinstance(value, list):
        return [_without_markers(item) for item in value]
    return value


def _secret_ref(value: JsonValue | None, checks: ValueChecks) -> bool:
    return isinstance(value, str) and not checks.schema_issues(value)


def _narrow_canon(value: JsonValue) -> tuple[object, ...]:
    """JSON identity of the engine's narrowing (``merge._canon``): bool is not a number, ``1 == 1.0``,
    nested arrays keep their order, objects compare by content."""
    if value is None:
        return ("z",)
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, int | float):
        return ("n", value)
    if isinstance(value, str):
        return ("s", value)
    if isinstance(value, list):
        return ("l", tuple(_narrow_canon(item) for item in value))
    return ("o", tuple(sorted((key, _narrow_canon(item)) for key, item in value.items())))


def _narrow_same(left: JsonValue, right: JsonValue) -> bool:
    """Equality of narrow values as the engine sees them; the outer intersect arrays compare as sets."""
    if isinstance(left, list) and isinstance(right, list):
        return {_narrow_canon(item) for item in left} == {_narrow_canon(item) for item in right}
    return _narrow_canon(left) == _narrow_canon(right)


def _narrowing(
    key: str, level: str, value: JsonValue, farther: ResolutionView, checks: ValueChecks
) -> SkmError | None:
    """R8 (§B.5.3, K16 variant A): an explicit farther result is a ceiling for every level; without one only
    project/plan/run are bounded by the base value (pack/default), and a missing base bounds nothing."""
    base = farther.base
    explicit = base is not None and str(base.level) not in _BASE_LEVELS
    if not explicit and (level in CHAIN_OPEN_LEVELS or not farther.present):
        return None
    ceiling = farther.value if farther.present else None
    try:
        narrower = farther.present and _narrow_same(
            checks.narrow_value(cast("JsonValue", ceiling), value), value
        )
    except ValueError:
        narrower = False
    if narrower:
        return None
    winner = farther.winner
    return ValidationFailed(
        ErrorCode.CONFIG_NARROWING_VIOLATION,
        "the value is wider than the ceiling of farther levels",
        details={
            "key": key,
            "ceiling": copy_value(ceiling),
            "ceiling_from": None if winner is None else winner.to_json(),
        },
    )
