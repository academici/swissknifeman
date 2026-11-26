"""SchemaIssue / SchemaValidator: pointer and code per keyword, ordering, dedup, truncation (§3.3)."""

import copy
import json
import sys
from collections import UserDict
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from types import MappingProxyType
from typing import Any, override

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.platform.schema.findings import MESSAGE_LIMIT, SchemaIssue, json_pointer, truncate
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.schema.validator import SchemaValidator, is_schema_type, without_dialect

DIALECT = "https://json-schema.org/draft/2020-12/schema"


def issues(schema: dict[str, Any], instance: object) -> tuple[SchemaIssue, ...]:
    return SchemaValidator({"$schema": DIALECT, **schema}, Registry()).issues(instance)


def codes(found: tuple[SchemaIssue, ...]) -> list[tuple[str, str]]:
    return [(issue.pointer, issue.code) for issue in found]


def test_json_pointer_escapes_per_rfc6901() -> None:
    assert json_pointer([]) == ""
    assert json_pointer(["items", 0, "title"]) == "/items/0/title"
    assert json_pointer(["a/b", "m~n", ""]) == "/a~1b/m~0n/"


def test_valid_instance_has_no_issues() -> None:
    assert issues({"type": "object", "required": ["a"]}, {"a": 1}) == ()


def test_required_reports_every_missing_property_at_the_object() -> None:
    found = issues({"type": "object", "required": ["a", "b"]}, {})
    assert codes(found) == [("", "required"), ("", "required")]
    messages = sorted(issue.message for issue in found)
    assert messages == ["'a' is a required property", "'b' is a required property"]
    assert {issue.schema_pointer for issue in found} == {"/required"}


def test_nested_pointer_and_schema_pointer() -> None:
    item = {"properties": {"title": {"type": "string"}}}
    schema = {"properties": {"items": {"type": "array", "items": item}}}
    found = issues(schema, {"items": [{"title": "ok"}, {"title": 5}]})
    expected = SchemaIssue(
        "/items/1/title", "/properties/items/items/properties/title/type", "type", "5 is not of type 'string'"
    )
    assert found == (expected,)


def test_pointer_segments_are_escaped() -> None:
    schema = {"properties": {"a/b": {"type": "integer"}, "m~n": {"type": "integer"}}}
    found = issues(schema, {"a/b": "x", "m~n": "y"})
    assert [issue.pointer for issue in found] == ["/a~1b", "/m~0n"]


@pytest.mark.parametrize(
    ("schema", "instance", "code"),
    [
        ({"type": "integer"}, "x", "type"),
        ({"enum": [1, 2]}, 3, "enum"),
        ({"const": "a"}, "b", "const"),
        ({"pattern": "^a"}, "b", "pattern"),
        ({"minLength": 2}, "a", "minLength"),
        ({"maxLength": 1}, "ab", "maxLength"),
        ({"minimum": 2}, 1, "minimum"),
        ({"maximum": 1}, 2, "maximum"),
        ({"minItems": 1}, [], "minItems"),
        ({"maxItems": 1}, [1, 2], "maxItems"),
        ({"uniqueItems": True}, [1, 1], "uniqueItems"),
        ({"format": "uuid"}, "nope", "format"),
        ({"format": "date-time"}, "2026-10-25", "format"),
    ],
)
def test_keyword_is_the_code(schema: dict[str, Any], instance: object, code: str) -> None:
    found = issues(schema, instance)
    assert codes(found) == [("", code)]


def test_boolean_is_not_an_integer() -> None:
    assert codes(issues({"type": "integer"}, True)) == [("", "type")]


@pytest.mark.parametrize(
    ("instance", "matching"),
    [
        (None, {"null"}),
        (True, {"boolean"}),
        (False, {"boolean"}),
        (0, {"integer", "number"}),
        (10**1000, {"integer", "number"}),
        (1.0, {"integer", "number"}),
        (-0.0, {"integer", "number"}),
        (1.5, {"number"}),
        (float("inf"), {"number"}),
        (float("nan"), {"number"}),
        (Decimal("1.0"), {"number"}),
        (Fraction(1, 1), {"number"}),
        (1 + 2j, {"number"}),
        ("public", {"string"}),
        (["public"], {"array"}),
        ({"public": "ok"}, {"object"}),
        (("public",), set()),
        (MappingProxyType({"public": "ok"}), set()),
        (UserDict({"public": "ok"}), set()),
    ],
)
def test_type_facade_keeps_exact_draft_2020_12_semantics(instance: object, matching: set[str]) -> None:
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        assert is_schema_type(instance, name) is (name in matching)
        assert is_schema_type(instance, name) is Draft202012Validator.TYPE_CHECKER.is_type(instance, name)


@pytest.mark.parametrize(
    ("instance", "matching"),
    [
        (1, {"integer", "number"}),
        (1.0, {"integer", "number"}),
        (1.5, {"number"}),
        ("public", {"string"}),
        (["public"], {"array"}),
        ({"public": "ok"}, {"object"}),
    ],
)
def test_type_facade_keeps_stock_subclass_behavior(instance: Any, matching: set[str]) -> None:
    subclass = type("Subclass", (type(instance),), {})(instance)
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        assert is_schema_type(subclass, name) is (name in matching)
        assert is_schema_type(subclass, name) is Draft202012Validator.TYPE_CHECKER.is_type(subclass, name)


