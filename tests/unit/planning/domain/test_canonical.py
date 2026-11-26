"""Normalization and the specification digest (planning §5.6): defaults, empty arrays, identity, bytes."""

import copy
import inspect
import json
import random
import re
import unicodedata
from collections.abc import Callable, Iterator, Mapping
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from skm.modules.planning.domain.canonical import (
    CANONICALIZATION_VERSION,
    document_bytes,
    normalize_document,
    specification_digest,
)
from skm.modules.planning.domain.changes import rekey
from skm.modules.planning.domain.identity import ENTITY_ARRAYS
from skm.modules.planning.domain.specification import from_document, to_document
from skm.platform.jsonc import canonical as jsonc
from skm.platform.jsonc.digest import digest
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/auth-refresh.specification.json"
SCHEMA = ROOT / "src/skm/schemas/planning/specification.v1.json"
SOURCE = ROOT / "src/skm/modules/planning/domain/canonical.py"
SPECIFICATION = "urn:skm:planning:specification:v1"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def _doc() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


def _normal(doc: Any) -> dict[str, Any]:
    return normalize_document(doc)


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _by_key(doc: Mapping[str, Any], array: str, key: str, owner: str | None = None) -> dict[str, Any]:
    return next(e for e in doc[array] if e["key"] == key and (owner is None or e["owner"] == owner))


# ------------------------------------------------------------------------------------------- defaults


def _without_defaults(doc: dict[str, Any], drop: Callable[[], bool] = lambda: True) -> dict[str, Any]:
    """``doc`` without members that hold the default normalization writes (each one only when ``drop()``)."""
    out = copy.deepcopy(doc)

    def strip(entity: dict[str, Any], name: str, default: Any) -> None:
        if name in entity and entity[name] == default and drop():
            del entity[name]

    for phase in out["phases"]:
        strip(phase, "strategy", "dag")
    for item in out["items"]:
        strip(item, "work_kind", "code")
        strip(item, "authority", {"kind": "routine"})
        strip(item, "unit_strategy", "dag")
        if item["review"]["mode"] == "required":
            strip(item["review"], "independence", "separate_session")
    for unit in out.get("units", []):
        strip(unit, "unit_kind", "implementation")
        strip(unit, "mode", "either")
    for check in out.get("checks", []):
        strip(check, "required", check["category"] == "acceptance")
        strip(check, "rerun_after_integration", False)
        strip(check, "evidence", {"stdout": True, "stderr": True})
        definition = check["definition"]
        strip(definition, "timeout_seconds", 600)
        strip(definition, "allowed_verdicts", ["pass", "fail"])
        if "cwd" in definition:
            strip(definition["cwd"], "path", ".")
    for material in out.get("materials", []):
        strip(material, "freshness", {"policy": "pinned"})
        strip(material, "global", False)
    for decision in out.get("decisions", []):
        strip(decision, "global", False)
    if "execution_constraints" in out:
        strip(out["execution_constraints"], "strategy", "dag")
        strip(out, "execution_constraints", {})
    return out


def test_normalized_example_is_schema_valid_idempotent_and_the_to_document_form(registry):
    doc = _doc()
    normal = _normal(doc)
    registry.require_valid(SPECIFICATION, normal)
    assert _normal(normal) == normal
    assert to_document(from_document(doc)[0]) == normal
    assert _normal(to_document(from_document(normal)[0])) == normal


