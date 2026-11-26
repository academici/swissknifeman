"""Key metadata and level vocabulary of the config engine (settings §B.1).

These are pure value types: the registry reads ``x-skm`` and builds ``KeySpec``; merge
and the resolver only consume them. ``MISSING`` is "no value" and is never ``None`` (``None`` is a
legal JSON value of a nullable key). JSON fragments (schema, default, ``unlimited``) are deep-frozen on
construction into ``FrozenDict``/``FrozenList``: they stay ``dict``/``list`` for JSON Schema and ``json``
consumers, compare equal to plain JSON, but every mutating call raises ``TypeError``. A spec therefore never
aliases a caller's container and nobody can change it afterwards; ``copy_json`` yields a plain mutable copy.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal, NoReturn, Self, cast, final, overload, override

from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "BASE_LEVELS",
    "CHAIN_LEVELS",
    "CHAIN_OPEN_LEVELS",
    "CHAIN_STORED_LEVELS",
    "EXPLICIT_LEVELS",
    "LOCK_LEVELS",
    "MISSING",
    "SECRET_REF_URN",
    "SHARED_LEVELS",
    "STORED_LEVELS",
    "Chain",
    "Deprecation",
    "FrozenDict",
    "FrozenList",
    "KeySpec",
    "Level",
    "MergeStrategy",
    "Missing",
    "NarrowDirection",
    "NarrowSpec",
    "Reload",
    "SectionInfo",
    "Sensitivity",
    "UiHints",
    "ValidatorSpec",
    "ValueType",
    "copy_json",
    "freeze_json",
]

SECRET_REF_URN: Final = "urn:skm:config:secret-ref:v1"

type ValueType = Literal["string", "integer", "number", "boolean", "array", "object", "secret"]


class Chain(StrEnum):
    WORK = "work"
    HOST = "host"


class Level(StrEnum):
    DEFAULT = "default"
    PACK = "pack"
    INSTANCE = "instance"
    WORKSPACE = "workspace"
    PROJECT = "project"
    PLAN = "plan"
    RUN = "run"
    HOST = "host"
    INVOCATION = "invocation"
    RUN_BUNDLE = "run_bundle"  # provenance only: value taken from the frozen run snapshot
    PROCESS = "process"  # provenance only: restart key fixed at process start


class MergeStrategy(StrEnum):
    REPLACE = "replace"
    DEEP_MERGE = "deep_merge"
    APPEND = "append"
    APPEND_UNIQUE = "append_unique"
    UNION = "union"
    NARROW = "narrow"


class Reload(StrEnum):
    LIVE = "live"
    RUN_FROZEN = "run_frozen"
    RESTART = "restart"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SECRET = "secret"


class NarrowDirection(StrEnum):
    MIN = "min"
    MAX = "max"
    AND = "and"
    OR = "or"
    INTERSECT = "intersect"


# Layer order inside a chain, farthest first (§B.1). Provenance-only levels are in no chain.
CHAIN_LEVELS: Final[Mapping[Chain, tuple[Level, ...]]] = MappingProxyType(
    {
        Chain.WORK: (
            Level.DEFAULT,
            Level.PACK,
            Level.INSTANCE,
            Level.WORKSPACE,
            Level.PROJECT,
            Level.PLAN,
            Level.RUN,
            Level.INVOCATION,
        ),
        Chain.HOST: (Level.DEFAULT, Level.PACK, Level.INSTANCE, Level.HOST, Level.INVOCATION),
    }
)
STORED_LEVELS: Final = frozenset(
    {Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN, Level.HOST}
)
SHARED_LEVELS: Final = frozenset({Level.INSTANCE, Level.WORKSPACE, Level.HOST})  # right config.write_shared
LOCK_LEVELS: Final = frozenset({Level.INSTANCE, Level.WORKSPACE})
BASE_LEVELS: Final = frozenset({Level.DEFAULT, Level.PACK})  # base value of narrow, not a ceiling (§B.5.3)
EXPLICIT_LEVELS: Final = STORED_LEVELS | {Level.INVOCATION}  # narrow the chain (§B.5.3)
# May open a narrow chain wider than the base value; invocation reaches fold only with spec.override
# (§B.5.1 step 3).
CHAIN_OPEN_LEVELS: Final = SHARED_LEVELS | {Level.INVOCATION}
# Stored levels a key of the chain may declare in ``x-skm.levels`` (REG-04).
CHAIN_STORED_LEVELS: Final[Mapping[Chain, frozenset[Level]]] = MappingProxyType(
    {
        chain: frozenset(level for level in levels if level in STORED_LEVELS)
        for chain, levels in CHAIN_LEVELS.items()
    }
)


@final
class Missing:
    """Singleton for "no value": falsy, unequal to ``None``, the same object after copy/deepcopy/pickle."""

    __slots__ = ()
    _instance: "Missing | None" = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cast("Self", cls._instance)

    @override
    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: object) -> Self:
        return self

    @override
    def __reduce__(self) -> str:
        return "MISSING"


MISSING: Final = Missing()


@overload
def copy_json(value: Mapping[str, object], path: str) -> JsonObject: ...
@overload
def copy_json(value: object, path: str) -> JsonValue: ...
def copy_json(value: object, path: str) -> JsonValue:
    """Deep copy of a JSON value; a non-JSON value (set, tuple, NaN, non-str key) is a ``TypeError``."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path}: non-finite float is not JSON")
        return value
    if isinstance(value, list):
        return [copy_json(item, f"{path}[{index}]") for index, item in enumerate(cast("list[object]", value))]
    if isinstance(value, Mapping):
        copied: dict[str, JsonValue] = {}
        for key, item in cast("Mapping[object, object]", value).items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: object keys must be strings")
            copied[key] = copy_json(item, f"{path}.{key}")
        return copied
    raise TypeError(f"{path}: {type(value).__name__} is not a JSON value")


