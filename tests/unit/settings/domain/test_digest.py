"""``entries_digest``: the CAS digest of one scope's entries (settings §A.4, §A.7.6)."""

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from typing import cast
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.ids import PrincipalId, ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.settings.domain.digest import entries_digest
from skm.modules.settings.domain.entry import (
    VALUE_MAX_BYTES,
    ConfigEntry,
    ConfigEntryId,
    EntryOp,
    canonical_json,
    change_entry,
    int_text,
    new_entry,
    same_content,
    set_lock,
)
from skm.platform.jsonc.digest import digest, is_tagged_digest

SCOPE = ScopeRef(ScopeKind.WORKSPACE, ScopeId(UUID(int=1)))
ACTOR = PrincipalId(UUID(int=2))
NOW = datetime(2026, 10, 28, tzinfo=UTC)


def make(
    key: str, value: JsonValue | None, *, op: EntryOp = EntryOp.SET, locked: bool = False
) -> ConfigEntry:
    return new_entry(
        entry_id=ConfigEntryId(uuid4()),
        scope=SCOPE,
        key=key,
        op=op,
        value=value,
        locked=locked,
        reason="",
        actor=ACTOR,
        now=NOW,
    )


def tagged(value: JsonValue) -> JsonValue:
    """The type-tagged value of a digest row: ``[tag, payload]`` at every depth."""
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, float):
        return ["float", repr(value)]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, list):
        return ["list", [tagged(item) for item in value]]
    return ["object", {key: tagged(item) for key, item in value.items()}]


def platform_digest(rows: list[list[JsonValue]]) -> str:
    return digest([[key, op, tagged(value), locked] for key, op, value, locked in rows])


def test_empty_scope_is_the_digest_of_an_empty_list() -> None:
    assert entries_digest([]) == digest([])
    assert entries_digest({}) == digest([])
    assert is_tagged_digest(entries_digest([]))


def test_digest_is_platform_jsonc_of_sorted_rows_with_tagged_values() -> None:
    entries = [
        make("execution.review.max_rounds", 2, locked=True),
        make("budgets.run.max_usd", 15.0),
        make("execution.consilium.members", None, op=EntryOp.UNSET),
        make("execution.generation.command", ["python3", "tools/gen.py"], op=EntryOp.APPEND),
        make("execution.workflow.profile_by_work_kind", {"research": {"$unset": True}, "docs": "quick-fix"}),
        make("integrations.targets", ["ä", "z"]),
    ]
    expected = platform_digest(
        [
            ["budgets.run.max_usd", "set", 15.0, False],
            ["execution.consilium.members", "unset", None, False],
            ["execution.generation.command", "append", ["python3", "tools/gen.py"], False],
            ["execution.review.max_rounds", "set", 2, True],
            [
                "execution.workflow.profile_by_work_kind",
                "set",
                {"docs": "quick-fix", "research": {"$unset": True}},
                False,
            ],
            ["integrations.targets", "set", ["ä", "z"], False],
        ]
    )
    assert entries_digest(entries) == expected
    assert entries_digest(reversed(entries)) == expected
    assert entries_digest({entry.key: entry for entry in entries}) == expected


