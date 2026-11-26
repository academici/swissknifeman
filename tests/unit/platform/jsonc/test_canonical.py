"""Byte-level compatibility and rejection rules for canonical JSON v1."""

import json
from collections import OrderedDict
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from skm.platform.jsonc.canonical import (
    CANONICALIZATION_VERSION,
    InvalidUnicodeError,
    canonical_bytes,
    canonical_value,
    format_decimal,
    format_timestamp,
)
from skm.platform.jsonc.digest import digest

VECTORS_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "digest" / "vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(vector["input"], vector["canonical"].encode("utf-8")) for vector in VECTORS],
    ids=[vector["name"] for vector in VECTORS],
)
def test_legacy_canonical_bytes(value: object, expected: bytes) -> None:
    assert CANONICALIZATION_VERSION == 1
    assert canonical_bytes(value) == expected


def test_canonical_value_sorts_objects_and_copies_containers_without_mutating() -> None:
    items = [True, {"z": None, "a": [1, 2]}]
    original = OrderedDict([("z", items), ("a", "é")])
    result = canonical_value(MappingProxyType(original))
    assert result == {"a": "é", "z": (True, {"a": (1, 2), "z": None})}
    assert isinstance(result, dict)
    assert list(result) == ["a", "z"]
    assert list(result["z"][1]) == ["a", "z"]
    assert list(original) == ["z", "a"]
    assert items == [True, {"z": None, "a": [1, 2]}]
    assert canonical_bytes(original) == b'{"a":"\xc3\xa9","z":[true,{"a":[1,2],"z":null}]}'


def test_tuples_and_lists_have_identical_bytes_and_keep_array_order() -> None:
    assert canonical_bytes((1, [2, (3,)])) == canonical_bytes([1, (2, [3])]) == b"[1,[2,[3]]]"
    assert canonical_bytes([1, 2]) != canonical_bytes([2, 1])


@pytest.mark.parametrize("value", [1.5, 1.0, 0.0, -0.0, float("nan"), float("inf"), -float("inf")])
def test_floats_are_rejected_at_every_depth(value: float) -> None:
    for document in (value, {"a": value}, [0, {"a": (value,)}]):
        with pytest.raises(TypeError, match=r"^canonical JSON values must not use floats$"):
            canonical_value(document)
        with pytest.raises(TypeError, match=r"^canonical JSON values must not use floats$"):
            canonical_bytes(document)


@pytest.mark.parametrize("key", [1, False, None, ("a",), b"a"])
def test_non_string_keys_fail_before_sorting_or_json_coercion(key: object) -> None:
    for document in ({"a": 1, key: "x"}, [{"nested": {key: "x"}}]):
        with pytest.raises(TypeError, match=r"^canonical JSON object keys must be strings$"):
            canonical_bytes(document)


@pytest.mark.parametrize(
    "value",
    [
        object(),
        UUID(int=1),
        datetime(2026, 1, 1, tzinfo=UTC),
        Decimal("0.125"),
        b"x",
        bytearray(b"x"),
        memoryview(b"x"),
        {1, 2},
        frozenset({1}),
        range(3),
    ],
    ids=[
        "object",
        "uuid",
        "datetime",
        "decimal",
        "bytes",
        "bytearray",
        "memoryview",
        "set",
        "frozenset",
        "range",
    ],
)
def test_unsupported_objects_need_an_explicit_json_projection(value: object) -> None:
    for document in (value, {"a": [value]}):
        with pytest.raises(TypeError, match=r"^value is not canonical JSON data$"):
            canonical_bytes(document)


def test_booleans_null_missing_and_integers_keep_distinct_json_meanings() -> None:
    assert canonical_bytes([True, False, 1, 0, -7, None]) == b"[true,false,1,0,-7,null]"
    assert canonical_bytes({"a": None}) != canonical_bytes({})
    # Schema owners restrict numeric ranges; the core retains the donor's large integer vector.
    assert canonical_bytes(12345678901234567890) == b"12345678901234567890"
    assert canonical_bytes({"cost_usd_micros": 125000}) == b'{"cost_usd_micros":125000}'


def test_all_mandatory_escapes_and_only_mandatory_escapes() -> None:
    controls = "".join(chr(code) for code in range(32))
    expected = (
        '"\\u0000\\u0001\\u0002\\u0003\\u0004\\u0005\\u0006\\u0007'
        "\\b\\t\\n\\u000b\\f\\r\\u000e\\u000f\\u0010\\u0011\\u0012\\u0013"
        "\\u0014\\u0015\\u0016\\u0017\\u0018\\u0019\\u001a\\u001b"
        '\\u001c\\u001d\\u001e\\u001f"'
    )
    assert canonical_bytes(controls) == expected.encode("utf-8")
    assert canonical_bytes('"\\/\x7fé😀\u2028\u2029') == '"\\"\\\\/\x7fé😀\u2028\u2029"'.encode("utf-8")