def test_additional_properties_message_is_the_property_name() -> None:
    schema = {"type": "object", "properties": {"known": {}}, "additionalProperties": False}
    found = issues(schema, {"known": 1, "zeta": 2, "alpha": 3})
    assert [(i.pointer, i.code, i.message) for i in found] == [
        ("", "additionalProperties", "alpha"),
        ("", "additionalProperties", "zeta"),
    ]
    assert found[0].schema_pointer == "/additionalProperties"


def test_additional_properties_skips_pattern_properties_and_keeps_nested_pointer() -> None:
    strict = {"additionalProperties": False, "patternProperties": {"^x_": {}}, "properties": {"a": {}}}
    schema = {"properties": {"o": strict}}
    found = issues(schema, {"o": {"a": 1, "x_free": 2, "stray": 3}})
    assert [(i.pointer, i.message) for i in found] == [("/o", "stray")]


def test_one_of_reports_itself_and_the_most_relevant_branch() -> None:
    schema = {"oneOf": [{"type": "string"}, {"type": "object", "required": ["x"]}]}
    found = issues(schema, {})
    assert codes(found) == [("", "oneOf"), ("", "required")]
    assert "'x' is a required property" in found[1].message
    assert found[1].schema_pointer == "/oneOf/1/required"


def test_any_of_branch_error_keeps_its_deeper_pointer() -> None:
    schema = {"anyOf": [{"type": "string"}, {"type": "object", "properties": {"n": {"type": "integer"}}}]}
    found = issues(schema, {"n": "x"})
    assert codes(found) == [("", "anyOf"), ("/n", "type")]


def test_one_of_matching_several_branches_has_only_its_own_issue() -> None:
    found = issues({"oneOf": [{"type": "integer"}, {"minimum": 0}]}, 1)
    assert codes(found) == [("", "oneOf")]


def test_issues_are_sorted_by_pointer_then_code() -> None:
    properties = {"b": {"type": "integer"}, "a": {"type": "integer", "minimum": 5}}
    schema = {"properties": properties, "required": ["c"]}
    found = issues(schema, {"b": "x", "a": "y"})
    assert codes(found) == [("", "required"), ("/a", "type"), ("/b", "type")]
    assert found == tuple(sorted(found, key=lambda i: (i.pointer, i.code, i.message, i.schema_pointer)))


def test_identical_findings_from_several_branches_are_reported_once() -> None:
    schema = {"allOf": [{"required": ["a"]}, {"required": ["a"]}]}
    found = issues(schema, {})
    assert len(found) == 1
    assert found[0].code == "required"


def test_long_instance_values_are_cut_to_eighty_characters() -> None:
    value = "x" * 500
    (issue,) = issues({"maxLength": 5}, value)
    assert value not in issue.message
    assert "…" in issue.message
    assert len(issue.message) < 120


def test_short_instance_values_stay_whole() -> None:
    (issue,) = issues({"maxLength": 1}, "x" * 70)
    assert "x" * 70 in issue.message


def test_message_is_bounded_to_three_hundred_characters() -> None:
    (issue,) = issues({"enum": [f"option-{n:04d}" for n in range(200)]}, "other")
    assert len(issue.message) == MESSAGE_LIMIT
    assert issue.message.endswith("…")
    assert SchemaIssue("", "", "x", "y" * 1000).message == truncate("y" * 1000, MESSAGE_LIMIT)


def test_to_json_is_the_four_documented_fields() -> None:
    issue = SchemaIssue("/a", "/properties/a/type", "type", "bad")
    expected: dict[str, JsonValue] = {
        "pointer": "/a",
        "schema_pointer": "/properties/a/type",
        "code": "type",
        "message": "bad",
    }
    assert issue.to_json() == expected


# Wider than the default int-to-text limit (4300 digits): its ``repr`` raises unless the validator guards it.
WIDE = 7 * (10**5001 - 1) // 9  # 5001 sevens


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf"])
@pytest.mark.parametrize("number", [WIDE, -WIDE, 10**640], ids=["wide", "negative", "first-wide"])
def test_a_wide_integer_matching_one_branch_is_valid(keyword: str, number: int) -> None:
    schema = {keyword: [{"type": "string"}, {"type": "object"}, {"type": "integer"}]}
    assert issues(schema, number) == ()
    assert issues({"type": "object", "properties": {"n": schema}}, {"n": number}) == ()


def test_a_wide_integer_failing_every_branch_is_reported_with_its_leading_digits() -> None:
    schema = {"anyOf": [{"type": "string"}, {"type": "integer", "maximum": 10}]}
    found = issues({"properties": {"n": {"type": "array", "items": schema}}}, {"n": [1, WIDE]})
    assert codes(found) == [("/n/1", "anyOf"), ("/n/1", "maximum")]
    shown = "7" * 79 + "…"
    assert [issue.message for issue in found] == [
        f"{shown} is not valid under any of the given schemas",
        f"{shown} is greater than the maximum of 10",
    ]


