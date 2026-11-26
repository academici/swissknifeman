"""Domain write rules R1-R13, R16 of settings §A.5 plus the entry/history invariants they rely on.

The engine side (``KeySpec``, ``fold`` → ``KeyResolution``, schema validation, ``deep_merge``,
``narrow_value``) is the real ``platform.config`` code: the domain reads it only structurally, so these
tests pin that the real types fit the domain views and the rules agree with the engine.
"""

import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from runpy import run_path
from typing import Any, cast, override
from uuid import UUID, uuid4

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, PreconditionFailed, SkmError, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.settings.domain import write_rules
from skm.modules.settings.domain.entry import (
    VALUE_MAX_BYTES,
    ConfigEntry,
    ConfigEntryId,
    EntryOp,
    change_entry,
    new_entry,
    same_content,
    set_lock,
    version_conflict,
)
from skm.modules.settings.domain.history import ChangeKind, HistoryRecord, history_record
from skm.modules.settings.domain.write_rules import (
    Problem,
    ValueChecks,
    WriteContext,
    WriteRequest,
    check_write,
    collect_write_problems,
    required_permissions,
)
from skm.platform.config import keys as engine_keys
from skm.platform.config.keys import (
    MISSING,
    SECRET_REF_URN,
    Chain,
    Deprecation,
    KeySpec,
    Level,
    MergeStrategy,
    NarrowDirection,
    NarrowSpec,
    Reload,
    Sensitivity,
    UiHints,
    copy_json,
)
from skm.platform.config.layers import Contribution, LayerRef
from skm.platform.config.merge import KeyResolution, deep_merge, fold, narrow_value
from skm.platform.config.registry import SettingsRegistry
from skm.platform.schema.findings import SchemaIssue
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator, dialect_free, without_dialect

WORK = frozenset({Level.INSTANCE, Level.WORKSPACE, Level.PROJECT, Level.PLAN, Level.RUN})
SCOPES = {kind: ScopeId(uuid4()) for kind in ScopeKind}
ACTOR = PrincipalId(UUID(int=7))
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
ALL_RIGHTS = frozenset({"config.write", "config.write_shared", "config.lock", "hook.manage"})
SECRET = "plain-secret-value-123"


# ---------------------------------------------------------------------------------------------------------
# engine fixtures


@cache
def free_registry() -> Any:
    """The packaged schemas without dialect markers, copied once (as the settings registry does)."""
    return dialect_free({}, SchemaRegistry.load_default().registry)[1]


def validator(schema: object) -> SchemaValidator:
    plain = cast("Mapping[str, JsonValue]", schema)
    return SchemaValidator(without_dialect(plain), free_registry(), dialect_free_inputs=True)


def _without_required(schema: object) -> object:
    if isinstance(schema, Mapping):
        return {
            name: _without_required(item)
            for name, item in cast("Mapping[str, object]", schema).items()
            if name != "required"
        }
    if isinstance(schema, list):
        return [_without_required(item) for item in cast("list[object]", schema)]
    return schema


class EngineChecks:
    """``ValueChecks`` over the real engine, as the application builds it for one key."""

    def __init__(self, spec: KeySpec) -> None:
        schema = cast("Mapping[str, JsonValue]", copy_json(spec.value_schema, "schema"))
        self.spec = spec
        self.full = validator(schema)
        self.partial = validator(_without_required(schema))
        self.items = validator(schema.get("items") or {})

    def schema_issues(self, value: JsonValue, *, partial: bool = False) -> Sequence[SchemaIssue]:
        return (self.partial if partial else self.full).issues(value)

    def item_issues(self, item: JsonValue) -> Sequence[SchemaIssue]:
        return self.items.issues(item)

    def deep_merge(self, base: JsonValue, overlay: JsonValue) -> JsonValue:
        return deep_merge(cast("Mapping[str, JsonValue]", base), cast("Mapping[str, JsonValue]", overlay))

    def narrow_value(self, current: JsonValue, candidate: JsonValue) -> JsonValue:
        return narrow_value(self.spec, current, candidate)


def key_spec(
    key: str = "demo.value",
    *,
    schema: Mapping[str, Any] | None = None,
    merge: MergeStrategy = MergeStrategy.REPLACE,
    levels: frozenset[Level] = WORK,
    default: object = MISSING,
    lockable: bool = True,
    confirm: bool = False,
    sensitivity: Sensitivity = Sensitivity.PUBLIC,
    write_permission: str | None = None,
    deprecated: Deprecation | None = None,
    narrow: NarrowSpec | None = None,
    chain: Chain = Chain.WORK,
) -> KeySpec:
    return KeySpec(
        key=key,
        section=key.split(".")[0],
        owner="test",
        value_schema=schema or {"type": "integer"},
        default=cast("JsonValue", default),
        description="",
        chain=chain,
        levels=levels,
        merge=merge,
        reload=Reload.LIVE,
        override=False,
        sensitivity=sensitivity,
        portable=True,
        lockable=lockable,
        nullable=default is MISSING,
        pack=True,
        confirm=confirm,
        path=False,
        write_permission=write_permission,
        narrow=narrow,
        validators=(),
        deprecated=deprecated,
        ui=UiHints("g", 1, "text"),
    )


def layer(level: Level) -> LayerRef:
    if level is Level.DEFAULT:
        return LayerRef(level)
    if level is Level.PACK:
        return LayerRef(level, pack_id="core")
    return LayerRef(level, SCOPES[ScopeKind(level.value)], level.value)


def contribution(level: Level, value: JsonValue, *, locked: bool = False) -> Contribution:
    return Contribution(layer(level), "default" if level is Level.DEFAULT else "set", value, locked=locked)


def farther(spec: KeySpec, *items: Contribution) -> KeyResolution:
    """Resolution of the farther levels: the default (when the key has one) and ``items``."""
    default = (
        () if spec.default is MISSING else (contribution(Level.DEFAULT, cast("JsonValue", spec.default)),)
    )
    return fold(spec, (*default, *items))


def scope(kind: ScopeKind) -> ScopeRef:
    return ScopeRef(kind, SCOPES[kind])


def entry(
    kind: ScopeKind = ScopeKind.PROJECT,
    key: str = "demo.value",
    value: JsonValue | None = 1,
    *,
    op: EntryOp = EntryOp.SET,
    locked: bool = False,
    version: int = 1,
) -> ConfigEntry:
    made = new_entry(
        entry_id=ConfigEntryId(uuid4()),
        scope=scope(kind),
        key=key,
        op=op,
        value=value,
        locked=locked,
        reason="",
        actor=ACTOR,
        now=NOW,
    )
    return replace(made, row_version=version)


def request(
    kind: ScopeKind = ScopeKind.PROJECT,
    value: JsonValue | None = 1,
    *,
    key: str = "demo.value",
    op: EntryOp | None = EntryOp.SET,
    locked: bool | None = None,
    expected: int | None = None,
    confirmed: bool = False,
    action: write_rules.WriteAction = "write",
) -> WriteRequest:
    if action != "write":
        op, value = None, None
    return WriteRequest(scope(kind), key, op, value, locked, expected, confirmed, action)


def context(
    spec: KeySpec | None,
    *,
    existing: ConfigEntry | None = None,
    resolution: KeyResolution | None = None,
    granted: frozenset[str] = ALL_RIGHTS,
    checks: ValueChecks | None = None,
    refused: Mapping[str, str] | None = None,
) -> WriteContext:
    if spec is None:
        return WriteContext(None, existing, resolution, granted, checks, refused=refused or {})
    return WriteContext(
        spec,
        existing,
        resolution if resolution is not None else farther(spec),
        granted,
        checks if checks is not None else EngineChecks(spec),
        refused=refused or {},
    )


