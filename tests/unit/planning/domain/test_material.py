"""Materials: document round trip; ``retrieved_at`` keeps the fraction digits it was written with."""

import copy
import dataclasses
import json
import pickle
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from skm.modules.planning.domain.material import Material, material_from_doc, material_to_doc
from skm.modules.planning.domain.reads import Timestamp, format_timestamp, parse_timestamp

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/auth-refresh.specification.json"
FRACTIONS = ("", ".0", ".5", ".50", ".120", ".0001", ".00000", ".000000", ".123456", ".999999")
PARIS = ZoneInfo("Europe/Paris")
# Paris at its 2026 clock changes: the first and the second 02:30 of 25 October, 03:30 after 29 March's gap
ACROSS_DST = ("2026-10-25T00:30:00.5Z", "2026-10-25T01:30:00.5Z", "2026-03-29T01:30:00.120Z")


def _external() -> dict[str, Any]:
    doc = json.loads(EXAMPLE.read_text())
    return next(m for m in doc["materials"] if m["key"] == "oauth-threats")


def _material(retrieved_at: str) -> Material:
    return material_from_doc({**_external(), "retrieved_at": retrieved_at})


def _retrieved_at(material: Material) -> datetime:
    assert material.retrieved_at is not None
    return material.retrieved_at


def _copies[T](value: T) -> list[T]:
    """``value`` through ``copy``, ``deepcopy`` and every pickle protocol."""
    pickled = [pickle.loads(pickle.dumps(value, p)) for p in range(pickle.HIGHEST_PROTOCOL + 1)]  # noqa: S301
    return [copy.copy(value), copy.deepcopy(value), *pickled]


def test_the_owner_example_round_trips():
    doc = _external()
    assert material_to_doc(material_from_doc(doc)) == doc


@pytest.mark.parametrize("fraction", FRACTIONS)
def test_retrieved_at_keeps_the_fraction_digits_it_was_written_with(fraction):
    text = f"2026-10-21T10:00:00{fraction}Z"
    material = _material(text)
    assert material_to_doc(material)["retrieved_at"] == text
    assert material_to_doc(material_from_doc(material_to_doc(material)))["retrieved_at"] == text
    value = _retrieved_at(material)
    assert isinstance(value, datetime)
    assert value.utcoffset() == timedelta(0)
    assert value == datetime.fromisoformat(text)


def test_precision_is_part_of_the_text_not_of_the_instant():
    short = _retrieved_at(_material("2026-10-21T10:00:00.5Z"))
    padded = _retrieved_at(_material("2026-10-21T10:00:00.500000Z"))
    assert short == padded == datetime(2026, 10, 21, 10, 0, 0, 500000, tzinfo=UTC)
    assert hash(short) == hash(padded)
    assert short - padded == timedelta(0)


def test_copies_keep_the_written_text_and_the_value_is_immutable():
    material = _material("2026-10-21T10:00:00.120Z")
    deep = copy.deepcopy(material)
    assert _retrieved_at(deep) is not _retrieved_at(material)
    for twin in (copy.copy(material), deep):
        assert material_to_doc(twin)["retrieved_at"] == "2026-10-21T10:00:00.120Z"
    with pytest.raises(AttributeError):
        _retrieved_at(material)._fraction_digits = 6  # type: ignore[attr-defined]
    assert material_to_doc(material)["retrieved_at"] == "2026-10-21T10:00:00.120Z"


def test_a_timestamp_never_holds_fewer_digits_than_its_instant_needs():
    moment = datetime(2026, 10, 21, 10, 0, 0, 120000, tzinfo=UTC)
    assert Timestamp.of(moment, 2).fraction_digits == 2
    for digits in (1, -1, 7):
        with pytest.raises(ValueError, match="fraction digits"):
            Timestamp.of(moment, digits)


def test_computed_datetimes_keep_the_plain_rendering():
    material = _material("2026-10-21T10:00:00.5Z")
    later = _retrieved_at(material) + timedelta(seconds=1)  # a computed instant has no written text
    rendered = [
        material_to_doc(dataclasses.replace(material, retrieved_at=value))["retrieved_at"]
        for value in (
            later,
            datetime(2026, 10, 21, 10, tzinfo=UTC),
            datetime(2026, 10, 21, 12, 0, 0, 120000, tzinfo=timezone(timedelta(hours=2))),
        )
    ]
    assert rendered == ["2026-10-21T10:00:01.500000Z", "2026-10-21T10:00:00Z", "2026-10-21T10:00:00.120000Z"]


@pytest.mark.parametrize("fraction", FRACTIONS)
def test_every_copy_of_a_written_timestamp_keeps_its_text(fraction):
    text = f"2026-10-25T01:30:00{fraction}Z"
    written = _retrieved_at(_material(text))
    for twin in _copies(written):
        assert type(twin) is Timestamp
        assert (twin.tzinfo, twin.fold, twin.fraction_digits) == (UTC, 0, len(fraction.removeprefix(".")))
        assert format_timestamp(twin) == text


@pytest.mark.parametrize("text", ACROSS_DST)
def test_every_copy_of_a_converted_timestamp_keeps_its_zone_fold_and_arithmetic(text):
    converted = parse_timestamp(text).astimezone(PARIS)
    assert isinstance(converted, Timestamp)
    assert converted.fraction_digits is None  # a converted value is computed: it has no written text
    for twin in _copies(converted):
        assert type(twin) is Timestamp
        assert (twin.tzinfo, twin.fold, twin.fraction_digits) == (PARIS, converted.fold, None)
        assert twin.utcoffset() == converted.utcoffset()
        assert twin.astimezone(UTC) == converted.astimezone(UTC) == datetime.fromisoformat(text)
        # arithmetic moves the wall time in Paris, not in UTC: a copy that fell back to UTC lands elsewhere
        for delta in (timedelta(hours=1), timedelta(hours=-1), timedelta(days=1)):
            assert format_timestamp(twin + delta) == format_timestamp(converted + delta)
            assert (twin + delta).utcoffset() == (converted + delta).utcoffset()
        assert format_timestamp(twin) == format_timestamp(converted)


def test_every_copy_of_a_material_keeps_a_converted_retrieved_at():
    material = _material("2026-10-25T01:30:00.5Z")
    local = dataclasses.replace(material, retrieved_at=_retrieved_at(material).astimezone(PARIS))
    for twin in _copies(local):
        twin_at = _retrieved_at(twin)
        assert (twin_at.tzinfo, twin_at.hour, twin_at.fold) == (PARIS, 2, 1)  # the second 02:30
        assert twin == local
        assert material_to_doc(twin) == material_to_doc(local)
        assert material_to_doc(twin)["retrieved_at"] == "2026-10-25T01:30:00.500000Z"