@pytest.mark.parametrize(
    ("schema", "instance", "code", "shown"),
    [
        ({"type": "string"}, -WIDE, "type", "-" + "7" * 78 + "… is not"),
        ({"enum": [1, 2]}, 10**640, "enum", "1" + "0" * 78 + "…"),
        ({"maximum": 1}, 10**640, "maximum", "1" + "0" * 78 + "…"),
        ({"multipleOf": 2}, WIDE, "multipleOf", "7" * 79 + "…"),
        ({"uniqueItems": True}, [WIDE, WIDE], "uniqueItems", "[" + "7" * 78 + "…"),
        ({"type": "object"}, [WIDE, "x"], "type", "[" + "7" * 78 + "…"),
    ],
    ids=["type", "enum", "maximum", "multipleOf", "uniqueItems", "container"],
)
def test_a_wide_integer_in_a_failure_is_bounded_not_raised(
    schema: dict[str, Any], instance: object, code: str, shown: str
) -> None:
    (issue,) = issues(schema, instance)
    assert issue.code == code
    assert issue.message.startswith(shown)
    assert len(issue.message) < 160


@pytest.mark.parametrize(
    "number", [WIDE, -WIDE, 10**309, 10**65536 - 1], ids=["wide", "negative", "float", "edge"]
)
def test_an_integer_too_wide_for_a_float_is_checked_against_a_float_multiple(number: int) -> None:
    """Stock ``multipleOf`` divides by a float divisor as a float: past 1.8e308 it raised OverflowError."""
    nested = {"properties": {"n": {"items": {"multipleOf": 0.75}}}}
    assert issues({"multipleOf": 0.5}, number) == ()
    assert issues(nested, {"n": [number * 3]}) == ()
    assert issues({"multipleOf": 0.75}, number * 3) == ()
    (issue,) = issues({"multipleOf": 0.75}, number + 1)  # (number + 1) * 4 / 3 is not an integer
    assert issue.code == "multipleOf"
    assert issue.message.endswith("… is not a multiple of 0.75")
    assert len(issue.message) < 160
    assert codes(issues(nested, {"n": [number + 1]})) == [("/n/0", "multipleOf")]
    assert issues({"multipleOf": 3}, number * 3) == ()  # an integer divisor never took the float path


# 5404319552844595 / 2**54: the binary value of 0.3, whose numerator times 10**5000 is a multiple of it.
BINARY_POINT_THREE = (0.3).as_integer_ratio()[0] * 10**5000


@pytest.mark.parametrize(
    ("divisor", "number", "valid"),
    [
        (0.1, 10**5000, True),  # Fraction(0.1) is not 1/10: an exact binary divisor rejected it
        (0.1, -(10**5000) - 1, True),
        (0.3, BINARY_POINT_THREE, False),  # ... and accepted this non-multiple of 3/10
        (0.3, 3 * 10**5000, True),
        (0.75, 10**307, False),  # no overflow: the float quotient 1.33e307 was an integer, so accepted
        (0.75, 3 * 10**307, True),
        (0.75, 10**16, False),  # the first decades past 2**53 take the exact path as well
        (0.75, 3 * 10**16, True),
        (1e-5, 10**700 + 1, True),
        (1.5e-3, 10**309 + 1, False),  # 3/2000
        (2.5e3, 10**309 + 3, False),
    ],
    ids=[
        "0.1",
        "0.1-negative",
        "binary-0.3",
        "0.3",
        "0.75",
        "0.75-multiple",
        "2**53",
        "2**53-multiple",
        "exponent",
        "exponent-not",
        "large-float",
    ],
)
def test_a_wide_integer_uses_the_divisors_shortest_decimal_representation(
    divisor: float, number: int, valid: bool
) -> None:
    expected = [] if valid else [("", "multipleOf")]
    assert codes(issues({"multipleOf": divisor}, number)) == expected
    nested = {"properties": {"n": {"type": "array", "items": {"multipleOf": divisor}}}}
    assert codes(issues(nested, {"n": [number]})) == ([] if valid else [("/n/0", "multipleOf")])
    branches = {"anyOf": [{"type": "string"}, {"type": "integer", "multipleOf": divisor}]}
    assert codes(issues(branches, number)) == ([] if valid else [("", "anyOf"), ("", "multipleOf")])
    other = {"oneOf": [{"type": "string"}, {"multipleOf": divisor}]}
    assert (issues(other, number) == ()) is valid
    assert (issues({"not": {"multipleOf": divisor}}, number) == ()) is not valid


def test_multiple_of_checks_small_numbers_without_rounding_the_quotient() -> None:
    assert issues({"multipleOf": 0.75}, 9) == ()
    assert codes(issues({"multipleOf": 0.75}, 2**53)) == [("", "multipleOf")]
    assert issues({"multipleOf": 0.75}, 4.5) == ()
    assert issues({"multipleOf": 0.1}, 7) == ()
    (issue,) = issues({"multipleOf": 0.75}, 10)
    assert issue.message == "10 is not a multiple of 0.75"
    assert codes(issues({"multipleOf": 0.75}, -1.5e16)) == []
    assert codes(issues({"multipleOf": 0.75}, True)) == []  # a boolean is not a number
    (wide,) = issues({"multipleOf": 0.75}, 10**20)
    assert wide.message == "100000000000000000000 is not a multiple of 0.75"


class _FloatUnit(float, Enum):
    HALF = 0.5
    ONE = 1.0
    TENTH = 0.1
    THREE_TENTHS = 0.3
    NEXT_THREE_TENTHS = 0.30000000000000004


class _DisplayFloat(float):
    @override
    def __repr__(self) -> str:
        return "display-float-" + "x" * 400

    @override
    def __str__(self) -> str:
        return repr(self)

    @override
    def __float__(self) -> float:
        return 99.0


class _NumericDisplayFloat(_DisplayFloat):
    @override
    def __repr__(self) -> str:
        return "99.0"