def fails(req: WriteRequest, ctx: WriteContext) -> SkmError:
    with pytest.raises(SkmError) as caught:
        check_write(req, ctx)
    return caught.value


def rules(req: WriteRequest, ctx: WriteContext) -> list[str]:
    return [problem.rule for problem in collect_write_problems(req, ctx)]


INT = key_spec()


# ---------------------------------------------------------------------------------------------------------
# vocabulary and permissions


def test_level_vocabulary_matches_the_engine() -> None:
    assert {level.value for level in engine_keys.STORED_LEVELS} == write_rules.STORED_LEVELS
    assert {level.value for level in engine_keys.SHARED_LEVELS} == write_rules.SHARED_LEVELS
    assert {level.value for level in engine_keys.LOCK_LEVELS} == write_rules.LOCK_LEVELS
    assert {level.value for level in engine_keys.CHAIN_OPEN_LEVELS} == write_rules.CHAIN_OPEN_LEVELS
    assert {"default", "pack"} == {level.value for level in engine_keys.BASE_LEVELS}


@pytest.mark.parametrize(
    ("level", "lock_change", "permission", "expected"),
    [
        (Level.PROJECT, False, None, {"config.write"}),
        (Level.PLAN, False, None, {"config.write"}),
        (Level.RUN, False, None, {"config.write"}),
        (Level.INSTANCE, False, None, {"config.write_shared"}),
        (Level.WORKSPACE, False, None, {"config.write_shared"}),
        (Level.HOST, False, None, {"config.write_shared"}),
        (Level.INSTANCE, True, None, {"config.write_shared", "config.lock"}),
        (Level.PROJECT, True, None, {"config.write", "config.lock"}),
        (Level.PROJECT, False, "hook.manage", {"config.write", "hook.manage"}),
        (Level.WORKSPACE, True, "hook.manage", {"config.write_shared", "config.lock", "hook.manage"}),
    ],
)
def test_required_permissions_need_every_right_of_the_set(
    level: Level, lock_change: bool, permission: str | None, expected: set[str]
) -> None:
    spec = key_spec(write_permission=permission)
    assert required_permissions(level, spec, lock_change=lock_change) == expected
    assert required_permissions(ScopeKind(level.value), spec, lock_change=lock_change) == expected


def test_required_permissions_for_unknown_key_and_bad_level() -> None:
    assert required_permissions("project", None, lock_change=False) == {"config.write"}
    with pytest.raises(ValueError, match="stored level"):
        required_permissions("invocation", None, lock_change=False)
    with pytest.raises(ValueError, match="stored level"):
        required_permissions("default", INT, lock_change=False)


@cache
def owner_registry() -> SettingsRegistry:
    inputs = run_path(str(Path(__file__).parents[2] / "platform/config/test_registry_all_sections.py"))
    return cast("SettingsRegistry", inputs["real_registry"]())


def test_real_hook_subscriptions_key_adds_hook_manage() -> None:
    spec = owner_registry().spec("hooks.subscriptions")
    assert spec.write_permission == "hook.manage"
    needed = required_permissions(Level.WORKSPACE, spec, lock_change=False)
    assert needed == {"config.write_shared", "hook.manage"}


# ---------------------------------------------------------------------------------------------------------
# R1-R4


def test_r1_unknown_key_is_reported_before_any_other_rule() -> None:
    error = fails(request(ScopeKind.HOST, confirmed=False, expected=5), context(None))
    assert isinstance(error, ValidationFailed)
    assert error.code is ErrorCode.CONFIG_UNKNOWN_KEY
    assert dict(error.details) == {"key": "demo.value"}
    assert rules(request(ScopeKind.HOST, expected=5), context(None)) == ["R1"]


def test_r2_deprecated_key_refuses_writes_but_not_removal() -> None:
    spec = key_spec(deprecated=Deprecation(since="2.1", replacement="demo.other"))
    error = fails(request(), context(spec))
    assert error.code is ErrorCode.CONFIG_INVALID
    assert dict(error.details) == {"key": "demo.value", "reason": "deprecated", "replacement": "demo.other"}
    check_write(request(action="remove"), context(spec, existing=entry()))
    check_write(request(), context(INT))


def test_r3_level_must_be_declared_by_the_key() -> None:
    spec = key_spec(levels=frozenset({Level.INSTANCE, Level.WORKSPACE}))
    error = fails(request(ScopeKind.PROJECT), context(spec))
    assert error.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    assert dict(error.details) == {
        "key": "demo.value",
        "level": "project",
        "allowed": ["instance", "workspace"],
    }
    check_write(request(ScopeKind.WORKSPACE), context(spec))
    # R3 also guards removal and lock of an entry stored at a level the key does not allow
    assert (
        fails(request(action="remove"), context(spec, existing=entry())).code
        is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    )


def test_r1_r3_order_unknown_key_before_scope() -> None:
    spec = key_spec(levels=frozenset({Level.INSTANCE}))
    assert rules(request(ScopeKind.RUN), context(spec)) == ["R3"]
    assert rules(request(ScopeKind.RUN), context(None)) == ["R1"]


ARRAY = key_spec(schema={"type": "array", "items": {"type": "string"}})


@pytest.mark.parametrize(
    ("spec", "op", "value", "allowed"),
    [
        (ARRAY, EntryOp.APPEND, ["x"], True),
        (key_spec(schema={"type": "array"}, merge=MergeStrategy.APPEND_UNIQUE), EntryOp.APPEND, ["x"], False),
        (key_spec(schema={"type": "array"}, merge=MergeStrategy.UNION), EntryOp.APPEND, ["x"], False),
        (INT, EntryOp.APPEND, [1], False),
        (INT, EntryOp.UNSET, None, True),
        (key_spec(schema={"type": "object"}, merge=MergeStrategy.DEEP_MERGE), EntryOp.UNSET, None, True),
        (key_spec(schema={"type": "array"}, merge=MergeStrategy.UNION), EntryOp.UNSET, None, False),
        (
            key_spec(merge=MergeStrategy.NARROW, narrow=NarrowSpec(NarrowDirection.MIN), default=3),
            EntryOp.UNSET,
            None,
            False,
        ),
    ],
)
def test_r4_operation_must_fit_the_merge_strategy(
    spec: KeySpec, op: EntryOp, value: JsonValue | None, allowed: bool
) -> None:
    req = request(value=value, op=op)
    if allowed:
        check_write(req, context(spec))
        return
    error = fails(req, context(spec))
    assert error.code is ErrorCode.CONFIG_OP_NOT_ALLOWED
    assert dict(error.details) == {"key": "demo.value", "op": op.value, "merge": spec.merge.value}
    assert "R5" not in rules(req, context(spec))  # a refused operation is not value-checked as well


# ---------------------------------------------------------------------------------------------------------
# R5, R6


def test_r5_set_value_is_validated_by_the_key_schema() -> None:
    spec = key_spec(schema={"type": "integer", "minimum": 1})
    error = fails(request(value=0), context(spec))
    assert error.code is ErrorCode.CONFIG_INVALID
    issues = cast("list[dict[str, Any]]", error.details["issues"])
    assert [(issue["pointer"], issue["code"]) for issue in issues] == [("", "minimum")]
    check_write(request(value=1), context(spec))
    assert fails(request(value="1"), context(spec)).code is ErrorCode.CONFIG_INVALID


def test_r5_set_needs_a_value_and_unset_none() -> None:
    error = fails(request(value=None), context(INT))
    assert cast("list[dict[str, Any]]", error.details["issues"])[0]["code"] == "required"
    check_write(request(value=None, op=EntryOp.UNSET), context(INT))
    with pytest.raises(ValueError, match="unset"):
        request(value=1, op=EntryOp.UNSET)