def test_unicode_is_not_normalized_and_keys_follow_code_points() -> None:
    assert canonical_bytes("é") != canonical_bytes("e\u0301")
    assert canonical_bytes({"😀": 1, "\uffff": 2, "é": 3, "e\u0301": 4}) == (
        '{"e\u0301":4,"é":3,"\uffff":2,"😀":1}'.encode("utf-8")
    )


@pytest.mark.parametrize("bad", ["\ud800", "\udfff", "a\ud83d", "\ude00b", "\ud83d\ude00\udc00", "é\udbffx"])  # noqa: PT014
def test_unpaired_surrogates_are_invalid_unicode_in_values_and_keys_at_every_depth(bad: str) -> None:
    documents = (
        bad,
        [bad],
        {"a": bad},
        {bad: 1},
        {"a": 1, bad: 2},
        {"outer": [{"inner": (None, {bad: "x"})}]},
        {"outer": [{"inner": (None, {"k": bad})}]},
    )
    for document in documents:
        with pytest.raises(InvalidUnicodeError, match=r"^canonical JSON strings must be valid Unicode text$"):
            canonical_value(document)
        with pytest.raises(InvalidUnicodeError):
            canonical_bytes(document)
        with pytest.raises(InvalidUnicodeError):
            digest(document)


def test_invalid_unicode_is_a_value_error_that_never_repeats_the_text() -> None:
    with pytest.raises(InvalidUnicodeError) as raised:
        canonical_bytes({"secret-key\ud800": "secret-value\udc00"})
    assert isinstance(raised.value, ValueError)
    assert "secret" not in str(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


def test_valid_unicode_including_paired_surrogates_and_noncharacters_is_unchanged() -> None:
    # A pair written as two surrogate code units is not valid in Python; the astral code point is.
    assert canonical_bytes("\U0001f600") == '"😀"'.encode()
    assert "\ud83d\ude00" != "\U0001f600"
    assert canonical_bytes({"\ufffe": "\uffff", "ключ": "значение", "日本": ["語", "\U0010ffff"]}) == (
        '{"ключ":"значение","日本":["語","\U0010ffff"],"\ufffe":"\uffff"}'.encode("utf-8")
    )
    assert canonical_bytes("\x00\x7f\x80\u07ff\u0800\ud7ff\ue000") == (
        '"\\u0000\x7f\x80\u07ff\u0800\ud7ff\ue000"'.encode("utf-8")
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2026, 10, 25, 14, 3, 11, 123456, tzinfo=UTC), "2026-10-25T14:03:11.123456Z"),
        (datetime(2026, 1, 1, tzinfo=UTC), "2026-01-01T00:00:00.000000Z"),
        (
            datetime(2026, 1, 1, 0, 15, 3, 4, tzinfo=timezone(timedelta(hours=3, minutes=30))),
            "2025-12-31T20:45:03.000004Z",
        ),
    ],
)
def test_timestamp_projection_is_utc_with_exact_microseconds(value: datetime, expected: str) -> None:
    assert format_timestamp(value) == expected
    assert canonical_bytes(format_timestamp(value)) == f'"{expected}"'.encode()


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        format_timestamp(datetime(2026, 1, 1))  # noqa: DTZ001 - deliberately naive


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.1250", "0.125"),
        ("1E+3", "1000"),
        ("1E-7", "0.0000001"),
        ("-12.34000", "-12.34"),
        ("100.000", "100"),
        ("0.000", "0"),
        ("-0.00", "-0"),
    ],
)
def test_decimal_projection_is_fixed_and_has_no_fractional_trailing_zeros(text: str, expected: str) -> None:
    assert format_decimal(Decimal(text)) == expected
    assert canonical_bytes(format_decimal(Decimal(text))) == f'"{expected}"'.encode()


def test_decimal_projection_does_not_round_to_the_ambient_context() -> None:
    value = Decimal("123456789012345678901234567890.1234500")
    with localcontext() as context:
        context.prec = 3
        assert format_decimal(value) == "123456789012345678901234567890.12345"


@pytest.mark.parametrize("text", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_non_finite_decimals_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="finite"):
        format_decimal(Decimal(text))