def test_meaningful_defaults_are_written_explicitly_and_equal_their_absence():
    stripped = _without_defaults(_doc())
    assert "strategy" not in stripped["phases"][0]
    assert "execution_constraints" in stripped  # it holds more than its strategy
    assert "strategy" not in stripped["execution_constraints"]
    normal = _normal(stripped)
    written = {
        "phases": {"strategy": "dag"},
        "items": {"work_kind": "code", "authority": {"kind": "routine"}, "unit_strategy": "dag"},
        "units": {"unit_kind": "implementation", "mode": "either"},
    }
    for array, defaults in written.items():
        for before, after in zip(stripped[array], normal[array], strict=True):
            for name, default in defaults.items():
                assert after[name] == before.get(name, default), (array, before["key"], name)
    assert any("work_kind" not in i for i in stripped["items"])
    assert any("unit_kind" not in u for u in stripped["units"])
    assert all(c["evidence"] == {"stdout": True, "stderr": True} for c in normal["checks"])
    for before, after in zip(stripped["checks"], normal["checks"], strict=True):
        assert after["rerun_after_integration"] is before.get("rerun_after_integration", False)
        assert after["required"] is before.get("required", before["category"] == "acceptance")
    assert _by_key(normal, "checks", "V1", "P1.2")["definition"] == {
        "argv": _by_key(stripped, "checks", "V1", "P1.2")["definition"]["argv"],
        "cwd": {"mount": "api", "path": "."},
        "timeout_seconds": 600,
    }
    assert _by_key(normal, "checks", "V1", "P2.3")["definition"]["allowed_verdicts"] == ["pass", "fail"]
    assert normal["items"][0]["review"]["independence"] == "separate_session"
    assert all(m["freshness"] for m in normal["materials"])
    assert normal["execution_constraints"]["strategy"] == "dag"
    assert normal == _normal(_doc())
    assert specification_digest(stripped) == specification_digest(_doc())
    minimal = {key: value for key, value in stripped.items() if key != "execution_constraints"}
    assert _normal(minimal)["execution_constraints"] == {"strategy": "dag"}


def test_check_required_follows_the_category_and_an_explicit_value_is_kept():
    doc = _doc()
    for check in doc["checks"]:
        check.pop("required")
    normal = _normal(doc)
    assert {(c["category"], c["required"]) for c in normal["checks"]} == {
        ("acceptance", True),
        ("impact", False),
        ("live", False),
    }
    explicit = _doc()
    _by_key(explicit, "checks", "V1", "P1.2")["required"] = False
    assert _by_key(_normal(explicit), "checks", "V1", "P1.2")["required"] is False
    assert specification_digest(explicit) != specification_digest(_doc())


def test_review_independence_is_a_default_of_required_review_only():
    doc = _doc()
    reviews = {i["key"]: i["review"] for i in _normal(doc)["items"]}
    assert reviews["P2.3"]["mode"] == "waived"
    assert "independence" not in reviews["P2.3"]
    doc["items"][0]["review"] = {"mode": "self", "reason": "Trivial rename."}
    assert _normal(doc)["items"][0]["review"] == {"mode": "self", "reason": "Trivial rename."}


def test_defaults_the_model_does_not_write_back_are_dropped(registry):
    doc, absent = _doc(), _doc()
    for entity in (*doc["decisions"], *doc["materials"]):
        entity.setdefault("global", False)
    doc["phases"][1]["contract"] = {"consumes": [], "produces": []}
    _by_key(doc, "checks", "V2", "P2.3")["definition"]["params"] = {}
    del _by_key(absent, "checks", "V2", "P2.3")["definition"]["params"]
    registry.require_valid(SPECIFICATION, doc)
    normal = _normal(doc)
    assert "global" not in normal["decisions"][0]
    assert _by_key(normal, "materials", "auth-module")["global"] is True
    assert "contract" not in normal["phases"][1]
    assert "params" not in _by_key(normal, "checks", "V2", "P2.3")["definition"]
    assert normal == to_document(from_document(doc)[0])
    assert normal == _normal(absent)
    assert specification_digest(doc) == specification_digest(absent)


# ------------------------------------------------------------------------------------------- empty arrays


@cache
def _optional_arrays() -> frozenset[tuple[str, str]]:
    """``(owner, member)`` of every optional array of the schema an empty value of which is valid."""
    schema = json.loads(SCHEMA.read_text())
    defs = schema["$defs"]
    found: set[tuple[str, str]] = set()

    def resolved(node: Mapping[str, Any]) -> Mapping[str, Any]:
        while "$ref" in node:
            node = defs[node["$ref"].rsplit("/", 1)[1]]
        return node

    def walk(node: Mapping[str, Any], owner: str) -> None:
        for variant in node.get("oneOf", ()):
            walk(variant, owner)
        required = set(node.get("required", ()))
        for name, member in node.get("properties", {}).items():
            target = resolved(member)
            if target.get("type") == "array" and name not in required:
                if not target.get("minItems") and "default" not in target:
                    found.add((owner, name))
            elif member.get("type") == "object":
                walk(member, f"{owner}.{name}")

    walk(schema, "#")
    for name, node in defs.items():
        walk(node, name)
    return frozenset(found)


