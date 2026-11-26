"""Merge strategies and provenance of one key (settings §B.5).

``fold`` folds the contributions of one key, farthest first, into a ``KeyResolution``: the value, the
contribution that decided it, the base of a narrowing chain, the lock and one trace status per contribution.
It is pure and fail-closed: a contribution that may not take part (level, pack, override, lock, operation, a
value that would widen a ceiling or does not fit the strategy) is ignored with a reason and one warning per
reason; it is never applied and never raises. Only programming errors raise ``ValueError``: contributions out
of chain order, two defaults, a ``narrow`` key without narrow metadata.

``unset`` resets the key to its default on that level (§18 п.6): earlier contributions except the default are
shadowed, there is no tombstone. Monotonic keys (``narrow``, ``union``) refuse ``unset``. For ``narrow``
(§B.5.3, K16 variant A) default and pack give the base value, not a ceiling; only ``CHAIN_OPEN_LEVELS`` may
start the chain wider than the base, ``project``/``plan``/``run`` without farther explicit contributions only
narrow the base. A lock (instance/workspace) ignores every later contribution that passed the level checks.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, cast

from skm.kernel.json_types import JsonValue
from skm.kernel.outcomes import Diagnostic, Severity

from .keys import (
    BASE_LEVELS,
    CHAIN_LEVELS,
    CHAIN_OPEN_LEVELS,
    LOCK_LEVELS,
    MISSING,
    KeySpec,
    Level,
    MergeStrategy,
    Missing,
    NarrowDirection,
    NarrowSpec,
    Sensitivity,
    copy_json,
    freeze_json,
)
from .layers import Contribution, LayerRef

__all__ = [
    "IGNORE_REASONS",
    "ContributionTrace",
    "IgnoreReason",
    "KeyResolution",
    "TraceStatus",
    "apply_unset_markers",
    "deep_merge",
    "fold",
    "is_unset_marker",
    "narrow_value",
    "narrow_widens",
]

type TraceStatus = Literal["winner", "used", "shadowed", "ignored"]
type IgnoreReason = Literal[
    "locked_above",
    "scope_not_allowed",
    "narrowing_violation",
    "override_not_allowed",
    "op_not_allowed",
    "pack_not_allowed",
]

_STATUSES: Final = frozenset({"winner", "used", "shadowed", "ignored"})
# Checked in this order (§B.5.1 steps 1-6); diagnostics follow it too.
IGNORE_REASONS: Final[tuple[IgnoreReason, ...]] = (
    "scope_not_allowed",
    "pack_not_allowed",
    "override_not_allowed",
    "locked_above",
    "op_not_allowed",
    "narrowing_violation",
)
_DIAGNOSTIC_CODE: Final[Mapping[IgnoreReason, str]] = {
    "scope_not_allowed": "CONFIG_SCOPE_NOT_ALLOWED",
    "pack_not_allowed": "CONFIG_PACK_NOT_ALLOWED",
    "override_not_allowed": "CONFIG_OVERRIDE_NOT_ALLOWED",
    "locked_above": "CONFIG_LOCKED",
    "op_not_allowed": "CONFIG_OP_NOT_ALLOWED",
    "narrowing_violation": "CONFIG_NARROWING_VIOLATION",
}
_ALWAYS_ALLOWED: Final = frozenset({Level.DEFAULT, Level.PACK, Level.INVOCATION})
_LIST_STRATEGIES: Final = frozenset({MergeStrategy.APPEND, MergeStrategy.APPEND_UNIQUE, MergeStrategy.UNION})


@dataclass(frozen=True, slots=True)
class ContributionTrace:
    contribution: Contribution
    status: TraceStatus
    reason: IgnoreReason | None = None

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"status must be one of {sorted(_STATUSES)}, not {self.status!r}")
        if (self.status == "ignored") != (self.reason is not None):
            raise ValueError("a reason is given exactly for an ignored contribution")
        if self.reason is not None and self.reason not in IGNORE_REASONS:
            raise ValueError(f"reason must be one of {sorted(IGNORE_REASONS)}, not {self.reason!r}")


@dataclass(frozen=True, slots=True)
class KeyResolution:
    key: str
    value: JsonValue | Missing
    winner: LayerRef | None  # contribution that decided the value (union/append: the nearest used one)
    base: LayerRef | None  # narrow: started the chain (first applied explicit, else pack/default)
    locked_by: LayerRef | None
    trace: tuple[ContributionTrace, ...]
    diagnostics: tuple[Diagnostic, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.value is not MISSING:
            object.__setattr__(self, "value", freeze_json(self.value, "value"))
        object.__setattr__(self, "trace", tuple(self.trace))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def present(self) -> bool:
        return self.value is not MISSING


# ---------------------------------------------------------------------------------------------------------
# JSON identity: bool is not a number, 1 == 1.0, objects compare by content.

type _Canon = tuple[object, ...]


def _canon(value: JsonValue) -> _Canon:
    if value is None:
        return ("z",)
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, int | float):
        return ("n", value)
    if isinstance(value, str):
        return ("s", value)
    if isinstance(value, list):
        return ("l", tuple(_canon(item) for item in value))
    return ("o", tuple(sorted((key, _canon(item)) for key, item in value.items())))


def _same(left: JsonValue, right: JsonValue) -> bool:
    return _canon(left) == _canon(right)


def _unique(items: Sequence[JsonValue]) -> list[JsonValue]:
    seen: set[_Canon] = set()
    kept: list[JsonValue] = []
    for item in items:
        mark = _canon(item)
        if mark not in seen:
            seen.add(mark)
            kept.append(item)
    return kept


# ---------------------------------------------------------------------------------------------------------
# deep_merge (§B.5.5)


def is_unset_marker(value: object) -> bool:
    """``{"$unset": true}`` inside a ``deep_merge`` contribution: remove that key from the result."""
    if not isinstance(value, Mapping):
        return False
    marker = cast("Mapping[str, object]", value)
    return len(marker) == 1 and marker.get("$unset") is True


def deep_merge(base: Mapping[str, JsonValue], overlay: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Field-wise merge: objects (maps and fixed records) merge recursively, arrays and scalars replace,
    ``{"$unset": true}`` removes the key at any depth. The result is a plain copy without markers."""
    merged: dict[str, JsonValue] = {key: copy_json(item, key) for key, item in base.items()}
    for key, item in overlay.items():
        if is_unset_marker(item):
            merged.pop(key, None)
            continue
        below = merged.get(key)
        if isinstance(item, Mapping) and isinstance(below, Mapping):
            merged[key] = deep_merge(below, item)
        elif isinstance(item, Mapping):
            merged[key] = deep_merge({}, item)
        else:
            merged[key] = copy_json(item, key)
    return merged