@pytest.mark.parametrize("float_type", [_FloatUnit, _DisplayFloat, _NumericDisplayFloat])
@pytest.mark.parametrize("operand", ["instance", "divisor", "both"])
@pytest.mark.parametrize(
    ("number", "divisor", "valid"),
    [(1.0, 0.5, True), (0.5, 1, False), (0.3, 0.1, True), (0.30000000000000004, 0.1, False)],
)
def test_multiple_of_uses_the_builtin_float_value_despite_subclass_display_overrides(
    float_type: type[float], operand: str, number: float, divisor: int | float, valid: bool
) -> None:
    instance = float_type(number) if operand in {"instance", "both"} else number
    factor = float_type(divisor) if operand in {"divisor", "both"} else divisor
    schema = {"type": "number", "multipleOf": factor}
    uri = "urn:skm:shop:multiple:v1"
    registry = SchemaRegistry({uri: schema}, Registry())
    assert is_schema_type(instance, "number")
    assert registry.is_valid_schema(schema)
    found = issues(schema, instance)
    assert codes(found) == ([] if valid else [("", "multipleOf")])
    assert all(
        issue.schema_pointer == "/multipleOf" and len(issue.message) <= MESSAGE_LIMIT for issue in found
    )
    assert registry.validate(uri, instance) == found
    if valid:
        registry.require_valid(uri, instance)
    else:
        with pytest.raises(ValidationFailed) as raised:
            registry.require_valid(uri, instance)
        assert raised.value.details["issues"] == [issue.to_json() for issue in found]


def decimal_multiple(number: int | float, divisor: int | float) -> bool:
    """Independent oracle: integer cross multiplication of exact canonical decimal coefficients."""
    value = Decimal(repr(number)) if isinstance(number, float) else Decimal(number)
    factor = Decimal(repr(divisor)) if isinstance(divisor, float) else Decimal(divisor)
    numerator, denominator = value.as_integer_ratio()
    divisor_numerator, divisor_denominator = factor.as_integer_ratio()
    return (numerator * divisor_denominator) % (denominator * divisor_numerator) == 0


FLOAT_MAX_DECIMAL = 17976931348623157 * 10**292  # the decimal sys.float_info.max is written as


@pytest.mark.parametrize(
    ("divisor", "number", "valid"),
    [
        (2**1000 + 1, float(2**1000), False),  # the stock remainder rounded the divisor to 2**1000: accepted
        (2**1000 + 1, -float(2**1000), False),
        (2**53 + 1, float(2**53), False),  # the first integer no float holds rounds to 2**53 as well
        (2**53 + 1, -float(2**53), False),
        (2**53 + 1, float(2**53 + 2), False),
        (2**53 + 1, 1.5, False),
        (2**53 + 1, 5e-324, False),
        (10**16 + 1, 1e16, False),
        (2**1023 + 1, 2.0**1023, False),
        (10**300, 1e300, True),
        (10**300, -7e300, True),  # the stock remainder of the binary 7e300 rejected this decimal multiple
        (3 * 10**300, 3e300, True),
        (3 * 10**300, 1e300, False),
        (FLOAT_MAX_DECIMAL, sys.float_info.max, True),
        (FLOAT_MAX_DECIMAL, -sys.float_info.max, True),
        (10**309, 1e308, False),  # past the float range: the stock remainder raised OverflowError
        (10**309, sys.float_info.max, False),
        (2**1000 + 1, 0.0, True),
        (2**1000 + 1, -0.0, True),
        (10**309, -0.0, True),
    ],
    ids=[
        "2**1000",
        "2**1000-negative",
        "2**53",
        "2**53-negative",
        "2**53-next",
        "fraction",
        "subnormal",
        "10**16",
        "2**1023",
        "10**300",
        "10**300-decimal",
        "3e300",
        "3e300-not",
        "float-max",
        "float-max-negative",
        "past-range",
        "past-range-max",
        "zero",
        "negative-zero",
        "past-range-zero",
    ],
)
def test_a_float_is_a_multiple_of_an_integer_no_float_holds_as_the_decimal_it_is_written_as(
    divisor: int, number: float, valid: bool
) -> None:
    assert decimal_multiple(number, divisor) is valid
    expected = [] if valid else [("", "multipleOf")]
    assert codes(issues({"multipleOf": divisor}, number)) == expected
    nested = {"properties": {"n": {"type": "array", "items": {"multipleOf": divisor}}}}
    assert codes(issues(nested, {"n": [1.5, number]})) == [("/n/0", "multipleOf")] + (
        [] if valid else [("/n/1", "multipleOf")]
    )
    branches = {"anyOf": [{"type": "string"}, {"type": "number", "multipleOf": divisor}]}
    assert codes(issues(branches, number)) == ([] if valid else [("", "anyOf"), ("", "multipleOf")])
    other = {"oneOf": [{"type": "string"}, {"multipleOf": divisor}]}
    assert (issues(other, number) == ()) is valid
    deep = {"properties": {"n": {"oneOf": [{"type": "boolean"}, {"type": "number", "multipleOf": divisor}]}}}
    assert (issues(deep, {"n": number}) == ()) is valid
    assert (issues({"not": {"multipleOf": divisor}}, number) == ()) is not valid