def _definitions(doc: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    commands = [u["command"] for u in doc.get("units", []) if "command" in u]
    return [c["definition"] for c in (*doc.get("checks", []), *commands) if c["kind"] == kind]


# Where the objects of each schema owner of an optional array live in a document.
LOCATORS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "#": lambda d: [d],
    "brief": lambda d: [d["brief"]],
    "requirement": lambda d: d["requirements"],
    "phase": lambda d: d["phases"],
    "phase.contract": lambda d: [p.setdefault("contract", {}) for p in d["phases"]],
    "phase.assurance": lambda d: [p["assurance"] for p in d["phases"] if "assurance" in p],
    "item": lambda d: d["items"],
    "review": lambda d: [i["review"] for i in d["items"] if i["review"]["mode"] == "required"],
    "unit": lambda d: d["units"],
    "criterion": lambda d: d["criteria"],
    "evidence_policy": lambda d: [c.setdefault("evidence", {}) for c in d["checks"]],
    "command_definition": lambda d: _definitions(d, "command"),
    "shell_definition": lambda d: _definitions(d, "shell"),
    "decision": lambda d: d["decisions"],
    "material": lambda d: d["materials"],
    "execution_constraints": lambda d: [d["execution_constraints"]],
}


def test_the_schema_optional_arrays_are_known_and_phase_depends_on_is_one_of_them():
    owners = {owner for owner, _ in _optional_arrays()}
    assert owners <= set(LOCATORS), owners - set(LOCATORS)
    assert ("phase", "depends_on") in _optional_arrays()
    assert ("#", "phases") not in _optional_arrays()  # required arrays stay
    assert ("phase", "sections") in _optional_arrays()  # an array behind $ref counts


@pytest.mark.parametrize(
    ("owner", "member"),
    sorted(_optional_arrays() - {("phase", "depends_on")}),
    ids=str,
)
def test_an_empty_optional_array_is_dropped_and_means_its_absence(owner, member):
    empty, absent = _doc(), _doc()
    targets = LOCATORS[owner](empty)
    assert targets, owner  # the example holds such an object
    for entity in targets:
        entity[member] = []
    for entity in LOCATORS[owner](absent):
        entity.pop(member, None)
    normal = _normal(empty)
    assert normal == _normal(absent)
    assert all(member not in entity for entity in LOCATORS[owner](copy.deepcopy(normal)) if entity)
    assert specification_digest(empty) == specification_digest(absent)
    assert to_document(from_document(empty)[0]) == normal


def test_phase_depends_on_absent_and_empty_are_different_documents():
    doc = _doc()
    assert doc["phases"][0]["depends_on"] == []
    assert "depends_on" not in doc["phases"][1]
    normal = _normal(doc)
    assert normal["phases"][0]["depends_on"] == []
    assert "depends_on" not in normal["phases"][1]
    swapped = _doc()
    del swapped["phases"][0]["depends_on"]
    swapped["phases"][1]["depends_on"] = []
    assert specification_digest(swapped) != specification_digest(doc)
    absent = _doc()
    del absent["phases"][0]["depends_on"]
    assert specification_digest(absent) != specification_digest(doc)
    assert to_document(from_document(absent)[0]) == _normal(absent)


def test_required_arrays_stay_when_empty():
    doc = _doc()
    doc["phases"][0]["scope"]["exclude"] = []
    doc["brief"]["messages"] = []
    normal = _normal(doc)
    assert normal["phases"][0]["scope"]["exclude"] == []
    assert normal["brief"]["messages"] == []
    bare = _normal({"schema": SPECIFICATION, "title": "t", "goal": "g", "phases": [], "items": []})
    assert bare == {
        "schema": SPECIFICATION,
        "title": "t",
        "goal": "g",
        "phases": [],
        "items": [],
        "execution_constraints": {"strategy": "dag"},
    }