def apply_unset_markers(value: JsonValue) -> JsonValue:
    """The value a contribution yields with nothing below it: objects lose their unset markers recursively."""
    return deep_merge({}, value) if isinstance(value, Mapping) else copy_json(value, "value")


# ---------------------------------------------------------------------------------------------------------
# narrow (§B.5.3): "unlimited" is the least strict value of the key.


type _Kind = Literal["number", "boolean", "set", "enum", "enum_map"]
type _Map = Mapping[str, JsonValue]


def _narrow_kind(spec: KeySpec) -> tuple[_Kind, NarrowSpec]:
    narrow = spec.narrow
    if spec.merge is not MergeStrategy.NARROW or narrow is None:
        raise ValueError(f"{spec.key}: not a narrow key with narrow metadata")
    if narrow.order is not None:
        return ("enum_map" if spec.value_type == "object" else "enum"), narrow
    match narrow.direction:
        case NarrowDirection.MIN | NarrowDirection.MAX:
            return "number", narrow
        case NarrowDirection.AND | NarrowDirection.OR:
            return "boolean", narrow
        case NarrowDirection.INTERSECT:
            return "set", narrow
        case None:
            raise ValueError(f"{spec.key}: narrow needs a direction or an order")


def _unlimited(narrow: NarrowSpec, value: JsonValue) -> bool:
    return not isinstance(narrow.unlimited, Missing) and _same(narrow.unlimited, value)


