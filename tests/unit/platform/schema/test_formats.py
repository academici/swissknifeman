"""The own FormatChecker: positive and negative table per format (kernel-platform §3.3)."""

import pytest

from skm.platform.schema.formats import FORMAT_CHECKER, KNOWN_FORMATS

VALID = {
    "date-time": [
        "2026-10-25T14:03:11Z",
        "2026-10-25T14:03:11.123456Z",
        "2026-10-25T14:03:11+03:00",
        "2026-10-25T14:03:11.5-05:30",
    ],
    "date": ["2026-10-25", "2024-02-29"],
    "uuid": [
        "0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07",
        "0191E2A4-7C3F-7B21-8A54-3F6D2C1B9E07",
    ],
    "uri": ["https://example.com/a?b=c", "urn:skm:kernel:defs:v1", "file:///tmp/x", "mailto:a@b.co"],
    "email": ["a@b.co", "first.last@example.com"],
    "duration-seconds": ["0", "30", "007"],
    "regex": ["^[a-z]+$", "(?P<name>x)+"],
}
INVALID = {
    "date-time": [
        "2026-10-25 14:03:11Z",
        "2026-10-25T14:03:11",
        "2026-10-25T14:03:11+0300",
        "2026-10-25",
        "2026-13-25T14:03:11Z",
        "2026-10-25t14:03:11z",
        "2026-10-25T24:00:00Z",
        "",
    ],
    "date": ["2026-02-30", "20261025", "2026-1-5", "2026-10-25T00:00:00", " 2026-10-25", "2026-10-25\n", ""],
    "uuid": [
        "0191e2a47c3f7b218a543f6d2c1b9e07",
        "{0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07}",
        "urn:uuid:0191e2a4-7c3f-7b21-8a54-3f6d2c1b9e07",
        "not-a-uuid",
        "",
    ],
    "uri": ["example.com", "/relative/path", "https://exa mple.com", "1http://x", "http://[::1", ""],
    "email": ["a", "@b.co", "a@", "a@@b", "a b@c.d", "a@b c", ""],
    "duration-seconds": ["-1", "1.5", "1e3", " 1", "", "١٢", "5\n"],
    "regex": ["(", "[a-"],
}


def test_every_known_format_has_a_table() -> None:
    assert KNOWN_FORMATS == frozenset(VALID) == frozenset(INVALID)


@pytest.mark.parametrize(("name", "value"), [(n, v) for n, values in VALID.items() for v in values])
def test_valid_values_conform(name: str, value: str) -> None:
    assert FORMAT_CHECKER.conforms(value, name)


@pytest.mark.parametrize(("name", "value"), [(n, v) for n, values in INVALID.items() for v in values])
def test_invalid_values_do_not_conform(name: str, value: str) -> None:
    assert not FORMAT_CHECKER.conforms(value, name)


@pytest.mark.parametrize("name", sorted(KNOWN_FORMATS))
@pytest.mark.parametrize("value", [None, 5, 1.5, True, [], {}])
def test_non_strings_are_not_this_keywords_concern(name: str, value: object) -> None:
    assert FORMAT_CHECKER.conforms(value, name)


def test_checker_holds_only_the_documented_formats() -> None:
    assert "hostname" not in FORMAT_CHECKER.checkers
    assert "ipv4" not in FORMAT_CHECKER.checkers