def test_r5_append_takes_an_array_of_valid_items() -> None:
    check_write(request(value=["a", "b"], op=EntryOp.APPEND), context(ARRAY))
    error = fails(request(value=["a", 2, "c", 4], op=EntryOp.APPEND), context(ARRAY))
    issues = cast("list[dict[str, Any]]", error.details["issues"])
    assert [issue["pointer"] for issue in issues] == ["/1", "/3"]
    problems = collect_write_problems(request(value=["a", 2, "c", 4], op=EntryOp.APPEND), context(ARRAY))
    assert [(p.rule, p.pointer) for p in problems] == [("R5", "/1"), ("R5", "/3")]
    assert fails(request(value="a", op=EntryOp.APPEND), context(ARRAY)).code is ErrorCode.CONFIG_INVALID


RECORD = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "limit"],
    "properties": {
        "mode": {"type": "string", "enum": ["strict", "lenient"]},
        "limit": {"type": "integer", "minimum": 1},
        "tags": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
}
DEEP = key_spec(schema=RECORD, merge=MergeStrategy.DEEP_MERGE, default={"mode": "strict", "limit": 3})


def test_r5_deep_merge_contribution_is_partial_and_the_merge_is_complete() -> None:
    # (a) a partial map without the required fields is a valid contribution
    check_write(request(value={"limit": 5}), context(DEEP))
    check_write(request(value={"tags": {"a": "x", "b": {"$unset": True}}}), context(DEEP))
    # (a) the partial schema still checks types and unknown fields
    assert fails(request(value={"limit": 0}), context(DEEP)).code is ErrorCode.CONFIG_INVALID
    assert fails(request(value={"other": 1}), context(DEEP)).code is ErrorCode.CONFIG_INVALID
    # (b) removing a required field from the merged result is invalid
    error = fails(request(value={"mode": {"$unset": True}}), context(DEEP))
    issues = cast("list[dict[str, Any]]", error.details["issues"])
    assert [issue["code"] for issue in issues] == ["required"]
    # without farther contributions (no default) the partial map alone must be complete
    bare = key_spec(schema=RECORD, merge=MergeStrategy.DEEP_MERGE)
    assert fails(request(value={"limit": 5}), context(bare)).code is ErrorCode.CONFIG_INVALID
    check_write(request(value={"limit": 5, "mode": "lenient"}), context(bare))


def test_r5_unset_marker_only_in_deep_merge() -> None:
    free = key_spec(schema={"type": "object"})
    error = fails(request(value={"a": {"b": {"$unset": True}}}), context(free))
    issues = cast("list[dict[str, Any]]", error.details["issues"])
    assert issues == [{"pointer": "/a/b", "code": "unset_marker", "message": issues[0]["message"]}]
    check_write(request(value={"a": {"b": {"$unset": False}}}), context(free))


RECORDS = key_spec(schema={"type": "array", "items": {"type": "object"}})


@pytest.mark.parametrize(
    ("value", "pointer"),
    [
        ([{"$unset": True}], "/0"),
        ([{"a": 1}, {"a": {"$unset": True}}], "/1/a"),
        ([{"a": [{"b": {"$unset": True}}]}], "/0/a/0/b"),
    ],
)
def test_r5_unset_marker_is_refused_in_append_items(value: JsonValue, pointer: str) -> None:
    req = request(value=value, op=EntryOp.APPEND)
    error = fails(req, context(RECORDS))
    assert error.code is ErrorCode.CONFIG_INVALID
    issues = cast("list[dict[str, Any]]", error.details["issues"])
    assert [(issue["pointer"], issue["code"]) for issue in issues] == [(pointer, "unset_marker")]
    problems = collect_write_problems(req, context(RECORDS))
    assert [(p.rule, p.code, p.pointer) for p in problems] == [("R5", "CONFIG_INVALID", pointer)]


def test_r5_plain_objects_in_append_items_stay_valid() -> None:
    values: tuple[JsonValue, ...] = ([{"a": 1}], [{"$unset": False}], [{"$unset": True, "b": 1}], [])
    for value in values:
        check_write(request(value=value, op=EntryOp.APPEND), context(RECORDS))


@contextmanager
def int_text_limit(digits: int) -> Iterator[None]:
    """The interpreter's int-to-text limit for one block (0: off); product code never sets it."""
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(digits)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(before)


LIMITS = (640, 4300, 0)  # the lowest limit an interpreter allows, the default, off
W641 = 10**640  # 641 digits: wider than the lowest limit
W5001 = 10**5000 + 7  # 5001 digits: wider than the default limit
# exactly VALUE_MAX_BYTES of canonical JSON: 65536 digits, "-" and 65535, {"n":} and 65530, a string
EDGES: tuple[JsonValue, ...] = (
    10**VALUE_MAX_BYTES - 1,
    -(10 ** (VALUE_MAX_BYTES - 1) - 1),
    {"n": 10 ** (VALUE_MAX_BYTES - 6) - 1},
    "x" * (VALUE_MAX_BYTES - 2),
)
WIDE: tuple[JsonValue, ...] = (W641, -W641, W5001, {"n": W5001}, [W641, -W5001], {"a": {"b": [W641]}}, *EDGES)
HUGE = 10**1_000_000  # far beyond the bound: never written out
# one byte over each edge, and the huge integer
OVER: tuple[JsonValue, ...] = (
    10**VALUE_MAX_BYTES,
    -(10 ** (VALUE_MAX_BYTES - 1)),
    {"n": 10 ** (VALUE_MAX_BYTES - 6)},
    "x" * (VALUE_MAX_BYTES - 1),
    [HUGE],
)
FREE = key_spec(schema={"type": ["string", "integer", "array", "object"]})
INTS = key_spec(schema={"type": "array", "items": {"type": "integer"}})