@pytest.mark.parametrize("number", [float("inf"), float("-inf"), float("nan")], ids=["inf", "-inf", "nan"])
@pytest.mark.parametrize(
    "divisor",
    [2, 2.0, 0.1, 2**53 + 1, 2**1000 + 1, 10**309],
    ids=["int", "float", "decimal", "2**53", "2**1000", "past-range"],
)
def test_a_non_finite_float_is_no_multiple_of_a_positive_finite_divisor(
    divisor: int | float, number: float
) -> None:
    (issue,) = issues({"multipleOf": divisor}, number)
    assert issue.code == "multipleOf"
    assert issue.message == truncate(f"{number!r} is not a multiple of {divisor}", MESSAGE_LIMIT)


def test_a_float_failing_an_integer_no_float_holds_is_quoted_and_a_boolean_is_ignored() -> None:
    (issue,) = issues({"multipleOf": 2**53 + 1}, float(2**53))
    assert issue.message == "9007199254740992.0 is not a multiple of 9007199254740993"
    assert issues({"multipleOf": 2**53 + 1}, True) == ()  # a boolean is not a number
    assert issues({"multipleOf": 2**1000 + 1}, False) == ()
    assert codes(issues({"type": "number", "multipleOf": 2**53 + 1}, True)) == [("", "type")]


@pytest.mark.parametrize(
    ("divisor", "number", "valid"),
    [
        (2**1000, float(2**1000), False),  # the shortest decimal differs from the exact binary integer
        (2**53, float(2**53), True),
        (2**53, float(2**54), True),
        (2**53, float(2**53 + 2), False),
        (2**60, 3.0 * 2**60, False),
        (10**22, 1e22, True),
        (10**22, 1.5e22, False),
        (10, 1e23, True),
        (10, -7e300, True),
        (int(1e23), 1e23, False),
        (3, 4.5, False),
        (3, 9.0, True),
        (3, -0.0, True),
        (2, float("inf"), False),
    ],
)
def test_a_float_uses_its_shortest_decimal_even_when_the_integer_divisor_is_binary_exact(
    divisor: int, number: float, valid: bool
) -> None:
    if number != float("inf"):
        assert decimal_multiple(number, divisor) is valid
    assert (issues({"multipleOf": divisor}, number) == ()) is valid


@pytest.mark.parametrize(
    ("number", "divisor", "valid", "binary_valid"),
    [
        pytest.param(1e23, 10, True, False, id="float-int-false-refusal"),
        pytest.param(1e23, 10.0, True, False, id="float-float-equivalent-divisor"),
        pytest.param(1e23, int(1e23), False, True, id="float-int-false-acceptance"),
        pytest.param(10**23, 1e23, True, False, id="int-float"),
        pytest.param(float(2**1000), 2**1000, False, True, id="binary-power-instance"),
        pytest.param(2**1000, float(2**1000), False, True, id="binary-power-divisor"),
        pytest.param(-7e300, 10, True, False, id="negative"),
        pytest.param(0.3, 0.1, True, False, id="decimal-fractions"),
        pytest.param(0.30000000000000004, 0.1, False, False, id="no-tolerance"),
        pytest.param(7, 0.1, True, False, id="small-int"),
        pytest.param(3, 0.3, True, False, id="small-int-decimal-factor"),
        pytest.param(2**53 - 1, 0.75, False, False, id="below-old-threshold"),
        pytest.param(2**53, 0.75, False, False, id="at-old-threshold"),
        pytest.param(2**53 + 1, 0.75, True, True, id="above-old-threshold"),
        pytest.param(sys.float_info.max, 1e-308, True, False, id="overflowing-quotient"),
        pytest.param(1e-308, sys.float_info.max, False, False, id="underflowing-quotient"),
        pytest.param(1e23, 10**5000, False, False, id="wide-int-divisor"),
    ],
)
def test_multiple_of_uses_one_decimal_policy_for_all_int_and_float_pairs(
    number: int | float, divisor: int | float, valid: bool, binary_valid: bool
) -> None:
    assert decimal_multiple(number, divisor) is valid
    numerator, denominator = number.as_integer_ratio()
    factor_numerator, factor_denominator = divisor.as_integer_ratio()
    assert ((numerator * factor_denominator) % (denominator * factor_numerator) == 0) is binary_valid
    assert (issues({"multipleOf": divisor}, number) == ()) is valid
    branches = {"anyOf": [{"type": "string"}, {"type": "number", "multipleOf": divisor}]}
    assert codes(issues(branches, number)) == ([] if valid else [("", "anyOf"), ("", "multipleOf")])
    assert (issues({"oneOf": [{"type": "string"}, {"multipleOf": divisor}]}, number) == ()) is valid
    assert (issues({"not": {"multipleOf": divisor}}, number) == ()) is not valid


@pytest.mark.parametrize("divisor", [10, 10.0])
@pytest.mark.parametrize(
    ("number", "valid"),
    [(1e23, True), (-7e300, True), (0, True), (0.0, True), (-0.0, True), (1.5, False), (5e-324, False)],
)
def test_equivalent_integer_and_float_divisors_agree(
    divisor: int | float, number: int | float, valid: bool
) -> None:
    assert decimal_multiple(number, divisor) is valid
    assert (issues({"multipleOf": divisor}, number) == ()) is valid


@pytest.mark.parametrize(
    ("number", "divisor", "valid"),
    [
        (5e-324, 5e-324, True),
        (-5e-324, 5e-324, True),
        (1e-323, 5e-324, True),
        (5e-324, 1e-323, False),
        (1.5e-323, 5e-324, True),
        (1.5e-323, 1e-323, False),
        (1, 5e-324, True),
        (1, 1.5e-323, False),
        (0, 5e-324, True),
        (-0.0, 1.5e-323, True),
    ],
)
def test_multiple_of_subnormals_and_zero(number: int | float, divisor: float, valid: bool) -> None:
    assert decimal_multiple(number, divisor) is valid
    assert (issues({"multipleOf": divisor}, number) == ()) is valid