def _rank(order: tuple[str, ...], value: JsonValue) -> int:
    if not isinstance(value, str) or value not in order:
        raise ValueError(f"{value!r} is not one of {list(order)}")
    return order.index(value)


def _check_shape(kind: _Kind, narrow: NarrowSpec, value: JsonValue) -> None:
    """Raises ``ValueError`` when ``value`` cannot take part in narrowing of this kind."""
    match kind:
        case "number":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError("a number is required")
        case "boolean":
            if not isinstance(value, bool):
                raise ValueError("a boolean is required")
        case "set":
            if not isinstance(value, list):
                raise ValueError("an array is required")
        case "enum":
            _rank(cast("tuple[str, ...]", narrow.order), value)
        case "enum_map":
            if not isinstance(value, Mapping):
                raise ValueError("an object is required")
            for item in value.values():
                _rank(cast("tuple[str, ...]", narrow.order), item)


def _widens(kind: _Kind, narrow: NarrowSpec, current: JsonValue, candidate: JsonValue) -> bool:
    _check_shape(kind, narrow, current)
    _check_shape(kind, narrow, candidate)
    if kind in ("number", "set"):
        if _unlimited(narrow, candidate):
            return not _unlimited(narrow, current)
        if _unlimited(narrow, current):
            return False
    match kind:
        case "number":
            a, b = cast("float", current), cast("float", candidate)
            return b > a if narrow.direction is NarrowDirection.MIN else b < a
        case "boolean":
            stricter = narrow.direction is NarrowDirection.OR  # or: true is stricter; and: false is stricter
            return current is stricter and candidate is not stricter
        case "set":
            allowed = {_canon(item) for item in cast("list[JsonValue]", current)}
            return any(_canon(item) not in allowed for item in cast("list[JsonValue]", candidate))
        case "enum":
            order = cast("tuple[str, ...]", narrow.order)
            return _rank(order, candidate) < _rank(order, current)
        case "enum_map":
            order = cast("tuple[str, ...]", narrow.order)
            a_map, b_map = cast("_Map", current), cast("_Map", candidate)
            return any(_rank(order, b_map[key]) < _rank(order, a_map[key]) for key in b_map if key in a_map)


def _narrowed(kind: _Kind, narrow: NarrowSpec, current: JsonValue, candidate: JsonValue) -> JsonValue:
    if kind in ("number", "set"):
        if _unlimited(narrow, current):
            return copy_json(candidate, "value")
        if _unlimited(narrow, candidate):
            return copy_json(current, "value")
    match kind:
        case "number":
            a, b = cast("float", current), cast("float", candidate)
            return min(a, b) if narrow.direction is NarrowDirection.MIN else max(a, b)
        case "boolean":
            if narrow.direction is NarrowDirection.OR:
                return bool(current) or bool(candidate)
            return bool(current) and bool(candidate)
        case "set":
            kept = {_canon(item) for item in cast("list[JsonValue]", candidate)}
            items = cast("list[JsonValue]", current)
            return [copy_json(item, "value") for item in items if _canon(item) in kept]
        case "enum":
            order = cast("tuple[str, ...]", narrow.order)
            return current if _rank(order, current) >= _rank(order, candidate) else candidate
        case "enum_map":
            order = cast("tuple[str, ...]", narrow.order)
            a_map, b_map = cast("_Map", current), cast("_Map", candidate)
            merged: dict[str, JsonValue] = {}
            for key, item in a_map.items():
                other = b_map.get(key, item)
                merged[key] = item if _rank(order, item) >= _rank(order, other) else other
            for key, item in b_map.items():
                merged.setdefault(key, item)
            return merged