def test_digest_tracks_content_not_bookkeeping() -> None:
    base = make("demo.value", 1)
    same = replace(
        base, row_version=9, reason="other", updated_at=NOW + timedelta(days=1), id=ConfigEntryId(uuid4())
    )
    assert entries_digest([same]) == entries_digest([base])
    for changed in (
        replace(base, value=2),
        replace(base, value=1.0),
        replace(base, value=True),
        replace(base, value="1"),
        replace(base, op=EntryOp.UNSET, value=None),
        replace(base, op=EntryOp.APPEND, value=[1]),
        set_lock(replace(base, scope=SCOPE), locked=True, reason="", actor=ACTOR, now=NOW),
        replace(base, key="demo.other"),
    ):
        assert entries_digest([changed]) != entries_digest([base]), changed
    assert entries_digest([base, make("demo.extra", 1)]) != entries_digest([base])


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (1.5, "1.5"),  # a concurrent type change must move the scope CAS digest (§A.7.6)
        ({"config": {"ratio": 1.5}}, {"config": {"ratio": "1.5"}}),
        ([1.5, "x"], ["1.5", "x"]),
        ([[1.5]], [["1.5"]]),
        (1, 1.0),
        (1, True),
        (0, False),
        ({"a": None}, {"a": "null"}),
        # user values shaped like the tagged form itself
        (1.5, ["float", "1.5"]),
        ("x", ["str", "x"]),
        ([1], ["list", [["int", 1]]]),
        ({"a": 1}, ["object", {"a": ["int", 1]}]),
        ({"a": 1}, [["a", 1]]),
        ([], {}),
        ([None], ["null"]),
    ],
)
def test_digest_keeps_the_json_type_of_values(left: JsonValue, right: JsonValue) -> None:
    assert entries_digest([make("demo.value", left)]) != entries_digest([make("demo.value", right)])
    current = make("demo.value", left)
    assert not same_content(current, EntryOp.SET, right, False)


def test_duplicate_keys_are_not_one_scope() -> None:
    with pytest.raises(ValueError, match="twice"):
        entries_digest([make("demo.value", 1), make("demo.value", 2)])


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
# exactly VALUE_MAX_BYTES of canonical JSON: 65536 digits, "-" and 65535 digits, {"n":} and 65530 digits
EDGES: tuple[JsonValue, ...] = (
    10**VALUE_MAX_BYTES - 1,
    -(10 ** (VALUE_MAX_BYTES - 1) - 1),
    {"n": 10 ** (VALUE_MAX_BYTES - 6) - 1},
)
# one byte more, a string of one byte more and an integer far beyond the bound (never written out)
OVER: tuple[JsonValue, ...] = (
    10**VALUE_MAX_BYTES,
    -(10 ** (VALUE_MAX_BYTES - 1)),
    {"n": 10 ** (VALUE_MAX_BYTES - 6)},
    "x" * (VALUE_MAX_BYTES - 1),
    [10**1_000_000],
)


class Small(IntEnum):
    TWO = 2


@pytest.mark.parametrize("limit", LIMITS)
def test_int_text_is_the_json_text_under_any_limit(limit: int) -> None:
    numbers = [0, 1, -1, Small.TWO]
    for digits in (511, 512, 513, 640, 641, 1024, 1025, 1537, 5001):
        numbers += [
            10 ** (digits - 1),
            10**digits - 1,
            7 * 10 ** (digits - 1) + 12345,
            10 ** (digits - 1) + 1,
        ]
    numbers += [-number for number in numbers]
    with int_text_limit(0):
        expected = [json.dumps(number) for number in numbers]
    with int_text_limit(limit):
        assert [int_text(number) for number in numbers] == expected
        assert canonical_json({"n": numbers, "s": "ä"}) == '{"n":[' + ",".join(expected) + '],"s":"ä"}'


@pytest.mark.parametrize("value", [W641, {"n": W641}, {"n": W5001}, [-W5001], *EDGES], ids=lambda _: "")
def test_wide_integers_within_the_size_are_entries_whatever_the_limit(value: JsonValue) -> None:
    for limit in LIMITS:
        with int_text_limit(limit):
            assert make("demo.value", value).value == value