@pytest.mark.parametrize("external", [False, True], ids=["local-ref", "registry-ref"])
@pytest.mark.parametrize(
    ("number", "divisor", "valid"),
    [(1e23, 10, True), (1e23, int(1e23), False), (0.3, 0.1, True), (2**53, 0.75, False)],
)
def test_decimal_multiple_of_is_kept_through_nested_references(
    external: bool, number: int | float, divisor: int | float, valid: bool
) -> None:
    uri = "urn:skm:shop:multiple:v1"
    target = {"$schema": DIALECT, "$id": uri, "type": "number", "multipleOf": divisor}
    registry: Registry[Any] = Registry()
    if external:
        registry = registry.with_resource(uri, DRAFT202012.create_resource(target))
    reference = {"$ref": uri if external else "#/$defs/multiple"}
    schema = {
        "$schema": DIALECT,
        "$defs": {"multiple": target},
        "properties": {"n": {"items": {"anyOf": [{"type": "string"}, reference]}}},
    }
    found = SchemaValidator(schema, registry).issues({"n": ["ok", number]})
    assert codes(found) == ([] if valid else [("/n/1", "anyOf"), ("/n/1", "multipleOf")])
    if not valid:
        assert found[1].schema_pointer == "/properties/n/items/anyOf/1/multipleOf"
    assert target["$schema"] == DIALECT


@pytest.mark.parametrize(
    ("first", "second", "divisor", "first_valid", "float_valid"),
    [
        ("9007199254740993.0", "9007199254740992.0", 9007199254740993, True, False),
        ("1.0000000000000001e300", "1e300", 10**300, False, True),
    ],
)
def test_float_parsing_loses_source_precision_before_multiple_of(
    first: str, second: str, divisor: int, first_valid: bool, float_valid: bool
) -> None:
    """Shortest float text is a bounded interpretation; it cannot recover the original JSON number."""
    for token, valid in ((first, first_valid), (second, not first_valid)):
        numerator, denominator = Decimal(token).as_integer_ratio()
        assert (numerator % (denominator * divisor) == 0) is valid
    assert json.loads(first) == json.loads(second)
    for token in (first, second):
        assert (issues({"multipleOf": divisor}, json.loads(token)) == ()) is float_valid


@pytest.mark.parametrize("number", [True, False, None, "number", [], {}])
@pytest.mark.parametrize("divisor", [10, 10.0, 0.1])
def test_multiple_of_still_ignores_non_numeric_instances(number: object, divisor: int | float) -> None:
    assert issues({"multipleOf": divisor}, number) == ()


@pytest.mark.parametrize(
    "divisor", [0, 0.0, -2, -2.0, True, False, float("inf"), float("-inf"), float("nan")]
)
def test_invalid_divisors_keep_the_stock_behavior(divisor: object) -> None:
    """Invalid schemas are outside the positive finite divisor contract; do not redefine their behavior."""
    stock = Draft202012Validator({"multipleOf": divisor})
    try:
        valid = stock.is_valid(6.0)
    except (ZeroDivisionError, ValueError) as exc:
        with pytest.raises(type(exc)):
            issues({"multipleOf": divisor}, 6.0)
    else:
        assert (issues({"multipleOf": divisor}, 6.0) == ()) is valid


def test_multiple_of_does_not_change_the_interpreter_integer_text_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_change(_limit: int) -> None:
        pytest.fail("multipleOf must not change the interpreter integer text limit")

    before = sys.get_int_max_str_digits()
    monkeypatch.setattr(sys, "set_int_max_str_digits", refuse_change)
    assert issues({"multipleOf": WIDE}, 0.0) == ()
    assert codes(issues({"multipleOf": WIDE}, 1e23)) == [("", "multipleOf")]
    assert issues({"multipleOf": 0.1}, WIDE) == ()
    assert codes(issues({"multipleOf": 0.75}, 2**53)) == [("", "multipleOf")]
    assert sys.get_int_max_str_digits() == before


@pytest.mark.parametrize(
    ("schema", "number", "valid"),
    [
        ({"multipleOf": 2}, 10, True),
        ({"multipleOf": 2}, 7, False),
        ({"multipleOf": 2}, "foo", True),
        ({"multipleOf": 1.5}, 0, True),
        ({"multipleOf": 1.5}, 4.5, True),
        ({"multipleOf": 1.5}, 35, False),
        ({"multipleOf": 0.0001}, 0.0075, True),
        ({"multipleOf": 0.0001}, 0.00751, False),
        ({"type": "integer", "multipleOf": 0.123456789}, 1e308, False),
        ({"type": "integer", "multipleOf": 1e-8}, 12391239123, True),
    ],
)
def test_multiple_of_keeps_the_standard_suite_results(
    schema: dict[str, Any], number: object, valid: bool
) -> None:
    assert (issues(schema, number) == ()) is valid


def _nested(depth: int, innermost: object) -> object:
    value = innermost
    for _ in range(depth):
        value = [value]
    return value