def narrow_widens(spec: KeySpec, current: JsonValue, candidate: JsonValue) -> bool:
    """Whether ``candidate`` is wider (less strict) than ``current`` for a narrow key ("шире", §B.5.3).
    ``ValueError`` when a value cannot be compared (wrong type, value outside ``order``)."""
    kind, narrow = _narrow_kind(spec)
    return _widens(kind, narrow, current, candidate)


def narrow_value(spec: KeySpec, current: JsonValue, candidate: JsonValue) -> JsonValue:
    """The stricter combination of two values of a narrow key (table §B.5.3); ``ValueError`` as above."""
    kind, narrow = _narrow_kind(spec)
    _check_shape(kind, narrow, current)
    _check_shape(kind, narrow, candidate)
    return _narrowed(kind, narrow, current, candidate)


# ---------------------------------------------------------------------------------------------------------
# fold (§B.5.1)


class _Fold:
    def __init__(self, spec: KeySpec, contributions: Sequence[Contribution]) -> None:
        self.spec = spec
        self.items = contributions
        self.status: list[TraceStatus] = ["used"] * len(contributions)
        self.reason: list[IgnoreReason | None] = [None] * len(contributions)
        self.value: JsonValue | Missing = MISSING
        self.locked_by: LayerRef | None = None
        self.base: LayerRef | None = None
        self.default_at: int | None = None
        self.bad_locks: list[LayerRef] = []
        self.ceilings: list[tuple[int, JsonValue | Missing, LayerRef | None]] = []
        # narrow state: the base value (default/pack) and whether an explicit contribution opened the chain
        self.base_at: int | None = None
        self.open = False

    def ignore(self, index: int, reason: IgnoreReason) -> None:
        self.status[index] = "ignored"
        self.reason[index] = reason

    def shadow(self, indices: Sequence[int]) -> None:
        for index in indices:
            if self.status[index] == "used":
                self.status[index] = "shadowed"

    def applied(self, below: int) -> list[int]:
        return [index for index in range(below) if self.status[index] != "ignored"]

    def gate(self, contribution: Contribution) -> IgnoreReason | None:
        spec, level = self.spec, contribution.layer.level
        if level not in _ALWAYS_ALLOWED and level not in spec.levels:
            return "scope_not_allowed"
        if level is Level.PACK and not spec.pack:
            return "pack_not_allowed"
        if level is Level.INVOCATION and not spec.override:
            return "override_not_allowed"
        if self.locked_by is not None:
            return "locked_above"
        if not self.op_allowed(contribution):
            return "op_not_allowed"
        return None

    def op_allowed(self, contribution: Contribution) -> bool:
        spec, value = self.spec, contribution.value
        match contribution.op:
            case "unset":
                return not spec.monotonic
            case "append":
                return spec.merge is MergeStrategy.REPLACE and _array_key(spec) and isinstance(value, list)
            case _:
                if spec.merge in _LIST_STRATEGIES:
                    return isinstance(value, list)
                if spec.merge is MergeStrategy.DEEP_MERGE:
                    return isinstance(value, Mapping)
                return True

    def reset(self, index: int) -> None:
        """``unset``: back to the default; everything applied before, except the default, is shadowed."""
        self.shadow([at for at in self.applied(index) if at != self.default_at])
        if self.default_at is None:
            self.value = MISSING
        else:
            self.status[self.default_at] = "used"
            default = self.items[self.default_at].value
            self.value = deep_merge({}, default) if isinstance(default, Mapping) else default

    def apply(self, index: int, contribution: Contribution) -> None:
        op, value, merge = contribution.op, contribution.value, self.spec.merge
        if op == "default":
            self.default_at = index
        if merge is MergeStrategy.NARROW:
            self.apply_narrow(index, contribution)
            return
        if op == "unset":
            self.reset(index)
            return
        current = self.value
        match merge:
            case MergeStrategy.REPLACE if op == "append":
                if not isinstance(current, list):
                    self.shadow(self.applied(index))
                    current = []
                self.value = [*current, *cast("list[JsonValue]", value)]
            case MergeStrategy.REPLACE:
                self.shadow(self.applied(index))
                self.value = value
            case MergeStrategy.APPEND | MergeStrategy.APPEND_UNIQUE:
                joined = [*(current if isinstance(current, list) else []), *cast("list[JsonValue]", value)]
                self.value = _unique(joined) if merge is MergeStrategy.APPEND_UNIQUE else joined
            case MergeStrategy.UNION:
                joined = [*(current if isinstance(current, list) else []), *cast("list[JsonValue]", value)]
                self.value = sorted(_unique(joined), key=_canon)
            case MergeStrategy.DEEP_MERGE:
                below = current if isinstance(current, Mapping) else {}
                self.value = deep_merge(below, cast("Mapping[str, JsonValue]", value))
            case _:  # pragma: no cover - NARROW is handled above
                raise AssertionError(merge)

    def apply_narrow(self, index: int, contribution: Contribution) -> None:
        kind, narrow = _narrow_kind(self.spec)
        layer, value = contribution.layer, contribution.value
        try:
            _check_shape(kind, narrow, value)
        except ValueError:
            self.violation(index)
            return
        if layer.level in BASE_LEVELS:  # base values replace each other and never open the chain
            if self.base_at is not None:
                self.shadow([self.base_at])
            self.base_at, self.value, self.base = index, value, layer
            return
        if not self.open:
            base = self.value
            if layer.level in CHAIN_OPEN_LEVELS or isinstance(base, Missing):
                self.value = value
            elif _widens(kind, narrow, base, value):
                self.violation(index)
                return
            else:
                self.value = _narrowed(kind, narrow, base, value)
            if self.base_at is not None:
                self.shadow([self.base_at])
            self.open, self.base = True, layer
            return
        current = cast("JsonValue", self.value)
        if _widens(kind, narrow, current, value):
            self.violation(index)
            return
        self.value = _narrowed(kind, narrow, current, value)

    def violation(self, index: int) -> None:
        applied = self.applied(index)
        self.ceilings.append((index, self.value, self.items[applied[-1]].layer if applied else None))
        self.ignore(index, "narrowing_violation")

    def run(self) -> KeyResolution:
        for index, contribution in enumerate(self.items):
            reason = self.gate(contribution)
            if reason is not None:
                self.ignore(index, reason)
            else:
                self.apply(index, contribution)
            if contribution.locked and contribution.layer.level not in LOCK_LEVELS:
                self.bad_locks.append(contribution.layer)
            elif contribution.locked and self.status[index] != "ignored" and self.locked_by is None:
                self.locked_by = contribution.layer
        used = [index for index, status in enumerate(self.status) if status == "used"]
        winner = used[-1] if used else None
        if winner is not None:
            self.status[winner] = "winner"
        trace = tuple(
            ContributionTrace(item, self.status[index], self.reason[index])
            for index, item in enumerate(self.items)
        )
        return KeyResolution(
            key=self.spec.key,
            value=self.value,
            winner=None if winner is None else self.items[winner].layer,
            base=self.base if self.spec.merge is MergeStrategy.NARROW else None,
            locked_by=self.locked_by,
            trace=trace,
            diagnostics=self.diagnostics(),
        )

    def diagnostics(self) -> tuple[Diagnostic, ...]:
        found: list[Diagnostic] = []
        for reason in IGNORE_REASONS:
            layers = [self.items[i].layer for i, why in enumerate(self.reason) if why == reason]
            if layers:
                found.append(self.diagnostic(reason, layers))
        if self.bad_locks:
            found.append(
                Diagnostic(
                    code="CONFIG_SCOPE_NOT_ALLOWED",
                    message=f"lock at {', '.join(ref.display for ref in self.bad_locks)} is ignored: "
                    "only instance and workspace may lock a key",
                    severity=Severity.WARNING,
                    target=self.spec.key,
                    details={"reason": "lock_level", "layers": [ref.to_json() for ref in self.bad_locks]},
                )
            )
        return tuple(found)

    def diagnostic(self, reason: IgnoreReason, layers: Sequence[LayerRef]) -> Diagnostic:
        count = len(layers)
        noun = "contribution" if count == 1 else "contributions"
        verb = "is" if count == 1 else "are"
        details: dict[str, JsonValue] = {"layers": [ref.to_json() for ref in layers]}
        message = _MESSAGES[reason](self.spec)
        if reason == "locked_above":
            locked = cast("LayerRef", self.locked_by)
            details["layer"] = locked.to_json()
            message = f"{count} {noun} below {locked.display} {verb} ignored: the key is locked there"
        elif reason == "narrowing_violation":
            details["violations"] = [self.violation_details(*entry) for entry in self.ceilings]
            message = f"{count} {noun} {verb} ignored: {message}"
        else:
            message = f"{count} {noun} {verb} ignored: {message}"
        return Diagnostic(
            code=_DIAGNOSTIC_CODE[reason],
            message=message,
            severity=Severity.WARNING,
            target=self.spec.key,
            details=details,
        )

    def violation_details(
        self, index: int, ceiling: JsonValue | Missing, source: LayerRef | None
    ) -> dict[str, JsonValue]:
        entry: dict[str, JsonValue] = {"layer": self.items[index].layer.to_json()}
        if self.spec.sensitivity is not Sensitivity.SECRET:  # narrow keys are never secret; stay safe
            entry["value"] = self.items[index].value
            entry["ceiling"] = None if isinstance(ceiling, Missing) else ceiling
        entry["ceiling_from"] = None if source is None else source.to_json()
        return entry


