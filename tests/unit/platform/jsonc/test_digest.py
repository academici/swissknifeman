"""Digest/v1 donor vectors, deterministic projections and provenance checks."""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.platform.jsonc.canonical import canonical_bytes
from skm.platform.jsonc.digest import TAG, digest, digest_bytes, digest_json, is_tagged_digest, sha256_hex
from support import golden

VECTORS_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "digest" / "vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))["vectors"]
JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(),
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(), children, max_size=5),
    max_leaves=20,
)


@pytest.mark.parametrize(
    ("value", "canonical", "expected"),
    [(vector["input"], vector["canonical"], vector["digest"]) for vector in VECTORS],
    ids=[vector["name"] for vector in VECTORS],
)
def test_every_legacy_digest_vector(value: object, canonical: str, expected: str) -> None:
    assert digest(value) == expected
    assert digest_bytes(canonical.encode("utf-8")) == expected
    assert sha256_hex(canonical.encode("utf-8")) == expected.removeprefix(TAG)
    assert is_tagged_digest(expected)
    assert digest(value) == digest(value)
    if isinstance(value, Mapping):
        assert digest_json(value) == expected


def test_fixture_is_the_complete_byte_identical_donor_snapshot() -> None:
    source = golden.assert_legacy_source(VECTORS_PATH)
    assert "source: packages/aicore/schemas/digest/v1/vectors.json\n" in source
    assert "snapshot-sha256: de6d74a9817c10c9ede14703ca5511b12a5c49f642bbfb42dbaea9d6c2c054eb\n" in source
    assert len(VECTORS) == len({vector["name"] for vector in VECTORS}) == 8


def _reverse_objects(value: object) -> object:
    if isinstance(value, dict):
        return {key: _reverse_objects(item) for key, item in reversed(value.items())}
    if isinstance(value, list):
        return [_reverse_objects(item) for item in value]
    return value


@given(value=st.dictionaries(st.text(), JSON_VALUES, max_size=8), data=st.data())
def test_key_permutations_at_every_depth_leave_the_digest_unchanged(
    value: dict[str, object], data: st.DataObject
) -> None:
    original = deepcopy(value)
    keys = data.draw(st.permutations(tuple(value)))
    permuted = {key: _reverse_objects(value[key]) for key in keys}
    assert digest(permuted) == digest(value) == digest_json(MappingProxyType(value))
    assert canonical_bytes(permuted) == canonical_bytes(value)
    assert value == original


def test_exclusions_are_explicit_top_level_only_and_do_not_mutate() -> None:
    document = {
        "digest": "old",
        "updated_at": "old-time",
        "z": "привет",
        "a": {"digest": "nested", "updated_at": "nested-time", "n": 1},
    }
    original = deepcopy(document)
    projection = {"z": "привет", "a": document["a"]}
    excluded = (key for key in ("digest", "updated_at", "absent"))
    expected = digest(projection)
    assert digest_json(MappingProxyType(document), exclude_keys=excluded) == expected
    assert digest_json(document) != expected
    assert document == original
    document["digest"] = expected
    assert digest_json(document, exclude_keys=("digest", "updated_at")) == expected


def test_exclusion_projects_before_canonical_validation_and_keeps_nested_fields() -> None:
    assert digest_json({"digest": object(), "a": 1}, exclude_keys=("digest",)) == digest({"a": 1})
    with pytest.raises(TypeError, match="must not use floats"):
        digest_json({"digest": "old", "a": {"digest": 1.0}}, exclude_keys=("digest",))


@pytest.mark.parametrize("value", [[], (), "text", 1, True, None])
def test_digest_json_requires_a_mapping(value: Any) -> None:
    with pytest.raises(TypeError, match=r"^value must be a mapping$"):
        digest_json(value)


@pytest.mark.parametrize("value", [0.1, {"a": [1.0]}, {1: "a"}, {"a": object()}])
def test_digest_wrappers_preserve_canonical_rejections(value: Any) -> None:
    with pytest.raises(TypeError):
        digest(value)
    if isinstance(value, Mapping):
        with pytest.raises(TypeError):
            digest_json(value)


@pytest.mark.parametrize("data", ["text", bytearray(b"x"), memoryview(b"x"), None, 3])
def test_byte_hash_functions_reject_non_bytes(data: Any) -> None:
    for function in (sha256_hex, digest_bytes):
        with pytest.raises(TypeError, match=r"^data must be bytes$"):
            function(data)


def test_sha256_known_answers_and_raw_bytes_are_distinct_from_json() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert digest_bytes(b"abc") == "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert digest_bytes(b"{}") == "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
    assert digest_bytes(b"abc") != digest("abc")
    assert digest(True) != digest(1)
    assert digest(False) != digest(0)
    assert digest(None) != digest({})


@pytest.mark.parametrize(
    "value",
    [
        "sha256:" + "a" * 64 + "\n",
        "sha256:" + "a" * 64 + "\r\n",
        "sha256:" + "A" * 64,
        "SHA256:" + "a" * 64,
        "sha256:" + "g" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "a" * 64,
        " sha256:" + "a" * 64,
        None,
        5,
        [],
        b"sha256:" + b"a" * 64,
    ],
)
def test_tagged_digest_requires_an_exact_lowercase_full_match(value: object) -> None:
    assert not is_tagged_digest(value)


def test_valid_tagged_digest_includes_digits_and_all_lowercase_hex_letters() -> None:
    assert is_tagged_digest("sha256:" + "0123456789abcdef" * 4)


def test_pretty_document_rendering_stays_separate_from_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(golden, "GOLDEN_ROOT", tmp_path)
    document = {"z": 1, "a": "текст"}
    (tmp_path / "document").mkdir()
    rendered = json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    (tmp_path / "document" / "pretty.json").write_text(rendered, encoding="utf-8")
    golden.assert_golden("document", "pretty", document)
    assert canonical_bytes(document) == '{"a":"текст","z":1}'.encode()
    assert digest_bytes(rendered.encode("utf-8")) != digest(document)


def test_snapshot_provenance_requires_matching_bytes(tmp_path: Path) -> None:
    fixture = tmp_path / "snapshot.json"
    fixture.write_bytes(b"{}\n")
    checksum = hashlib.sha256(fixture.read_bytes()).hexdigest()
    provenance = fixture.with_suffix(".source.txt")
    provenance.write_text(
        f"source: packages/owner/vectors.json\ncommit: 0d6a393\nsnapshot-sha256: {checksum}\n",
        encoding="utf-8",
    )
    assert checksum in golden.assert_legacy_source(fixture)
    fixture.write_bytes(b"{ }\n")
    with pytest.raises(AssertionError, match="does not match snapshot-sha256"):
        golden.assert_legacy_source(fixture)


@pytest.mark.parametrize(
    "metadata",
    [
        "source: packages/owner/vectors.json\n",
        "snapshot-sha256: " + "0" * 64 + "\n",
        "source: packages/owner/vectors.json\nsnapshot-sha256: bad\n",
    ],
)
def test_snapshot_provenance_needs_source_and_a_valid_checksum(tmp_path: Path, metadata: str) -> None:
    fixture = tmp_path / "snapshot.json"
    fixture.write_bytes(b"{}\n")
    fixture.with_suffix(".source.txt").write_text(metadata, encoding="utf-8")
    with pytest.raises(AssertionError, match="source path and commit"):
        golden.assert_legacy_source(fixture)