@pytest.mark.parametrize("innermost", [[], 1, WIDE], ids=["empty", "small", "wide"])
@pytest.mark.parametrize(
    "schema",
    [
        {},
        {"type": "array"},
        {"anyOf": [{"type": "string"}, {"type": "array"}]},
        {"oneOf": [{"type": "object"}, {"type": "array", "minItems": 1}]},
    ],
    ids=["empty", "type", "anyOf", "oneOf"],
)
def test_a_deep_nesting_the_schema_never_descends_into_is_valid(
    schema: dict[str, Any], innermost: object
) -> None:
    """The wide-integer walk must not exhaust the stack and report a ``$ref`` recursion."""
    deep = _nested(1100, innermost)
    assert issues(schema, deep) == ()
    assert issues(schema, [deep, {"a": deep}]) == ()
    assert issues({"properties": {"a": schema}}, {"a": deep, "b": [deep]}) == ()


def test_a_deep_nesting_still_fails_where_the_schema_rejects_it() -> None:
    deep = _nested(1100, [])
    assert codes(issues({"anyOf": [{"type": "string"}, {"type": "object"}]}, deep))[0] == ("", "anyOf")
    assert codes(issues({"type": "array", "maxItems": 0}, deep)) == [("", "maxItems")]
    (issue,) = issues({"type": "string"}, _nested(1100, WIDE))
    assert issue.code == "type"
    assert len(issue.message) < 160


def test_a_shared_container_is_made_text_safe_everywhere_it_appears() -> None:
    shared = [WIDE]
    found = issues({"items": {"items": {"type": "string"}}}, [shared, [shared], shared])
    assert codes(found) == [("/0/0", "type"), ("/1/0", "type"), ("/2/0", "type")]
    assert all(len(issue.message) < 160 for issue in found)


def test_integers_below_the_text_limit_keep_their_exact_message() -> None:
    (issue,) = issues({"type": "string"}, 10**639)
    assert issue.message == "1" + "0" * 78 + "… is not of type 'string'"
    assert issues({"type": "string"}, 123)[0].message == "123 is not of type 'string'"
    assert issues({"const": 10**640}, 10**640) == ()
    assert codes(issues({"const": 5}, WIDE)) == [("", "const")]
    assert issues({"type": "integer", "minimum": 10**639}, WIDE) == ()


# --- a wide integer written in the schema itself (const/enum/bounds, a quoted oneOf/not branch)

SHOWN = "7" * 79 + "…"  # the leading digits of WIDE and of its neighbours WIDE ± 1
# sys.set_int_max_str_digits: the lowest accepted limit, the default, off
LIMITS = pytest.mark.parametrize("limit", [640, 4300, 0], ids=["lowest", "default", "off"])


@contextmanager
def int_text_limit(limit: int) -> Iterator[None]:
    before = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(limit)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(before)


@LIMITS
@pytest.mark.parametrize(
    ("schema", "equal", "unequal", "code", "message"),
    [
        ({"const": WIDE}, WIDE, WIDE + 1, "const", f"{SHOWN} was expected"),
        ({"const": -WIDE}, -WIDE, WIDE, "const", "-" + "7" * 78 + "… was expected"),
        ({"const": WIDE}, WIDE, 1e308, "const", f"{SHOWN} was expected"),
        ({"const": {"n": [WIDE]}}, {"n": [WIDE]}, {"n": [WIDE + 10]}, "const", "{'n': [" + "7" * 72 + "…"),
        ({"enum": [1, WIDE]}, WIDE, WIDE - 1, "enum", f"{SHOWN} is not one of [1, {SHOWN}]"),
        ({"maximum": WIDE}, WIDE, WIDE + 1, "maximum", f"{SHOWN} is greater than the maximum of {SHOWN}"),
        ({"maximum": WIDE}, 1e308, WIDE + 1, "maximum", f"{SHOWN} is greater than the maximum of {SHOWN}"),
        ({"minimum": -WIDE}, -WIDE, -WIDE - 1, "minimum", "-" + "7" * 78 + "… is less than the minimum"),
        ({"exclusiveMaximum": WIDE}, WIDE - 1, WIDE, "exclusiveMaximum", f"{SHOWN} is greater than or equal"),
        ({"exclusiveMinimum": WIDE}, WIDE + 1, WIDE, "exclusiveMinimum", f"{SHOWN} is less than or equal"),
        ({"multipleOf": WIDE}, 3 * WIDE, WIDE + 1, "multipleOf", f"{SHOWN} is not a multiple of {SHOWN}"),
        ({"multipleOf": WIDE}, 0.0, 5.5, "multipleOf", f"5.5 is not a multiple of {SHOWN}"),
        ({"multipleOf": WIDE}, -0.0, float("inf"), "multipleOf", f"inf is not a multiple of {SHOWN}"),
        ({"const": 10**65536 - 1}, 10**65536 - 1, 1, "const", "9" * 79 + "… was expected"),
    ],
    ids=[
        "const",
        "const-negative",
        "const-float",
        "const-container",
        "enum",
        "maximum",
        "maximum-float",
        "minimum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "multipleOf",
        "multipleOf-float",
        "multipleOf-inf",
        "edge",
    ],
)
def test_a_wide_schema_literal_is_compared_exactly_and_quoted_by_its_leading_digits(
    limit: int, schema: dict[str, Any], equal: object, unequal: object, code: str, message: str
) -> None:
    """``repr`` of a literal past the int-to-text limit raised ValueError while jsonschema built a message
    (and a float ``%`` a wide divisor raised OverflowError)."""
    with int_text_limit(limit):
        assert issues(schema, equal) == ()
        (issue,) = issues(schema, unequal)
        assert (issue.pointer, issue.code, issue.schema_pointer) == ("", code, f"/{code}")
        assert issue.message.startswith(message)
        assert len(issue.message) < 240  # two numbers of at most 80 characters and the keyword's text
        nested = {"properties": {"n": {"type": "array", "items": schema}}}
        assert issues(nested, {"n": [equal]}) == ()
        assert codes(issues(nested, {"n": [equal, unequal]})) == [("/n/1", code)]