def test_empty_extensions_are_dropped_and_payloads_are_kept_verbatim():
    doc = _doc()
    doc["extensions"] = {}
    assert "extensions" not in _normal(doc)
    assert specification_digest(doc) == specification_digest(_doc())
    payload = {"schema_version": 1, "value": {"tags": [], "meta": {}, "flag": None}}
    doc["extensions"] = {"acme/audit": payload}
    assert _normal(doc)["extensions"] == {"acme/audit": payload}
    changed = copy.deepcopy(doc)
    changed["extensions"]["acme/audit"]["value"]["tags"] = ["a"]
    assert specification_digest(changed) != specification_digest(doc)


# ------------------------------------------------------------------------------------------- identity


def _leaves(value: Any, pointer: tuple[str | int, ...] = ()) -> Iterator[tuple[tuple[str | int, ...], Any]]:
    if isinstance(value, dict):
        for name, item in value.items():
            yield from _leaves(item, (*pointer, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, (*pointer, index))
    else:
        yield pointer, value


def _replaced(doc: Any, pointer: tuple[str | int, ...], value: Any) -> Any:
    out = copy.deepcopy(doc)
    target = out
    for part in pointer[:-1]:
        target = target[part]
    target[pointer[-1]] = value
    return out


def _other(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    return value + "́" if value else "x"


def test_every_identity_and_text_of_the_document_takes_part_in_the_digest():
    normal = _normal(_doc())
    base = specification_digest(normal)
    leaves = list(_leaves(normal))
    entity_ids = [pointer for pointer, _ in leaves if len(pointer) == 3 and pointer[2] == "id"]
    assert len(entity_ids) == sum(len(normal[array]) for array, _ in ENTITY_ARRAYS) > 0
    assert {pointer[0] for pointer, _ in leaves} >= {"schema", "title", "goal", "brief", "phases", "items"}
    unchanged = [
        pointer
        for pointer, value in leaves
        if specification_digest(_replaced(normal, pointer, _other(value))) == base
    ]
    assert unchanged == []


def test_an_entity_id_alone_changes_the_digest_and_is_kept():
    doc = _doc()
    doc["items"][1]["id"] = "0192f5c4-0000-7000-8000-0000000000ff"
    assert _normal(doc)["items"][1]["id"] == "0192f5c4-0000-7000-8000-0000000000ff"
    assert specification_digest(doc) != specification_digest(_doc())
    assert _normal(doc)["items"][1]["key"] == "P1.2"


def test_rekey_changes_the_key_content_and_digest_but_keeps_the_id():
    doc = _doc()
    entity_id = _by_key(doc, "items", "P1.2")["id"]
    renamed = rekey(doc, "P1.2", "P1.9").document
    normal = _normal(renamed)
    moved = next(i for i in normal["items"] if i["id"] == entity_id)
    assert moved["key"] == "P1.9"
    assert [c["id"] for c in normal["checks"]] == [c["id"] for c in doc["checks"]]
    assert {c["owner"] for c in normal["checks"]} >= {"P1.9"}
    assert specification_digest(renamed) != specification_digest(doc)
    assert specification_digest(rekey(renamed, "P1.9", "P1.2").document) == specification_digest(doc)


# ------------------------------------------------------------------------------------------- canonical bytes


def _reordered(value: Any) -> Any:
    if isinstance(value, dict):
        return {name: _reordered(value[name]) for name in reversed(list(value))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


def test_key_order_and_pretty_printing_do_not_change_the_canonical_bytes():
    doc = _doc()
    canonical = jsonc.canonical_bytes(_normal(doc))
    pretty = json.loads(json.dumps(doc, indent=4, sort_keys=True))
    for variant in (_reordered(doc), pretty, json.loads(json.dumps(_reordered(doc), indent=1))):
        assert jsonc.canonical_bytes(_normal(variant)) == canonical
        assert specification_digest(variant) == specification_digest(doc)
        assert document_bytes(variant) == len(canonical)


def test_array_order_and_strings_are_kept_exactly():
    doc = _doc()
    swapped = _doc()
    swapped["requirements"][0], swapped["requirements"][1] = (
        swapped["requirements"][1],
        swapped["requirements"][0],
    )
    assert _normal(swapped)["requirements"][0]["key"] == "R2"
    assert specification_digest(swapped) != specification_digest(doc)
    composed, decomposed = _doc(), _doc()
    composed["title"] = unicodedata.normalize("NFC", "Café rotation")
    decomposed["title"] = unicodedata.normalize("NFD", "Café rotation")
    assert _normal(decomposed)["title"] == decomposed["title"]
    assert specification_digest(composed) != specification_digest(decomposed)
    spaced = _doc()
    spaced["goal"] = f"  {doc['goal']}\r\n"
    assert _normal(spaced)["goal"] == spaced["goal"]
    assert specification_digest(spaced) != specification_digest(doc)
    fraction = _doc()
    _by_key(fraction, "materials", "oauth-threats")["retrieved_at"] = "2026-10-21T10:00:00.5Z"
    assert _by_key(_normal(fraction), "materials", "oauth-threats")["retrieved_at"] == (
        "2026-10-21T10:00:00.5Z"
    )


def test_digest_and_size_are_canonical_json_v1_of_platform_jsonc():
    doc = _doc()
    normal = _normal(doc)
    assert CANONICALIZATION_VERSION == jsonc.CANONICALIZATION_VERSION == 1
    assert specification_digest(doc) == digest(normal)
    assert DIGEST.fullmatch(specification_digest(doc))
    assert document_bytes(doc) == len(jsonc.canonical_bytes(normal))
    wide = _doc()
    wide["title"] = "Ротация токенов"
    assert document_bytes(wide) - document_bytes(doc) == len(wide["title"].encode()) - len(
        doc["title"].encode()
    )
    assert specification_digest(wide) == digest(_normal(wide))


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        (("extensions",), {"acme/audit": {"schema_version": 1, "value": {"ratio": 0.5}}}),
        (("checks", 0, "definition", "timeout_seconds"), 600.0),
        (("extensions",), {"acme/audit": {"schema_version": 1, "value": {1: "x"}}}),
        (("extensions",), {"acme/audit": {"schema_version": 1, "value": {"x"}}}),
    ],
    ids=["float", "integral float", "non-string key", "set"],
)
def test_values_without_a_canonical_form_are_refused(pointer, value):
    doc = _replaced(_doc(), pointer, value)
    for function in (normalize_document, specification_digest, document_bytes):
        with pytest.raises(TypeError):
            function(doc)


# ------------------------------------------------------------------------------------------- copies


def _frozen(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({name: _frozen(item) for name, item in value.items()})
    if isinstance(value, list):
        return tuple(_frozen(item) for item in value)
    return value


def _containers(value: Any) -> Iterator[type]:
    yield type(value)
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _containers(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _containers(item)


def test_the_input_is_not_mutated_and_the_result_shares_no_container():
    doc = _without_defaults(_doc())
    doc["items"][0]["work_policy"] = {"role_intensity": {"executor": "heavy"}}
    before = copy.deepcopy(doc)
    normal = _normal(doc)
    assert doc == before
    normal["items"][0]["work_policy"]["role_intensity"]["executor"] = "light"
    normal["phases"][0]["depends_on"].append("P9")
    normal["brief"]["messages"][0]["text"] = "changed"
    assert doc == before


def test_frozen_nested_input_normalizes_like_plain_json():
    doc = _doc()
    doc["extensions"] = {"acme/audit": {"schema_version": 1, "value": {"tags": ["a"]}}}
    frozen = _frozen(doc)
    normal = _normal(frozen)
    assert normal == _normal(doc)
    assert set(_containers(normal)) <= {dict, list, str, int, bool}
    assert specification_digest(frozen) == specification_digest(doc)
    assert document_bytes(frozen) == document_bytes(doc)


# ------------------------------------------------------------------------------------------- work policy


def test_a_declared_work_policy_change_changes_the_digest():
    declared = _doc()
    declared["items"][0]["work_policy"] = {"role_intensity": {"executor": "heavy"}}
    lighter = copy.deepcopy(declared)
    lighter["items"][0]["work_policy"]["role_intensity"]["executor"] = "light"
    verification = copy.deepcopy(declared)
    verification["items"][0]["work_policy"]["verification_intensity"] = "heavy"
    unit = _doc()
    unit["units"][0]["work_policy"] = {"verification_intensity": "light"}
    digests = {specification_digest(d) for d in (_doc(), declared, lighter, verification, unit)}
    assert len(digests) == 5


def test_work_policy_is_kept_as_declared_absent_empty_and_partial():
    absent, empty, empty_roles, partial = _doc(), _doc(), _doc(), _doc()
    empty["items"][0]["work_policy"] = {}
    empty_roles["items"][0]["work_policy"] = {"role_intensity": {}}
    partial["items"][0]["work_policy"] = {"verification_intensity": "heavy"}
    assert "work_policy" not in _normal(absent)["items"][0]  # no medium is filled in
    assert _normal(empty)["items"][0]["work_policy"] == {}
    assert _normal(empty_roles)["items"][0]["work_policy"] == {"role_intensity": {}}
    assert _normal(partial)["items"][0]["work_policy"] == {"verification_intensity": "heavy"}
    digests = {specification_digest(d) for d in (absent, empty, empty_roles, partial)}
    assert len(digests) == 4
    for doc in (empty, empty_roles, partial):
        assert to_document(from_document(doc)[0]) == _normal(doc)


def test_role_intensity_key_order_does_not_change_the_canonical_bytes():
    one, other = _doc(), _doc()
    one["items"][0]["work_policy"] = {"role_intensity": {"executor": "heavy", "reviewer": "light"}}
    other["items"][0]["work_policy"] = {"role_intensity": {"reviewer": "light", "executor": "heavy"}}
    assert jsonc.canonical_bytes(_normal(one)) == jsonc.canonical_bytes(_normal(other))
    assert specification_digest(one) == specification_digest(other)


def test_the_digest_reads_the_document_only_not_settings_or_profiles():
    for function in (normalize_document, specification_digest, document_bytes):
        assert list(inspect.signature(function).parameters) == ["doc"]


# ------------------------------------------------------------------------------------------- properties


def _shuffled(value: Any, rnd: random.Random) -> Any:
    if isinstance(value, dict):
        names = list(value)
        rnd.shuffle(names)
        return {name: _shuffled(value[name], rnd) for name in names}
    if isinstance(value, list):
        return [_shuffled(item, rnd) for item in value]
    return value


def _variant(rnd: random.Random) -> dict[str, Any]:
    """An equivalent of the example: defaults dropped, empty optional arrays added, keys shuffled."""
    doc = _without_defaults(_doc(), lambda: rnd.random() < 0.5)
    for owner, member in sorted(_optional_arrays() - {("phase", "depends_on")}):
        for entity in LOCATORS[owner](doc):
            if member not in entity and rnd.random() < 0.3:
                entity[member] = []
    return _shuffled(doc, rnd)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(rnd=st.randoms(use_true_random=False), freeze=st.booleans())
def test_equivalent_documents_normalize_to_one_document_and_one_digest(rnd, freeze):
    expected = _normal(_doc())
    variant = _variant(rnd)
    assert to_document(from_document(variant)[0]) == _normal(variant)
    source = _frozen(variant) if freeze else variant
    normal = _normal(source)
    assert normal == expected
    assert _normal(normal) == normal
    assert specification_digest(source) == specification_digest(expected)


# ------------------------------------------------------------------------------------------- layering


def test_the_domain_module_imports_neither_platform_nor_io():
    source = SOURCE.read_text()
    forbidden = re.compile(
        r"^\s*(?:from|import)\s+skm\.(?:platform|adapters|modules\.(?:execution|runtimes))\b", re.M
    )
    assert forbidden.search(source) is None
    assert "import os" not in source
    assert "open(" not in source