@pytest.mark.parametrize(
    "value",
    [
        json.loads('"\\ud800"'),  # a parsed escape: a scalar, a key and a nested string
        json.loads('{"\\udc00": 1}'),
        json.loads('{"a": [{"b": "x\\udfffy"}]}'),
        *OVER,
    ],
    ids=lambda _: "",  # a test id would need the text form of a wide integer
)
def test_values_that_cannot_be_stored_have_no_entry_and_no_digest(value: JsonValue) -> None:
    """The entry refuses them, and a value changed in place is a ValueError of the digest, not of UTF-8."""
    with pytest.raises(ValueError, match="not storable canonical JSON"):
        make("demo.value", value)
    held: dict[str, JsonValue] = {"a": 1}
    current = make("demo.value", held)
    cast("dict[str, JsonValue]", current.value)["a"] = value  # shallow mutation (the adapter copies)
    with pytest.raises(ValueError, match="not storable canonical JSON") as caught:
        entries_digest([current])
    assert type(caught.value) is ValueError
    assert "\ud800" not in str(caught.value)


def test_wide_integers_digest_as_platform_jsonc_under_any_limit() -> None:
    """641 and 5001 digits, nested in a mapping or not, up to 64 KiB: one digest whatever the limit."""
    values: tuple[JsonValue, ...] = (W641, -W641, {"n": W5001}, {"n": [W5001, -W641], "s": "ä"}, *EDGES)
    for value in values:
        entries = [make("demo.value", value), make("demo.other", {"m": [W641]}, locked=True)]
        with int_text_limit(0):  # the oracle: platform jsonc where json may write every integer
            expected = platform_digest(
                [["demo.other", "set", {"m": [W641]}, True], ["demo.value", "set", value, False]]
            )
        for limit in LIMITS:
            with int_text_limit(limit):
                assert entries_digest(entries) == expected
    # CAS stays injective at full width: the next integer, its sign and its text are other contents
    base = entries_digest([make("demo.value", {"n": W5001})])
    with int_text_limit(0):
        text = str(W5001)
    others: tuple[JsonValue, ...] = (
        {"n": W5001 + 1},
        {"n": -W5001},
        {"n": text},
        {"n": [W5001]},
        {"n": float(10**300)},
    )
    for other in others:
        assert entries_digest([make("demo.value", other)]) != base
    assert entries_digest([make("demo.value", W641)]) == entries_digest([make("demo.value", W641)])
    text_value = "ä\U0001f600"
    assert entries_digest([make("demo.value", {text_value: text_value})]) == platform_digest(
        [["demo.value", "set", {text_value: text_value}, False]]
    )


# Strings may look like numbers or like the tagged form: the digest keeps every JSON type apart.
json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=4)
    | st.sampled_from(["1.5", "1", "0.0", "-0.0", "True", "null", "float", "str", "int", "list", "object"]),
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=3), children, max_size=3)
    ),
    max_leaves=8,
)


@given(json_values)
def test_canonical_json_is_the_json_text_of_a_value(value: JsonValue) -> None:
    assert canonical_json(value) == json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


@given(json_values, json_values, st.booleans(), st.booleans())
def test_no_op_content_keeps_the_digest(
    stored: JsonValue, wanted: JsonValue, was: bool, becomes: bool
) -> None:
    """R15 and CAS agree: a no-op write leaves the digest alone, a real change moves it."""
    if stored is None or wanted is None:
        return
    current = make("demo.value", stored, locked=was)
    after = change_entry(current, op=EntryOp.SET, value=wanted, reason="", actor=ACTOR, now=NOW)
    if becomes != was:
        after = set_lock(after, locked=becomes, reason="", actor=ACTOR, now=NOW)
    unchanged = same_content(current, EntryOp.SET, wanted, becomes)
    assert (entries_digest([current]) == entries_digest([after])) is unchanged


def _floats_as_text(value: JsonValue) -> JsonValue:
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return [_floats_as_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _floats_as_text(item) for key, item in value.items()}
    return value


@given(json_values)
def test_float_and_its_repr_string_never_share_a_digest(stored: JsonValue) -> None:
    """The type change a concurrent import could make (1.5 → "1.5", at any depth) moves the digest."""
    if stored is None:
        return
    text = _floats_as_text(stored)
    current = make("demo.value", stored)
    changed = make("demo.value", text)
    same = same_content(current, EntryOp.SET, text, False)
    assert (entries_digest([current]) == entries_digest([changed])) is same
