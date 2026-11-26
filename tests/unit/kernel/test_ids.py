"""UUIDv7 construction, extraction and strict parsing (kernel-platform §2.2, ADR 0007)."""

from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.ids import (
    UUID7_MAX_RAND_A,
    UUID7_MAX_RAND_B,
    UUID7_MAX_UNIX_MS,
    parse_uuid,
    uuid7,
    uuid7_timestamp_ms,
)

unix_ms_values = st.integers(min_value=0, max_value=UUID7_MAX_UNIX_MS)
rand_a_values = st.integers(min_value=0, max_value=UUID7_MAX_RAND_A)
rand_b_values = st.integers(min_value=0, max_value=UUID7_MAX_RAND_B)


@given(unix_ms_values, rand_a_values, rand_b_values)
def test_uuid7_has_version_7_and_rfc_variant(unix_ms: int, rand_a: int, rand_b: int) -> None:
    value = uuid7(unix_ms, rand_a, rand_b)

    assert value.version == 7
    assert value.variant == "specified in RFC 4122"
    assert (value.int >> 62) & 0b11 == 0b10


@given(unix_ms_values, rand_a_values, rand_b_values)
def test_uuid7_round_trips_fields(unix_ms: int, rand_a: int, rand_b: int) -> None:
    value = uuid7(unix_ms, rand_a, rand_b)

    assert uuid7_timestamp_ms(value) == unix_ms
    assert (value.int >> 64) & UUID7_MAX_RAND_A == rand_a
    assert value.int & UUID7_MAX_RAND_B == rand_b
    assert parse_uuid(str(value)) == value


@given(unix_ms_values, unix_ms_values, rand_a_values, rand_b_values, rand_a_values, rand_b_values)
def test_uuid7_orders_by_time(ms1: int, ms2: int, a1: int, b1: int, a2: int, b2: int) -> None:
    first, second = uuid7(ms1, a1, b1), uuid7(ms2, a2, b2)

    if ms1 < ms2:
        assert first < second
        assert str(first) < str(second)


@given(
    unix_ms_values,
    st.tuples(rand_a_values, rand_b_values),
    st.tuples(rand_a_values, rand_b_values),
)
def test_uuid7_differs_with_entropy(
    unix_ms: int, entropy1: tuple[int, int], entropy2: tuple[int, int]
) -> None:
    first, second = uuid7(unix_ms, *entropy1), uuid7(unix_ms, *entropy2)

    assert (first == second) == (entropy1 == entropy2)


def test_uuid7_is_pure() -> None:
    assert uuid7(1, 2, 3) == uuid7(1, 2, 3)


def test_uuid7_known_vector() -> None:
    assert uuid7(0x017F22E279B0, 0xCC3, 0x18C4DC0C0C07398F) == UUID("017f22e2-79b0-7cc3-98c4-dc0c0c07398f")


def test_uuid7_boundaries_are_accepted() -> None:
    low = uuid7(0, 0, 0)
    high = uuid7(UUID7_MAX_UNIX_MS, UUID7_MAX_RAND_A, UUID7_MAX_RAND_B)

    assert str(low) == "00000000-0000-7000-8000-000000000000"
    assert str(high) == "ffffffff-ffff-7fff-bfff-ffffffffffff"


@pytest.mark.parametrize(
    ("unix_ms", "rand_a", "rand_b"),
    [
        (-1, 0, 0),
        (UUID7_MAX_UNIX_MS + 1, 0, 0),
        (0, -1, 0),
        (0, UUID7_MAX_RAND_A + 1, 0),
        (0, 0, -1),
        (0, 0, UUID7_MAX_RAND_B + 1),
    ],
)
def test_uuid7_rejects_out_of_range(unix_ms: int, rand_a: int, rand_b: int) -> None:
    with pytest.raises(ValueError, match="must be in"):
        uuid7(unix_ms, rand_a, rand_b)


@pytest.mark.parametrize("bad", [True, 1.0, "1", None])
def test_uuid7_rejects_non_int(bad: object) -> None:
    with pytest.raises(TypeError):
        uuid7(bad, 0, 0)  # type: ignore[arg-type]


def test_timestamp_rejects_other_versions() -> None:
    with pytest.raises(ValueError, match="not a UUIDv7"):
        uuid7_timestamp_ms(uuid4())
    with pytest.raises(ValueError, match="not a UUIDv7"):
        uuid7_timestamp_ms(UUID(int=0))


def test_timestamp_rejects_non_rfc_variant_with_version_bits() -> None:
    foreign = UUID("017f22e2-79b0-7cc3-c8c4-dc0c0c07398f")  # variant 0b11

    with pytest.raises(ValueError, match="not a UUIDv7"):
        uuid7_timestamp_ms(foreign)


@given(st.uuids())
def test_parse_uuid_accepts_canonical_forms(value: UUID) -> None:
    assert parse_uuid(str(value)) == value
    assert parse_uuid(str(value).upper()) == value


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{017f22e2-79b0-7cc3-98c4-dc0c0c07398f}",
        "urn:uuid:017f22e2-79b0-7cc3-98c4-dc0c0c07398f",
        "017f22e279b07cc398c4dc0c0c07398f",
        "017f22e2-79b0-7cc3-98c4-dc0c0c07398",
        "017f22e2-79b0-7cc3-98c4-dc0c0c07398f0",
        " 017f22e2-79b0-7cc3-98c4-dc0c0c07398f",
        "017f22e2-79b0-7cc3-98c4-dc0c0c07398f\n",
        "017f22e2-79b0-7cc3-98c4-dc0c0c07398g",
        "017f22e2_79b0_7cc3_98c4_dc0c0c07398f",
        "017f22e-279b0-7cc3-98c4-dc0c0c07398f",
    ],
)
def test_parse_uuid_rejects_non_canonical(text: str) -> None:
    with pytest.raises(ValueError, match="not a canonical UUID"):
        parse_uuid(text)


def test_parse_uuid_rejects_non_str() -> None:
    with pytest.raises(TypeError):
        parse_uuid(b"017f22e2-79b0-7cc3-98c4-dc0c0c07398f")  # type: ignore[arg-type]