_MESSAGES: Final[Mapping[IgnoreReason, Callable[[KeySpec], str]]] = {
    "scope_not_allowed": lambda spec: f"the level is not allowed for the key ({sorted(spec.levels)})",
    "pack_not_allowed": lambda _spec: "packs may not set this key",
    "override_not_allowed": lambda _spec: "invocation overrides are not allowed for this key",
    "locked_above": lambda _spec: "the key is locked above",
    "op_not_allowed": lambda spec: f"the operation or value shape does not fit merge {spec.merge.value}",
    "narrowing_violation": lambda _spec: "the value would widen the narrowing ceiling of farther levels",
}


def _array_key(spec: KeySpec) -> bool:
    try:
        return spec.value_type == "array"
    except ValueError:
        return False


def _check_order(spec: KeySpec, contributions: Sequence[Contribution]) -> None:
    rank = {level: index for index, level in enumerate(CHAIN_LEVELS[spec.chain])}
    last = -1
    defaults = 0
    for contribution in contributions:
        level = contribution.layer.level
        defaults += level is Level.DEFAULT
        position = rank.get(level)
        if position is None:  # level of another chain or provenance only: ignored as scope_not_allowed
            continue
        if position < last:
            raise ValueError(f"{spec.key}: contributions go farthest first, {level.value!r} is out of order")
        last = position
    if defaults > 1:
        raise ValueError(f"{spec.key}: at most one default contribution")


def fold(spec: KeySpec, contributions: Sequence[Contribution]) -> KeyResolution:
    """Resolve one key from its contributions, farthest first (§B.5.1-B.5.6). Pure."""
    items = tuple(contributions)
    _check_order(spec, items)
    if spec.merge is MergeStrategy.NARROW:
        _narrow_kind(spec)
    return _Fold(spec, items).run()
