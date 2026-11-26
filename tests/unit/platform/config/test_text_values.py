"""Typed text scenarios ported from aicore; v2 additionally supports CSV typed arrays and maps."""

from dataclasses import replace
from pathlib import Path
from runpy import run_path

import pytest

from skm.kernel.errors import ValidationFailed
from skm.platform.config.sources.text_values import parse_text_value

h = run_path(str(Path(__file__).with_name("test_resolver.py")))


@pytest.fixture
def registry(tmp_path):
    return h["build_registry"](tmp_path)


@pytest.mark.parametrize(
    ("key", "text", "expected"),
    [
        ("size", "+007", 7),
        ("size", " -12 ", -12),
        ("ratio", "1.25e+2", 125.0),
        ("ratio", ".5", 0.5),
        ("note", ' "literal" ', ' "literal" '),
        ("note", "true", "true"),
        ("tags", ' ["one", "two"] ', ["one", "two"]),
        ("tags", " one, two , three ", ["one", "two", "three"]),
        ("tags", " ", []),
        ("token", "secret://env/TOKEN", "secret://env/TOKEN"),
    ],
)
def test_parse_declared_type(registry, key, text, expected):
    assert parse_text_value(registry.spec(f"demo.{key}"), text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("TRUE", True),
        ("1", True),
        ("Yes", True),
        ("ON", True),
        ("false", False),
        ("0", False),
        ("NO", False),
        ("off", False),
    ],
)
def test_boolean_vocabulary(registry, text, expected):
    spec = replace(registry.spec("demo.note"), value_schema={"type": "boolean"})
    assert parse_text_value(spec, text) is expected


def test_csv_items_are_typed_and_objects_require_json(registry):
    spec = replace(registry.spec("demo.tags"), value_schema={"type": "array", "items": {"type": "integer"}})
    assert parse_text_value(spec, "1, -2, +3") == [1, -2, 3]
    spec = replace(spec, value_schema={"type": "object"})
    assert parse_text_value(spec, '{"a": {"$unset": true}, "b": 1}') == {"a": {"$unset": True}, "b": 1}
    with pytest.raises(ValidationFailed, match="CONFIG_INVALID"):
        parse_text_value(spec, "a=1")


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("size", "1.0"),
        ("size", "1e2"),
        ("size", "0x10"),
        ("size", "true"),
        ("size", "\uff11\uff12"),  # Non-ASCII digits must not pass the integer grammar.
        ("ratio", "NaN"),
        ("ratio", "Infinity"),
        ("ratio", "1e9999"),
        ("tags", "[broken secret value"),
        ("tags", "[NaN]"),
    ],
)
def test_parse_errors_are_structured_and_do_not_quote_text(registry, key, text):
    with pytest.raises(ValidationFailed) as caught:
        parse_text_value(registry.spec(f"demo.{key}"), text)
    assert caught.value.code == "CONFIG_INVALID"
    assert caught.value.details["key"] == f"demo.{key}"
    assert caught.value.details["reason"] == "text_value"
    assert text not in str(caught.value.to_problem())


def test_json_null_is_not_the_text_string_null(registry):
    assert parse_text_value(registry.spec("demo.label"), "null") == "null"


def test_boolean_rejects_unknown_words(registry):
    spec = replace(registry.spec("demo.note"), value_schema={"type": "boolean"})
    with pytest.raises(ValidationFailed):
        parse_text_value(spec, "maybe")