def _deny(self: object, *_args: object, **_kwargs: object) -> NoReturn:
    raise TypeError(f"{type(self).__name__} is immutable")


class FrozenDict(dict[str, JsonValue]):
    """A JSON object that cannot be changed after construction."""

    __slots__ = ()

    @override
    def __reduce__(self) -> tuple[type[Self], tuple[dict[str, JsonValue]]]:
        return type(self), (dict(self),)


class FrozenList(list[JsonValue]):
    """A JSON array that cannot be changed after construction."""

    __slots__ = ()

    @override
    def __reduce__(self) -> tuple[type[Self], tuple[list[JsonValue]]]:
        return type(self), (list(self),)


for _name in (
    "__setitem__",
    "__delitem__",
    "__ior__",
    "clear",
    "pop",
    "popitem",
    "setdefault",
    "update",
):
    setattr(FrozenDict, _name, _deny)
for _name in (
    "__setitem__",
    "__delitem__",
    "__iadd__",
    "__imul__",
    "append",
    "clear",
    "extend",
    "insert",
    "pop",
    "remove",
    "reverse",
    "sort",
):
    setattr(FrozenList, _name, _deny)
del _name


def freeze_json(value: object, path: str) -> JsonValue:
    """Deep immutable copy of a JSON value (``FrozenDict``/``FrozenList``), validated as ``copy_json``."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path}: non-finite float is not JSON")
        return value
    if isinstance(value, list):
        return FrozenList(
            freeze_json(item, f"{path}[{index}]") for index, item in enumerate(cast("list[object]", value))
        )
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in cast("Mapping[object, object]", value).items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: object keys must be strings")
            frozen[key] = freeze_json(item, f"{path}.{key}")
        return FrozenDict(frozen)
    raise TypeError(f"{path}: {type(value).__name__} is not a JSON value")


def _json_or_missing(value: object, path: str) -> JsonValue | Missing:
    return MISSING if value is MISSING else freeze_json(value, path)


def _set(obj: object, name: str, value: object) -> None:
    object.__setattr__(obj, name, value)


def _enum[E: StrEnum](kind: type[E], value: object, field: str) -> E:
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(member.value for member in kind)
        raise ValueError(f"{field}: {value!r} is not one of {allowed}") from None


@dataclass(frozen=True, slots=True)
class NarrowSpec:
    direction: NarrowDirection | None = None
    order: tuple[str, ...] | None = None
    unlimited: JsonValue | Missing = MISSING

    def __post_init__(self) -> None:
        if self.direction is not None:
            _set(self, "direction", _enum(NarrowDirection, self.direction, "narrow.direction"))
        if self.order is not None:
            order = tuple(self.order)
            if (
                len(order) < 2
                or len(set(order)) != len(order)
                or not all(isinstance(item, str) for item in cast("tuple[object, ...]", order))
            ):
                raise ValueError("narrow.order: at least two distinct strings are required")
            _set(self, "order", order)
        _set(self, "unlimited", _json_or_missing(self.unlimited, "narrow.unlimited"))

    @classmethod
    def from_metadata(cls, narrow: Mapping[str, JsonValue]) -> Self:
        unknown = set(narrow) - {"direction", "order", "unlimited"}
        if unknown:
            raise ValueError(f"narrow: unknown fields {sorted(unknown)}")
        direction = narrow.get("direction")
        order = narrow.get("order")
        return cls(
            None if direction is None else _enum(NarrowDirection, direction, "narrow.direction"),
            None if order is None else tuple(cast("Iterable[str]", order)),
            narrow.get("unlimited", MISSING),
        )


@dataclass(frozen=True, slots=True)
class UiHints:
    group: str
    order: int
    widget: str
    advanced: bool = False
    title: str | None = None
    help_url: str | None = None

    @classmethod
    def from_metadata(cls, ui: Mapping[str, JsonValue]) -> Self:
        unknown = set(ui) - {"group", "order", "widget", "advanced", "title", "help_url"}
        if unknown:
            raise ValueError(f"ui: unknown fields {sorted(unknown)}")
        return cls(
            group=cast("str", ui["group"]),
            order=cast("int", ui["order"]),
            widget=cast("str", ui["widget"]),
            advanced=cast("bool", ui.get("advanced", False)),
            title=cast("str | None", ui.get("title")),
            help_url=cast("str | None", ui.get("help_url")),
        )


@dataclass(frozen=True, slots=True)
class Deprecation:
    since: str
    replacement: str | None = None
    until: str | None = None

    @classmethod
    def from_metadata(cls, deprecated: Mapping[str, JsonValue]) -> Self:
        unknown = set(deprecated) - {"since", "replacement", "until"}
        if unknown:
            raise ValueError(f"deprecated: unknown fields {sorted(unknown)}")
        return cls(
            since=cast("str", deprecated["since"]),
            replacement=cast("str | None", deprecated.get("replacement")),
            until=cast("str | None", deprecated.get("until")),
        )


_X_SKM_FIELDS: Final = frozenset(
    {
        "chain",
        "levels",
        "merge",
        "reload",
        "override",
        "sensitivity",
        "portable",
        "lockable",
        "nullable",
        "pack",
        "confirm",
        "path",
        "write_permission",
        "validators",
        "narrow",
        "deprecated",
        "ui",
    }
)
_X_SKM_REQUIRED: Final = frozenset(
    {
        "chain",
        "levels",
        "merge",
        "reload",
        "override",
        "sensitivity",
        "portable",
        "lockable",
        "nullable",
        "pack",
    }
    | {"confirm", "ui"}
)
_VALUE_TYPES: Final = frozenset({"string", "integer", "number", "boolean", "array", "object"})


def _schema_type(schema: Mapping[str, JsonValue]) -> str | None:
    """The single non-null JSON type a leaf schema describes, or ``None`` when it cannot be told."""
    if schema.get("$ref") == SECRET_REF_URN:
        return "secret"
    declared = schema.get("type")
    if isinstance(declared, str):
        return declared
    if isinstance(declared, list):
        names = [name for name in declared if name != "null"]
        only = names[0] if len(names) == 1 else None
        return only if isinstance(only, str) and only in _VALUE_TYPES else None
    found: set[str | None] = set()
    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            found |= {
                _schema_type(branch)
                for branch in branches
                if isinstance(branch, dict) and branch.get("type") != "null"
            }
    return next(iter(found)) if len(found) == 1 else None


@dataclass(frozen=True, slots=True)
class KeySpec:
    key: str
    section: str
    owner: str
    value_schema: Mapping[str, JsonValue]  # leaf schema without default/description/x-skm
    default: JsonValue | Missing
    description: str
    chain: Chain
    levels: frozenset[Level]
    merge: MergeStrategy
    reload: Reload
    override: bool
    sensitivity: Sensitivity
    portable: bool
    lockable: bool
    nullable: bool  # the effective value may be MISSING; unrelated to a JSON null value
    pack: bool
    confirm: bool
    path: bool
    write_permission: str | None  # x-skm.write_permission: right on top of config.write / config.write_shared
    narrow: NarrowSpec | None
    validators: tuple[str, ...]
    deprecated: Deprecation | None
    ui: UiHints

    def __post_init__(self) -> None:
        if not self.key or not self.section:
            raise ValueError("key and section must not be empty")
        _set(self, "value_schema", freeze_json(self.value_schema, "value_schema"))
        _set(self, "default", _json_or_missing(self.default, "default"))
        _set(self, "chain", _enum(Chain, self.chain, "chain"))
        levels = frozenset(_enum(Level, level, "levels") for level in self.levels)
        if not levels or not levels <= STORED_LEVELS:
            raise ValueError(f"levels: a non-empty subset of {sorted(STORED_LEVELS)} is required")
        _set(self, "levels", levels)
        _set(self, "merge", _enum(MergeStrategy, self.merge, "merge"))
        _set(self, "reload", _enum(Reload, self.reload, "reload"))
        _set(self, "sensitivity", _enum(Sensitivity, self.sensitivity, "sensitivity"))
        _set(self, "validators", tuple(self.validators))
        if self.write_permission is not None and not self.write_permission:
            raise ValueError("write_permission must be None or a permission id")

    @classmethod
    def from_metadata(
        cls,
        *,
        key: str,
        section: str,
        owner: str,
        value_schema: Mapping[str, JsonValue],
        default: JsonValue | Missing,
        description: str,
        x_skm: Mapping[str, JsonValue],
    ) -> Self:
        """Builds a spec from an ``x-skm`` object (already valid per ``urn:skm:config:key-spec:v1``; the
        registry reports schema violations as REG-03 before calling this). Optional fields take §B.1 defaults.
        """
        unknown = set(x_skm) - _X_SKM_FIELDS
        missing = _X_SKM_REQUIRED - set(x_skm)
        if unknown or missing:
            raise ValueError(f"x-skm: unknown fields {sorted(unknown)}, missing fields {sorted(missing)}")
        narrow = x_skm.get("narrow")
        deprecated = x_skm.get("deprecated")
        return cls(
            key=key,
            section=section,
            owner=owner,
            value_schema=value_schema,
            default=default,
            description=description,
            chain=_enum(Chain, x_skm["chain"], "chain"),
            levels=frozenset(
                _enum(Level, level, "levels") for level in cast("Iterable[str]", x_skm["levels"])
            ),
            merge=_enum(MergeStrategy, x_skm["merge"], "merge"),
            reload=_enum(Reload, x_skm["reload"], "reload"),
            override=cast("bool", x_skm["override"]),
            sensitivity=_enum(Sensitivity, x_skm["sensitivity"], "sensitivity"),
            portable=cast("bool", x_skm["portable"]),
            lockable=cast("bool", x_skm["lockable"]),
            nullable=cast("bool", x_skm["nullable"]),
            pack=cast("bool", x_skm["pack"]),
            confirm=cast("bool", x_skm["confirm"]),
            path=cast("bool", x_skm.get("path", False)),
            write_permission=cast("str | None", x_skm.get("write_permission")),
            narrow=None
            if narrow is None
            else NarrowSpec.from_metadata(cast("Mapping[str, JsonValue]", narrow)),
            validators=tuple(cast("Iterable[str]", x_skm.get("validators", ()))),
            deprecated=(
                None
                if deprecated is None
                else Deprecation.from_metadata(cast("Mapping[str, JsonValue]", deprecated))
            ),
            ui=UiHints.from_metadata(cast("Mapping[str, JsonValue]", x_skm["ui"])),
        )

    @property
    def monotonic(self) -> bool:
        return self.merge in (MergeStrategy.NARROW, MergeStrategy.UNION)

    @property
    def value_type(self) -> ValueType:
        found = _schema_type(self.value_schema)
        if found is None or found not in _VALUE_TYPES | {"secret"}:
            raise ValueError(f"{self.key}: value schema has no single JSON type")
        return cast("ValueType", found)


@dataclass(frozen=True, slots=True)
class ValidatorSpec:
    id: str
    keys: tuple[str, ...]
    rule: str

    def __post_init__(self) -> None:
        _set(self, "keys", tuple(self.keys))


@dataclass(frozen=True, slots=True)
class SectionInfo:
    id: str
    owner: str
    title: str
    schema_urn: str
    view: type
    validators: tuple[ValidatorSpec, ...]
    keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _set(self, "validators", tuple(self.validators))
        _set(self, "keys", tuple(self.keys))