def test_r5_value_size_is_bounded() -> None:
    text = key_spec(schema={"type": "string"})
    check_write(request(value="x" * (VALUE_MAX_BYTES - 2)), context(text))  # with its quotes: 64 KiB
    check_write(request(value="ä" * ((VALUE_MAX_BYTES - 2) // 2)), context(text))  # UTF-8 bytes count
    for value in ("x" * (VALUE_MAX_BYTES - 1), "ä" * ((VALUE_MAX_BYTES - 2) // 2) + "x", "x" * 70000):
        error = fails(request(value=value), context(text))
        issues = cast("list[dict[str, Any]]", error.details["issues"])
        assert [(issue["pointer"], issue["code"]) for issue in issues] == [("", "maxSize")]


@pytest.mark.parametrize("limit", LIMITS)
def test_r5_integers_of_any_width_within_the_size_are_valid(limit: int) -> None:
    """641 and 5001 digits, in a mapping or not, up to 64 KiB: valid whatever the int-to-text limit."""
    with int_text_limit(limit):
        for value in WIDE:
            check_write(request(ScopeKind.WORKSPACE, value=value), context(FREE))
            assert entry(ScopeKind.WORKSPACE, value=value).value == value
        for value in (W641, -W5001, 10**VALUE_MAX_BYTES - 1):
            check_write(request(value=value), context(INT))
        check_write(request(value=[W5001, -W641], op=EntryOp.APPEND), context(INTS))
        assert collect_write_problems(request(value={"limit": W5001}), context(DEEP)) == ()
        check_write(request(value=["ä", "\U0001f600", {"\U0001f600": 1}]), context(FREE))


@pytest.mark.parametrize("limit", LIMITS)
@pytest.mark.parametrize(
    ("spec", "op", "value", "pointer", "code"),
    [
        (FREE, EntryOp.SET, "\ud800", "", "lone_surrogate"),
        (FREE, EntryOp.SET, {"\udc00": 1}, "", "lone_surrogate"),
        (FREE, EntryOp.SET, {"a/b": [1, "x\udfffy"]}, "/a~1b/1", "lone_surrogate"),
        (FREE, EntryOp.SET, {"ok": {"\ud83d": "x"}}, "/ok", "lone_surrogate"),
        pytest.param(FREE, EntryOp.SET, OVER[0], "", "maxSize", id="int65537"),
        pytest.param(FREE, EntryOp.SET, OVER[1], "", "maxSize", id="negative-int65537-bytes"),
        pytest.param(FREE, EntryOp.SET, OVER[2], "", "maxSize", id="mapping-int65537-bytes"),
        pytest.param(FREE, EntryOp.SET, OVER[3], "", "maxSize", id="string65537-bytes"),
        pytest.param(INT, EntryOp.SET, HUGE, "", "maxSize", id="int1000001"),
        (ARRAY, EntryOp.APPEND, ["a", "\ud800"], "/1", "lone_surrogate"),
        (ARRAY, EntryOp.APPEND, "\ud800", "", "lone_surrogate"),  # not an array either: still R5
        pytest.param(INTS, EntryOp.APPEND, [HUGE], "", "maxSize", id="append-int1000001"),
        (DEEP, EntryOp.SET, {"tags": {"\ud800": "x"}}, "/tags", "lone_surrogate"),
        pytest.param(DEEP, EntryOp.SET, {"limit": OVER[0]}, "", "maxSize", id="deep-int65537"),
    ],
)
def test_r5_values_that_cannot_be_stored_are_problems_not_crashes(
    spec: KeySpec, op: EntryOp, value: JsonValue, pointer: str, code: str, limit: int
) -> None:
    """A parsed lone surrogate escape or a value over 64 KiB is one structured R5 finding."""
    with int_text_limit(limit):
        req = request(value=value, op=op)
        error = fails(req, context(spec))
        assert type(error) is ValidationFailed
        assert error.code is ErrorCode.CONFIG_INVALID
        issues = cast("list[dict[str, Any]]", error.details["issues"])
        assert [(issue["pointer"], issue["code"]) for issue in issues] == [(pointer, code)]
        problems = collect_write_problems(req, context(spec))
        assert [(p.rule, p.code, p.pointer, dict(p.details)) for p in problems] == [
            ("R5", "CONFIG_INVALID", pointer, {"code": code})
        ]
        rendered = [[p.message, p.pointer, dict(p.details)] for p in problems]
        json.dumps(rendered, ensure_ascii=False).encode("utf-8")  # the problem itself is UTF-8 JSON


TEXTS = key_spec(schema={"type": "object", "additionalProperties": {"type": "string"}})


BRANCHES = key_spec(schema={"anyOf": [{"type": "string"}, {"type": "integer", "maximum": 10}]})
ONE_OF = key_spec(schema={"oneOf": [{"type": "string"}, {"type": "integer", "minimum": 0}]})


@pytest.mark.parametrize("limit", LIMITS)
@pytest.mark.parametrize(
    ("spec", "op", "value", "pointer", "code"),
    [
        pytest.param(
            key_spec(schema={"type": "integer", "maximum": 10}),
            EntryOp.SET,
            W5001,
            "",
            "maximum",
            id="maximum",
        ),
        pytest.param(TEXTS, EntryOp.SET, {"a": "x", "n/m": W5001}, "/n~1m", "type", id="type-in-mapping"),
        pytest.param(ARRAY, EntryOp.APPEND, ["a", -W5001], "/1", "type", id="append-item"),
        pytest.param(DEEP, EntryOp.SET, {"limit": -W5001}, "/limit", "minimum", id="deep-merge-minimum"),
    ],
)
def test_r5_schema_finding_about_an_integer_over_the_text_limit_is_the_schema_finding(
    spec: KeySpec, op: EntryOp, value: JsonValue, pointer: str, code: str, limit: int
) -> None:
    """Whatever the int-to-text limit, the engine reports its own finding (leading digits only) and denies."""
    req = request(value=value, op=op)
    with int_text_limit(limit):
        problems = collect_write_problems(req, context(spec))
        assert [(p.rule, p.code, p.pointer, dict(p.details)) for p in problems] == [
            ("R5", "CONFIG_INVALID", pointer, {"code": code})
        ]
        rendered = json.dumps([[p.message, p.pointer, dict(p.details)] for p in problems], ensure_ascii=False)
        assert "0" * 100 not in rendered  # the message quotes the leading digits, not the value
        error = fails(req, context(spec))
        assert type(error) is ValidationFailed
        assert error.code is ErrorCode.CONFIG_INVALID
        issues = cast("list[dict[str, Any]]", error.details["issues"])
        assert [(issue["pointer"], issue["code"]) for issue in issues] == [(pointer, code)]
        assert "0" * 100 not in str(error) + repr(error.to_problem())


@pytest.mark.parametrize("limit", LIMITS)
def test_r5_wide_integer_matching_one_branch_is_valid_and_failing_all_is_denied(limit: int) -> None:
    with int_text_limit(limit):
        check_write(request(value=-W5001), context(BRANCHES))
        check_write(request(value=W5001), context(ONE_OF))
        # the branch keyword and the finding of the branch that came closest
        for spec, value, codes in (
            (BRANCHES, W5001, ["anyOf", "maximum"]),
            (ONE_OF, -W5001, ["minimum", "oneOf"]),
        ):
            req = request(value=value)
            problems = collect_write_problems(req, context(spec))
            assert [(p.rule, p.pointer, p.details["code"]) for p in problems] == [
                ("R5", "", c) for c in codes
            ]
            assert all(len(p.message) < 200 for p in problems)
            issues = cast("list[dict[str, Any]]", fails(req, context(spec)).details["issues"])
            assert [issue["code"] for issue in issues] == codes


class BrokenChecks(EngineChecks):
    @override
    def schema_issues(self, value: JsonValue, *, partial: bool = False) -> Sequence[SchemaIssue]:
        raise ValueError("engine failure")


def test_engine_errors_without_a_wide_integer_propagate() -> None:
    broken = BrokenChecks(FREE)
    values: tuple[JsonValue, ...] = (1, W641 - 1, {"n": [-(W641 - 1)]}, "x")
    for value in values:
        with pytest.raises(ValueError, match="engine failure"):
            check_write(request(value=value), context(FREE, checks=broken))
    problems = collect_write_problems(request(value={"n": [1, W641]}), context(FREE, checks=broken))
    assert [(p.rule, p.pointer, dict(p.details)) for p in problems] == [
        ("R5", "/n/1", {"code": "integer_text"})
    ]


@pytest.mark.parametrize(
    "value",
    [
        "secret://env/\ud800" + SECRET,
        {"token\ud800": SECRET},
        pytest.param("secret://env/" + SECRET + "x" * VALUE_MAX_BYTES, id="string-over-size"),
        pytest.param(OVER[0], id="int65537"),
    ],
)
def test_r5_secret_value_that_cannot_be_stored_is_not_echoed(value: JsonValue) -> None:
    req = request(value=value, key="demo.token")
    error = fails(req, context(SECRET_KEY))
    assert error.code is ErrorCode.CONFIG_INVALID
    issues = cast("list[dict[str, Any]]", error.details["issues"])
    assert [issue["pointer"] for issue in issues] == [""]
    problems = collect_write_problems(req, context(SECRET_KEY))
    assert [problem.rule for problem in problems] == ["R5"]  # R6 would only restate it
    rendered = repr(problems) + str(error) + repr(error.to_problem())
    assert SECRET not in rendered
    assert "token\\ud800" not in rendered
    assert "\ud800" not in rendered
    assert "\\ud800" not in rendered


def test_wide_secret_integer_within_the_size_is_r6() -> None:
    req = request(value=W5001, key="demo.token")
    assert rules(req, context(SECRET_KEY)) == ["R6"]


SECRET_KEY = key_spec(
    "demo.token", schema={"$ref": SECRET_REF_URN}, sensitivity=Sensitivity.SECRET, levels=frozenset(WORK)
)


@pytest.mark.parametrize("value", [SECRET, "secret://nope/" + SECRET, 12345, {"token": SECRET}])
def test_r6_secret_keys_take_a_reference_and_never_echo_the_value(value: JsonValue) -> None:
    req = request(value=value, key="demo.token")
    error = fails(req, context(SECRET_KEY))
    assert error.code is ErrorCode.CONFIG_INVALID
    assert dict(error.details) == {"key": "demo.token", "reason": "secret_ref_required"}
    problems = collect_write_problems(req, context(SECRET_KEY))
    assert [problem.rule for problem in problems] == ["R6"]
    rendered = repr(problems) + str(error) + repr(error.to_problem())
    assert SECRET not in rendered
    assert "12345" not in rendered


def test_r6_secret_reference_is_accepted() -> None:
    check_write(request(value="secret://env/SKM_TOKEN", key="demo.token"), context(SECRET_KEY))
    check_write(request(value=None, op=EntryOp.UNSET, key="demo.token"), context(SECRET_KEY))


# ---------------------------------------------------------------------------------------------------------
# R7, R8


def test_r7_lock_above_refuses_every_value_write() -> None:
    above = farther(INT, contribution(Level.INSTANCE, 4, locked=True))
    assert above.locked_by is not None
    for req in (request(ScopeKind.WORKSPACE), request(value=None, op=EntryOp.UNSET)):
        error = fails(req, context(INT, resolution=above))
        assert isinstance(error, PreconditionFailed)
        assert error.code is ErrorCode.CONFIG_LOCKED
        assert dict(error.details) == {
            "key": "demo.value",
            "locked_by": {"level": "instance", "scope_id": str(SCOPES[ScopeKind.INSTANCE])},
        }
    # removing an entry below the lock does not widen anything (R7 is not a removal rule)
    check_write(request(action="remove"), context(INT, existing=entry(), resolution=above))
    # an unlocked farther value is no lock
    check_write(request(), context(INT, resolution=farther(INT, contribution(Level.INSTANCE, 4))))


ROUNDS = key_spec(
    "demo.rounds", merge=MergeStrategy.NARROW, narrow=NarrowSpec(NarrowDirection.MIN), default=3
)


@pytest.mark.parametrize(
    ("farther_items", "kind", "value", "ok"),
    [
        # a farther explicit level is a ceiling for every level of the write
        ((contribution(Level.INSTANCE, 4),), ScopeKind.WORKSPACE, 5, False),
        ((contribution(Level.INSTANCE, 4),), ScopeKind.WORKSPACE, 4, True),
        ((contribution(Level.INSTANCE, 4),), ScopeKind.PROJECT, 2, True),
        ((contribution(Level.INSTANCE, 4), contribution(Level.WORKSPACE, 2)), ScopeKind.PROJECT, 3, False),
        # no farther explicit contribution: chain-open levels start the chain above the default
        ((), ScopeKind.INSTANCE, 10, True),
        ((), ScopeKind.WORKSPACE, 10, True),
        # ... project/plan/run only narrow the base value
        ((), ScopeKind.PROJECT, 10, False),
        ((), ScopeKind.RUN, 4, False),
        ((), ScopeKind.PLAN, 3, True),
        ((), ScopeKind.PROJECT, 1, True),
    ],
)
def test_r8_narrow_ceiling(
    farther_items: tuple[Contribution, ...], kind: ScopeKind, value: int, ok: bool
) -> None:
    resolution = farther(ROUNDS, *farther_items)
    req = request(kind, value, key="demo.rounds")
    if ok:
        check_write(req, context(ROUNDS, resolution=resolution))
        return
    error = fails(req, context(ROUNDS, resolution=resolution))
    assert error.code is ErrorCode.CONFIG_NARROWING_VIOLATION
    winner = cast("LayerRef", resolution.winner)
    assert dict(error.details) == {
        "key": "demo.rounds",
        "ceiling": resolution.value,
        "ceiling_from": winner.to_json(),
    }


def test_r8_agrees_with_the_engine_fold() -> None:
    """A write accepted by R8 is applied by fold at that level; a refused one would be ignored."""
    for items in ((), (contribution(Level.INSTANCE, 4),)):
        resolution = farther(ROUNDS, *items)
        for kind in (ScopeKind.WORKSPACE, ScopeKind.PROJECT):
            for value in range(1, 8):
                accepted = not collect_write_problems(
                    request(kind, value, key="demo.rounds"), context(ROUNDS, resolution=resolution)
                )
                level = Level(kind.value)
                folded = farther(ROUNDS, *items, contribution(level, value))
                applied = folded.trace[-1].status != "ignored"
                assert accepted == applied, (items, kind, value)


def test_r8_without_a_base_value_has_no_ceiling() -> None:
    bare = key_spec("demo.rounds", merge=MergeStrategy.NARROW, narrow=NarrowSpec(NarrowDirection.MIN))
    check_write(request(ScopeKind.RUN, 100, key="demo.rounds"), context(bare))


INTERSECT = key_spec(
    "demo.tools",
    schema={"type": "array", "items": {"type": "string"}},
    merge=MergeStrategy.NARROW,
    narrow=NarrowSpec(NarrowDirection.INTERSECT),
    default=["a", "b", "c"],
)
LEVELS = ("advisor", "owner")
ENUM_MAP = key_spec(
    "demo.roles",
    schema={"type": "object", "additionalProperties": {"type": "string", "enum": list(LEVELS)}},
    merge=MergeStrategy.NARROW,
    narrow=NarrowSpec(order=LEVELS),
    default={"a": "advisor", "b": "owner"},
)


def test_r8_intersect_compares_sets() -> None:
    def ok(value: JsonValue) -> bool:
        return not collect_write_problems(request(value=value, key="demo.tools"), context(INTERSECT))

    assert ok(["c", "a"])  # order does not widen
    assert ok(["a", "a"])
    assert ok([])
    assert not ok(["a", "z"])


def number_set(default: JsonValue, items: Mapping[str, Any] | None = None) -> KeySpec:
    return key_spec(
        "demo.numbers",
        schema={"type": "array", "items": items if items is not None else {"type": "number"}},
        merge=MergeStrategy.NARROW,
        narrow=NarrowSpec(NarrowDirection.INTERSECT),
        default=default,
    )


@pytest.mark.parametrize(
    ("ceiling", "value", "ok"),
    [
        ([1], [1.0], True),  # the engine treats 1 and 1.0 as one element
        ([1.0], [1], True),
        ([1, 2.5], [2.5, 1.0], True),  # order does not widen
        ([1, 2], [1.0, 1, 1.0], True),  # duplicates do not widen
        ([1], [1, 2], False),  # a new element widens
        ([1], [2.0], False),
    ],
)
def test_r8_intersect_compares_numbers_by_value(ceiling: JsonValue, value: JsonValue, ok: bool) -> None:
    spec = number_set(ceiling)
    req = request(value=value, key="demo.numbers")
    found = rules(req, context(spec))
    assert found == ([] if ok else ["R8"])
    # R8 agrees with fold: an accepted project contribution is applied, a refused one is ignored
    folded = farther(spec, contribution(Level.PROJECT, value))
    assert (folded.trace[-1].status != "ignored") is ok


def test_r8_intersect_nested_items_compare_by_value_and_keep_order() -> None:
    spec = number_set([[1, 2], {"a": 1}], items={"type": ["array", "object"]})

    def found(value: JsonValue) -> list[str]:
        return rules(request(value=value, key="demo.numbers"), context(spec))

    assert found([[1.0, 2.0], {"a": 1.0}]) == []
    assert found([{"a": 1.0}]) == []
    assert found([[2, 1]]) == ["R8"]  # nested arrays keep their order, as in the engine
    assert found([{"a": True}]) == ["R8"]


def test_r8_intersect_bool_is_not_a_number() -> None:
    assert rules(request(value=[True], key="demo.numbers"), context(number_set([1]))) == ["R5"]  # schema
    untyped = number_set([1], items={})
    assert rules(request(value=[True], key="demo.numbers"), context(untyped)) == ["R8"]  # engine
    assert rules(request(value=[False], key="demo.numbers"), context(number_set([0], items={}))) == ["R8"]


def test_r8_map_narrow_refuses_a_wider_entry() -> None:
    def problems(value: JsonValue) -> list[str]:
        return rules(request(value=value, key="demo.roles"), context(ENUM_MAP))

    assert problems({"a": "owner", "b": "owner"}) == []  # stricter
    assert problems({"a": "advisor", "b": "owner", "c": "advisor"}) == []  # a new key narrows nothing above
    assert problems({"a": "advisor", "b": "advisor"}) == ["R8"]  # b widens owner → advisor
    assert problems({"a": "advisor"}) == ["R8"]  # dropping b would lift its restriction from this value


class _Incomparable(EngineChecks):
    @override
    def narrow_value(self, current: JsonValue, candidate: JsonValue) -> JsonValue:
        raise ValueError("cannot compare")


def test_r8_fails_closed_when_values_cannot_be_compared() -> None:
    resolution = farther(ROUNDS, contribution(Level.INSTANCE, 4))
    ctx = context(ROUNDS, resolution=resolution, checks=_Incomparable(ROUNDS))
    assert fails(request(value=1, key="demo.rounds"), ctx).code is ErrorCode.CONFIG_NARROWING_VIOLATION


# ---------------------------------------------------------------------------------------------------------
# R9-R13, R16


@pytest.mark.parametrize(
    ("kind", "lockable", "ok"),
    [
        (ScopeKind.INSTANCE, True, True),
        (ScopeKind.WORKSPACE, True, True),
        (ScopeKind.PROJECT, True, False),
        (ScopeKind.RUN, True, False),
        (ScopeKind.INSTANCE, False, False),
    ],
)
def test_r9_lock_flag_only_on_instance_and_workspace_of_lockable_keys(
    kind: ScopeKind, lockable: bool, ok: bool
) -> None:
    spec = key_spec(lockable=lockable)
    cases = [
        (request(kind, locked=True), None),
        (
            request(kind, action="lock"),
            entry(kind) if kind in (ScopeKind.INSTANCE, ScopeKind.WORKSPACE) else None,
        ),
    ]
    for req, existing in cases:
        found = list(collect_write_problems(req, context(spec, existing=existing)))
        lock_problems = [problem for problem in found if problem.rule == "R9"]
        assert bool(lock_problems) != ok
        if lock_problems:
            assert lock_problems[0].details == {"key": "demo.value", "reason": "lock_level"}
            assert lock_problems[0].code == "CONFIG_SCOPE_NOT_ALLOWED"
    # unlocking is always possible where the entry is
    assert "R9" not in rules(request(kind, action="unlock"), context(spec, existing=entry(kind)))


def test_r10_confirmation_for_every_action_even_without_an_entry() -> None:
    spec = key_spec(confirm=True)
    for req, existing in (
        (request(expected=0), None),
        (request(action="remove"), entry()),
        (request(ScopeKind.WORKSPACE, action="lock"), entry(ScopeKind.WORKSPACE)),
        (request(ScopeKind.WORKSPACE, action="unlock"), entry(ScopeKind.WORKSPACE, locked=True)),
    ):
        error = fails(req, context(spec, existing=existing))
        assert isinstance(error, PreconditionFailed)
        assert error.code is ErrorCode.CONFIRMATION_REQUIRED
        assert dict(error.details) == {"key": "demo.value", "reasons": ["key_requires_confirmation"]}
        check_write(replace(req, confirmed=True), context(spec, existing=existing))


@pytest.mark.parametrize(
    ("expected", "existing_version", "actual"),
    [
        (0, 1, 1),  # "there must be no entry", but there is one
        (3, None, 0),  # a version of an entry that is gone
        (1, 2, 2),  # stale read
        (2, 1, 1),
    ],
)
def test_r11_version_conflict(expected: int, existing_version: int | None, actual: int) -> None:
    existing = None if existing_version is None else entry(version=existing_version)
    error = fails(request(expected=expected), context(INT, existing=existing))
    assert isinstance(error, Conflict)
    assert error.code is ErrorCode.VERSION_CONFLICT
    assert dict(error.details) == {"expected": expected, "actual": actual}


def test_r11_matching_or_absent_expectation_passes() -> None:
    check_write(request(expected=None), context(INT, existing=entry(version=4)))
    check_write(request(expected=4), context(INT, existing=entry(version=4)))
    check_write(request(expected=0), context(INT))
    check_write(request(expected=None), context(INT))


def test_r11_concurrent_writers_from_the_same_read() -> None:
    """Two writers read version 1; after the first commits version 2 the second's re-check conflicts,
    and two creators guarded by expected=0 cannot both create the entry."""
    first = entry(version=1)
    committed = change_entry(first, op=EntryOp.SET, value=2, reason="", actor=ACTOR, now=NOW)
    check_write(request(value=3, expected=1), context(INT, existing=first))
    error = fails(request(value=3, expected=1), context(INT, existing=committed))
    assert dict(error.details) == {"expected": 1, "actual": 2}
    created = entry(version=1)
    check_write(request(expected=0), context(INT))
    assert dict(fails(request(expected=0), context(INT, existing=created)).details) == {
        "expected": 0,
        "actual": 1,
    }
    assert dict(version_conflict(1, 0).details) == {"expected": 1, "actual": 0}


@pytest.mark.parametrize("action", ["remove", "lock", "unlock"])
def test_r12_entry_must_exist(action: write_rules.WriteAction) -> None:
    error = fails(request(ScopeKind.WORKSPACE, action=action), context(INT))
    assert isinstance(error, NotFound)
    assert dict(error.details) == {
        "kind": "config_entry",
        "scope_id": str(SCOPES[ScopeKind.WORKSPACE]),
        "key": "demo.value",
    }
    # expected=0 says "no entry" and still does not make a removal of nothing valid
    assert rules(request(ScopeKind.WORKSPACE, action=action, expected=0), context(INT)) == ["R12"]
    assert rules(request(ScopeKind.WORKSPACE, action=action, expected=2), context(INT)) == ["R11", "R12"]


NO_LOCK = ALL_RIGHTS - {"config.lock"}


@pytest.mark.parametrize(
    ("req", "existing", "needs_lock"),
    [
        (request(ScopeKind.WORKSPACE, locked=True), None, True),  # create locked
        (request(ScopeKind.WORKSPACE, locked=False), entry(ScopeKind.WORKSPACE, locked=True), True),
        (request(ScopeKind.WORKSPACE, locked=True), entry(ScopeKind.WORKSPACE, locked=False), True),
        (request(ScopeKind.WORKSPACE, locked=None), entry(ScopeKind.WORKSPACE, locked=True), False),
        (request(ScopeKind.WORKSPACE, locked=True), entry(ScopeKind.WORKSPACE, locked=True), False),
        (request(ScopeKind.WORKSPACE, locked=False), None, False),
        (request(ScopeKind.WORKSPACE, action="remove"), entry(ScopeKind.WORKSPACE, locked=True), True),
        (request(ScopeKind.WORKSPACE, action="remove"), entry(ScopeKind.WORKSPACE), False),
        (request(ScopeKind.WORKSPACE, action="lock"), entry(ScopeKind.WORKSPACE), True),
        (request(ScopeKind.WORKSPACE, action="unlock"), entry(ScopeKind.WORKSPACE, locked=True), True),
    ],
)
def test_r13_lock_changes_and_locked_removal_need_config_lock(
    req: WriteRequest, existing: ConfigEntry | None, needs_lock: bool
) -> None:
    if needs_lock:
        error = fails(req, context(INT, existing=existing, granted=NO_LOCK))
        assert isinstance(error, Forbidden)
        assert dict(error.details) == {"permission": "config.lock"}
    else:
        check_write(req, context(INT, existing=existing, granted=NO_LOCK))
    check_write(req, context(INT, existing=existing, granted=ALL_RIGHTS))


@pytest.mark.parametrize("action", ["write", "remove", "lock", "unlock"])
def test_r16_write_permission_of_the_key(action: write_rules.WriteAction) -> None:
    spec = key_spec(write_permission="hook.manage")
    existing = entry(ScopeKind.WORKSPACE, locked=action == "unlock")
    req = request(ScopeKind.WORKSPACE, action=action)
    error = fails(req, context(spec, existing=existing, granted=ALL_RIGHTS - {"hook.manage"}))
    assert isinstance(error, Forbidden)
    assert dict(error.details) == {"permission": "hook.manage"}
    check_write(req, context(spec, existing=existing))


def test_r13_and_r16_report_the_reason_of_the_refusing_decision_of_their_own_permission() -> None:
    spec = key_spec(write_permission="hook.manage")
    req = request(ScopeKind.WORKSPACE, action="lock")
    existing = entry(ScopeKind.WORKSPACE)
    missing = ALL_RIGHTS - {"config.lock", "hook.manage"}
    reasons = {"config.lock": "NO_MEMBERSHIP", "hook.manage": "TOKEN_NARROWED"}
    ctx = context(spec, existing=existing, granted=missing, refused=reasons)
    error = fails(req, ctx)
    assert dict(error.details) == {"permission": "config.lock", "reason_code": "NO_MEMBERSHIP"}
    [r13, r16] = collect_write_problems(req, ctx)
    assert (r13.rule, dict(r13.details)) == (
        "R13",
        {"permission": "config.lock", "reason_code": "NO_MEMBERSHIP"},
    )
    assert (r16.rule, dict(r16.details)) == (
        "R16",
        {"permission": "hook.manage", "reason_code": "TOKEN_NARROWED"},
    )
    # a reason of another permission is never borrowed; without its own, the refusal names none
    only_key = context(spec, existing=existing, granted=missing, refused={"hook.manage": "TOKEN_NARROWED"})
    assert dict(fails(req, only_key).details) == {"permission": "config.lock"}


def test_a_write_context_refuses_inconsistent_refusals_and_keeps_its_own_copy() -> None:
    with pytest.raises(ValueError, match="both granted and refused"):
        context(INT, refused={"config.lock": "ROLE_LACKS_PERMISSION"})
    for reason in ("", None, 7):
        with pytest.raises(ValueError, match="carries no reason_code"):
            context(INT, granted=frozenset(), refused=cast("Any", {"config.lock": reason}))
    given = {"config.lock": "NO_MEMBERSHIP"}
    ctx = context(INT, granted=frozenset(), refused=given)
    given["config.lock"] = "TOKEN_SCOPE"
    assert dict(ctx.refused) == {"config.lock": "NO_MEMBERSHIP"}
    with pytest.raises(TypeError):
        cast("Any", ctx.refused)["config.lock"] = "TOKEN_SCOPE"
    assert dict(context(INT).refused) == {}


# ---------------------------------------------------------------------------------------------------------
# order, collection, programming errors


def test_rules_are_collected_in_normative_order_and_check_write_raises_the_first() -> None:
    spec = key_spec(
        levels=frozenset({Level.INSTANCE}),
        deprecated=Deprecation(since="2.0"),
        confirm=True,
        lockable=False,
        write_permission="hook.manage",
    )
    above = farther(spec, contribution(Level.INSTANCE, 1, locked=True))
    req = request(ScopeKind.PROJECT, "x", locked=True, expected=3)
    ctx = context(spec, resolution=above, granted=frozenset({"config.write"}))
    assert rules(req, ctx) == ["R2", "R3", "R5", "R7", "R9", "R10", "R11", "R13", "R16"]
    assert fails(req, ctx).code is ErrorCode.CONFIG_INVALID  # R2 first
    problems = collect_write_problems(req, ctx)
    assert all(isinstance(problem, Problem) and problem.key == "demo.value" for problem in problems)
    assert [problem.code for problem in problems][-2:] == ["FORBIDDEN", "FORBIDDEN"]


def test_valid_writes_have_no_problems() -> None:
    assert collect_write_problems(request(), context(INT)) == ()
    assert collect_write_problems(request(ScopeKind.INSTANCE, locked=True), context(INT)) == ()


def test_programming_errors_raise_value_errors() -> None:
    with pytest.raises(ValueError, match="carries no operation"):
        WriteRequest(scope(ScopeKind.PROJECT), "demo.value", EntryOp.SET, 1, None, None, False, "remove")
    with pytest.raises(ValueError, match="carries an operation"):
        WriteRequest(scope(ScopeKind.PROJECT), "demo.value", None, 1, None, None, False, "write")
    with pytest.raises(ValueError, match="action"):
        WriteRequest(
            scope(ScopeKind.PROJECT), "demo.value", None, None, None, None, False, cast("Any", "drop")
        )
    for expected in (-1, cast("Any", True)):
        with pytest.raises(ValueError, match="expected_row_version"):
            request(expected=expected)
    with pytest.raises(ValueError, match="another scope"):
        check_write(request(ScopeKind.PROJECT), context(INT, existing=entry(ScopeKind.PLAN)))
    with pytest.raises(ValueError, match="spec of"):
        check_write(request(key="demo.other"), context(INT))
    # a value write without the engine checks fails closed instead of skipping R5/R6/R8
    with pytest.raises(ValueError, match="value checks"):
        check_write(request(), WriteContext(INT, None, farther(INT), ALL_RIGHTS, None))


def test_request_value_is_copied() -> None:
    value: dict[str, JsonValue] = {"a": [1]}
    req = request(value=value)
    cast("list[JsonValue]", value["a"]).append(2)
    assert req.value == {"a": [1]}


# ---------------------------------------------------------------------------------------------------------
# entries: versions, no-op content, lock factories


def test_entry_versions_and_lock_factories() -> None:
    made = entry(ScopeKind.WORKSPACE)
    assert made.row_version == 1
    later = NOW + timedelta(minutes=1)
    changed = change_entry(made, op=EntryOp.UNSET, value=None, reason="r", actor=ACTOR, now=later)
    assert (changed.row_version, changed.locked, changed.created_at, changed.updated_at) == (
        2,
        False,
        NOW,
        later,
    )
    locked = set_lock(changed, locked=True, reason="", actor=ACTOR, now=later)
    assert (locked.row_version, locked.locked, locked.op) == (3, True, EntryOp.UNSET)
    kept = change_entry(locked, op=EntryOp.SET, value=5, reason="", actor=ACTOR, now=later)
    assert kept.locked
    assert kept.row_version == 4
    with pytest.raises(ValueError, match="no-op"):
        set_lock(locked, locked=True, reason="", actor=ACTOR, now=later)
    with pytest.raises(ValueError, match="instance and workspace"):
        set_lock(entry(ScopeKind.PROJECT), locked=True, reason="", actor=ACTOR, now=later)
    with pytest.raises(ValueError, match="instance and workspace"):
        entry(ScopeKind.HOST, locked=True)


class _CasRows:
    """One stored row under the documented ``ConfigEntryRepository.save`` contract (ports.py)."""

    def __init__(self, row: ConfigEntry) -> None:
        self.row = row

    def save(self, after: ConfigEntry, *, expected_version: int) -> None:
        if self.row.row_version != expected_version:
            raise version_conflict(expected_version, self.row.row_version)
        if after.row_version <= expected_version:
            raise ValueError("the saved version must be above the expected one")
        self.row = after


@pytest.mark.parametrize(("was", "becomes"), [(False, True), (True, False)])
def test_value_change_with_lock_change_saves_two_versions_against_the_read_one(
    was: bool, becomes: bool
) -> None:
    """§A.7.1: change_entry then set_lock is one write; CAS expects the version that was read."""
    read = entry(ScopeKind.WORKSPACE, locked=was, version=4)
    changed = change_entry(read, op=EntryOp.SET, value=2, reason="", actor=ACTOR, now=NOW)
    after = set_lock(changed, locked=becomes, reason="", actor=ACTOR, now=NOW)
    assert (changed.row_version, after.row_version) == (5, 6)
    rows = _CasRows(read)
    rows.save(after, expected_version=read.row_version)
    assert (rows.row.row_version, rows.row.value, rows.row.locked) == (6, 2, becomes)
    # a single change is one version up and goes through the same check
    single = _CasRows(read)
    single.save(changed, expected_version=read.row_version)
    assert single.row.row_version == 5
    # a writer that read version 4 after another one committed: the conditional update conflicts
    with pytest.raises(Conflict) as caught:
        rows.save(after, expected_version=read.row_version)
    assert dict(caught.value.details) == {"expected": 4, "actual": 6}
    with pytest.raises(ValueError, match="above"):
        _CasRows(read).save(read, expected_version=read.row_version)


def test_entry_invariants_follow_the_ddl() -> None:
    with pytest.raises(ValueError, match="unset"):
        entry(value=None, op=EntryOp.SET)
    with pytest.raises(ValueError, match="unset"):
        entry(value=1, op=EntryOp.UNSET)
    with pytest.raises(ValueError, match="array"):
        entry(value=1, op=EntryOp.APPEND)
    with pytest.raises(ValueError, match="settings key"):
        entry(key="Demo.value")
    with pytest.raises(ValueError, match="settings key"):
        entry(key="demo")
    with pytest.raises(ValueError, match="row_version"):
        entry(version=0)
    with pytest.raises(ValueError, match="reason"):
        replace(entry(), reason="x" * 2001)
    with pytest.raises(ValueError, match="timezone"):
        replace(entry(), updated_at=datetime(2026, 1, 1))  # noqa: DTZ001 - the naive value is the case
    with pytest.raises(TypeError, match="JSON"):
        entry(value=cast("Any", (1, 2)))
    # a stored value has a canonical JSON digest of at most 64 KiB: what R5 reports for a request, an entry
    # refuses (ck_entries__value_size); integers of any width within it are stored
    refused: tuple[JsonValue, ...] = ("\ud800", {"\udc00": 1}, {"a": ["\udfff"]}, *OVER)
    for value in refused:
        with pytest.raises(ValueError, match="not storable canonical JSON"):
            entry(value=value)
        with pytest.raises(ValueError, match="not storable canonical JSON"):
            replace(entry(), value=value)
        with pytest.raises(ValueError, match="not storable canonical JSON"):
            change_entry(entry(), op=EntryOp.SET, value=value, reason="", actor=ACTOR, now=NOW)
    with pytest.raises(ValueError, match="not storable canonical JSON"):
        entry(value=["x", "\ud800"], op=EntryOp.APPEND)
    with pytest.raises(ValueError, match="not storable canonical JSON"):
        entry(value=[10**VALUE_MAX_BYTES], op=EntryOp.APPEND)
    for value in WIDE:
        assert replace(entry(), value=value).value == value


@pytest.mark.parametrize(
    ("stored", "op", "value", "locked", "same"),
    [
        (1, EntryOp.SET, 1, False, True),
        (1, EntryOp.SET, 1.0, False, False),
        (1, EntryOp.SET, True, False, False),
        (0, EntryOp.SET, False, False, False),
        ({"a": 1, "b": [1, 2]}, EntryOp.SET, {"b": [1, 2], "a": 1}, False, True),
        ([1, 2], EntryOp.SET, [2, 1], False, False),
        (1, EntryOp.SET, 1, True, False),
        ([1], EntryOp.APPEND, [1], False, True),
    ],
)
def test_same_content_is_strict(
    stored: JsonValue, op: EntryOp, value: JsonValue, locked: bool, same: bool
) -> None:
    existing = entry(ScopeKind.WORKSPACE, value=stored, op=op)
    assert same_content(existing, op, value, locked) is same
    appended = entry(ScopeKind.WORKSPACE, value=[1], op=EntryOp.APPEND)
    assert not same_content(appended, EntryOp.SET, [1], False)  # the operation is part of the content


def test_same_content_of_unset() -> None:
    existing = entry(value=None, op=EntryOp.UNSET)
    assert same_content(existing, EntryOp.UNSET, None, False)
    assert not same_content(existing, EntryOp.SET, 1, False)


# ---------------------------------------------------------------------------------------------------------
# history


def test_history_record_shapes() -> None:
    before = entry(ScopeKind.WORKSPACE)
    after = change_entry(before, op=EntryOp.SET, value=2, reason="", actor=ACTOR, now=NOW)
    locked = set_lock(after, locked=True, reason="", actor=ACTOR, now=NOW)

    def record(old: ConfigEntry | None, new: ConfigEntry | None, kind: ChangeKind) -> HistoryRecord:
        return history_record(
            record_id=uuid4(),
            before=old,
            after=new,
            kind=kind,
            actor=ACTOR,
            request_id="req-1",
            reason="why",
            generation=5,
            now=NOW,
        )

    created = record(None, before, ChangeKind.CREATED)
    assert (created.old_op, created.new_op, created.new_value, created.scope_id) == (
        None,
        EntryOp.SET,
        1,
        SCOPES[ScopeKind.WORKSPACE],
    )
    updated = record(before, after, ChangeKind.UPDATED)
    assert (updated.old_value, updated.new_value, updated.entry_id) == (1, 2, before.id)
    assert record(after, locked, ChangeKind.LOCKED).new_locked is True
    assert record(locked, None, ChangeKind.REMOVED).new_op is None
    for old, new, kind in (
        (before, before, ChangeKind.CREATED),
        (None, before, ChangeKind.UPDATED),
        (before, None, ChangeKind.UPDATED),
        (None, before, ChangeKind.REMOVED),
        (before, after, ChangeKind.LOCKED),
        (after, locked, ChangeKind.UNLOCKED),
    ):
        with pytest.raises(ValueError, match=r"history|record"):
            record(old, new, kind)
    with pytest.raises(ValueError, match="different entries"):
        record(before, entry(ScopeKind.WORKSPACE), ChangeKind.UPDATED)
    with pytest.raises(ValueError, match="generation"):
        replace(created, generation=0)