@LIMITS
def test_a_failing_branch_with_a_wide_literal_keeps_any_of_and_one_of(limit: int) -> None:
    any_of = {"anyOf": [{"const": WIDE}, {"maximum": -WIDE}, {"type": "string"}]}
    one_of = {"oneOf": [{"maximum": WIDE}, {"type": "integer"}]}
    with int_text_limit(limit):
        for number in (WIDE, -WIDE - 1, "x"):
            assert issues(any_of, number) == ()
        assert codes(issues(any_of, 5)) == [("", "anyOf")]
        assert codes(issues(any_of, WIDE + 1)) == [("", "anyOf")]
        assert issues(one_of, WIDE + 1) == ()  # exactly one branch: only the type matches
        assert issues(one_of, "x") == ()  # exactly one branch: maximum ignores a string
        (issue,) = issues(one_of, WIDE)  # both branches match, and the message quotes both schemas
        assert issue.code == "oneOf"
        assert issue.message.startswith(f"{SHOWN} is valid under each of ")
        assert "{'maximum': " + "7" * 50 in issue.message
        assert issues({"not": {"const": WIDE}}, 5) == ()
        (negated,) = issues({"not": {"const": WIDE}}, WIDE)
        assert negated.message.startswith(f"{SHOWN} should not be valid under {{'const': {SHOWN[:30]}")


@LIMITS
def test_a_wide_literal_reached_through_a_reference_or_a_count_is_quoted_safely(limit: int) -> None:
    schema = {
        "$defs": {"big": {"const": WIDE}, "few": {"contains": {"type": "integer"}, "minContains": WIDE}},
        "properties": {"n": {"items": {"$ref": "#/$defs/big"}}, "m": {"$ref": "#/$defs/few"}},
    }
    with int_text_limit(limit):
        assert issues(schema, {"n": [WIDE, WIDE], "m": "not an array"}) == ()
        found = issues(schema, {"n": [WIDE, 5], "m": [1]})
        assert codes(found) == [("/m", "minContains"), ("/n/1", "const")]
        expected = f"Too few items match the given schema (expected at least {SHOWN} but only 1 matched)"
        assert found[0].message == expected
        assert found[1].message == f"{SHOWN} was expected"
        assert issues({"contains": {}, "maxContains": WIDE}, [1, 2]) == ()


def test_a_wide_literal_does_not_change_the_original_schema() -> None:
    schema: dict[str, Any] = {"$schema": DIALECT, "properties": {"n": {"enum": [WIDE, 1]}}, "const": {"n": 1}}
    before = copy.deepcopy(schema)
    validator = SchemaValidator(schema, Registry())
    assert codes(validator.issues({"n": 2})) == [("", "const"), ("/n", "enum")]
    assert schema == before
    assert type(schema["properties"]["n"]["enum"][0]) is int  # the caller's literal is not replaced
    safe = without_dialect(schema)
    assert safe["properties"]["n"]["enum"] == [WIDE, 1]  # the copy holds the same values
    assert repr(safe["properties"]["n"]["enum"][0]) == SHOWN
    assert without_dialect(safe) == safe  # converting again changes nothing


@LIMITS
def test_a_float_against_a_wide_divisor_literal_is_its_decimal_and_quoted_safely(limit: int) -> None:
    with int_text_limit(limit):
        assert issues({"multipleOf": 10**5000}, 0.0) == ()
        (issue,) = issues({"multipleOf": 10**5000}, 7e300)
        assert issue.message == "7e+300 is not a multiple of " + "1" + "0" * 78 + "…"
        found = issues({"oneOf": [{"type": "string"}, {"multipleOf": WIDE}]}, 1e300)
        assert codes(found)[0] == ("", "oneOf")
        assert all(len(issue.message) < 240 for issue in found)


def test_schema_literals_below_the_text_limit_keep_their_exact_message() -> None:
    assert issues({"const": 5}, 6)[0].message == "5 was expected"
    assert issues({"enum": [1, 2]}, 3)[0].message == "3 is not one of [1, 2]"
    assert issues({"maximum": 10}, 11)[0].message == "11 is greater than the maximum of 10"
    assert issues({"multipleOf": 3}, 4.5)[0].message == "4.5 is not a multiple of 3"
    with int_text_limit(640):
        (issue,) = issues({"const": 10**639}, 5)  # 640 digits: still written in full, then truncated
        assert issue.message == truncate(f"{10**639} was expected", MESSAGE_LIMIT)
        assert issues({"const": 10**640}, 5)[0].message == "1" + "0" * 78 + "… was expected"


def test_unresolvable_reference_is_an_issue_not_a_fetch() -> None:
    found = issues({"properties": {"a": {"$ref": "urn:skm:ghost:missing:v1"}}}, {"a": 1})
    assert [i.code for i in found] == ["$ref"]
    assert "urn:skm:ghost:missing:v1" in found[0].message
