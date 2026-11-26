"""Specification schema v1: authoring contract, valid/invalid corpus and semantic-finding manifest."""

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_type_hints
from uuid import uuid4

import pytest

from skm.modules.planning.generated import documents
from skm.platform.schema.registry import SchemaRegistry
from support.registries import settings_registry

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/planning"
SCHEMAS = ROOT / "src/skm/schemas/planning"
EXAMPLES = ROOT / "tests/fixtures/corpus/examples/plans"
SPECIFICATION = "urn:skm:planning:specification:v1"
FINDING_CATALOG = "urn:skm:planning:finding-catalog:v1"
SAVE_DRAFT = "urn:skm:planning:command:save-draft:v1"

ROLES = ("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar")
LEVELS = ("light", "medium", "heavy")

# SCHEMA_INVALID fixture -> (JSON pointer of the first issue, JSON Schema keyword that rejects it).
SCHEMA_INVALID = {
    "absolute-path": ("/items/0/change_hints/0/pattern", "pattern"),
    "dotdot-path": ("/units/0/write_scope/0/pattern", "pattern"),
    "tilde-path": ("/units/0/write_scope/0/pattern", "pattern"),
    "drive-path": ("/units/0/write_scope/0/pattern", "pattern"),
    "float-timeout": ("/checks/0", "oneOf"),
    "float-budget": ("/execution_constraints/max_parallel_units", "type"),
    "gate-and-label": ("/items/4/authority", "oneOf"),
    "item-without-review": ("/items/0", "required"),
    "review-mode-unknown": ("/items/0/review", "oneOf"),
    "self-review-without-reason": ("/items/0/review", "oneOf"),
    "waived-without-reason": ("/items/4/review", "oneOf"),
    "lifecycle-status-in-spec": ("/items/0", "additionalProperties"),
    "generated-position": ("/items/0", "additionalProperties"),
    "run-result-in-spec": ("/checks/0", "oneOf"),
    "check-owner-unit": ("/checks/0", "oneOf"),
    "qualified-ref-in-document": ("/items/1/depends_on/0", "pattern"),
    "model-without-runtime": ("/items/0/route", "dependentRequired"),
    "must-refresh-without-max-age": ("/materials/2", "oneOf"),
    "repository-path-latest-at-publish": ("/materials/1", "oneOf"),
    "material-required-for-unknown-stage": ("/materials/0", "oneOf"),
    "max-age-with-pinned": ("/materials/0", "oneOf"),
    "shell-without-risk-ack": ("/checks/1", "oneOf"),
    "work-policy-unknown-role": ("/items/0/work_policy/role_intensity", "additionalProperties"),
    "work-policy-unknown-level": ("/items/0/work_policy/role_intensity/executor", "enum"),
    "work-policy-null-in-document": ("/items/0/work_policy/role_intensity/executor", "enum"),
    "work-policy-null-policy": ("/items/0/work_policy", "type"),
    "work-policy-unknown-field": ("/units/0/work_policy", "additionalProperties"),
    "work-policy-float-level": ("/units/0/work_policy/verification_intensity", "enum"),
    "work-policy-in-phase": ("/phases/0", "additionalProperties"),
}

# Lifecycle, position and run-result vocabulary that belongs to execution, never to the document.
GENERATED_STATE_NAMES = frozenset(
    {"status", "position", "positions", "result", "results", "verdict", "lifecycle", "closed_at", "paused"}
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _names(directory: str, prefix: str = "") -> list[str]:
    return sorted(p.name for p in (FIXTURES / directory).glob(f"{prefix}*.json"))


VALID = _names("valid")
INVALID = _names("invalid")
SCHEMA_INVALID_FILES = _names("invalid", "SCHEMA_INVALID--")
SEMANTIC_FILES = [name for name in INVALID if not name.startswith("SCHEMA_INVALID--")]


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _issues(registry: SchemaRegistry, document: object, urn: str = SPECIFICATION):
    return registry.validate(urn, document)


def _auth_refresh() -> Any:
    return _load(FIXTURES / "valid/auth-refresh.specification.json")


def _defs() -> dict[str, Any]:
    return _load(SCHEMAS / "specification.v1.json")["$defs"]


def _keys(document: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for kind in ("phases", "items", "units", "requirements", "criteria", "decisions"):
        keys.update(entity["key"] for entity in document.get(kind, ()))
    keys.update(f"{check['owner']}:{check['key']}" for check in document.get("checks", ()))
    keys.update(f"material/{material['key']}" for material in document.get("materials", ()))
    return keys


# --- valid corpus -----------------------------------------------------------------------------------


def test_valid_corpus_is_large_enough_and_contains_the_reference_plan():
    assert len(VALID) >= 12
    assert "auth-refresh.specification.json" in VALID


@pytest.mark.parametrize("name", VALID)
def test_valid_document_passes_the_schema(registry, name):
    assert _issues(registry, _load(FIXTURES / "valid" / name)) == ()


def test_reference_plan_fixture_is_the_owner_example():
    assert _auth_refresh() == _load(EXAMPLES / "auth-refresh.specification.json")


def test_invalid_corpus_contains_every_owner_example():
    owner = {p.name for p in (EXAMPLES / "invalid").glob("*.json")}
    assert owner <= set(INVALID)
    for name in owner:
        assert _load(FIXTURES / "invalid" / name) == _load(EXAMPLES / "invalid" / name)


@pytest.mark.parametrize("name", VALID)
def test_valid_document_round_trips_through_the_generated_record(registry, name):
    raw = _load(FIXTURES / "valid" / name)
    record = documents.specification_doc_from_json(raw)
    restored = documents.specification_doc_to_json(record)
    assert restored == raw
    assert json.loads(json.dumps(restored)) == raw
    assert _issues(registry, restored) == ()


def test_generated_specification_doc_follows_the_schema_root():
    schema = _load(SCHEMAS / "specification.v1.json")
    hints = get_type_hints(documents.SpecificationDoc, include_extras=True)
    assert set(hints) == set(schema["properties"])
    assert documents.SpecificationDoc.__required_keys__ == frozenset(schema["required"])


def test_phase_depends_on_absence_differs_from_empty():
    raw = _load(FIXTURES / "valid/phase-depends-on-explicit.json")
    shapes = {phase["key"]: phase.get("depends_on", "<absent>") for phase in raw["phases"]}
    assert shapes == {"P1": [], "P2": "<absent>", "P3": ["P1"], "P4": ["P1", "P3"]}
    restored = documents.specification_doc_to_json(documents.specification_doc_from_json(raw))
    assert [phase.get("depends_on", "<absent>") for phase in restored["phases"]] == list(shapes.values())


def test_minimal_document_carries_no_materialised_defaults():
    raw = _load(FIXTURES / "valid/minimal.json")
    assert set(raw) == {"schema", "title", "goal", "phases", "items"}
    assert set(raw["items"][0]) == {"key", "phase", "title", "summary", "why", "review"}
    restored = documents.specification_doc_to_json(documents.specification_doc_from_json(raw))
    assert restored == raw


# --- required fields and state-free document ---------------------------------------------------------


@pytest.mark.parametrize("field", ["schema", "title", "goal", "phases", "items"])
def test_root_required_field_is_enforced(registry, field):
    raw = _auth_refresh()
    del raw[field]
    assert [issue.code for issue in _issues(registry, raw)] == ["required"]


@pytest.mark.parametrize("field", ["status", "created_at", "revision", "position"])
def test_unknown_root_field_is_rejected(registry, field):
    raw = _auth_refresh()
    raw[field] = "x"
    issues = _issues(registry, raw)
    assert [(issue.pointer, issue.code) for issue in issues] == [("", "additionalProperties")]


def test_no_entity_declares_generated_positions_status_or_results():
    schema = _load(SCHEMAS / "specification.v1.json")
    seen: set[str] = set(schema["properties"])

    def walk(node: object) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                seen.update(properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema["$defs"])
    assert not seen & GENERATED_STATE_NAMES


def test_schema_declares_no_float_typed_value():
    def types(node: object) -> Iterator[str]:
        if isinstance(node, dict):
            declared = node.get("type")
            yield from (declared,) if isinstance(declared, str) else (declared or ())
            for value in node.values():
                yield from types(value)
        elif isinstance(node, list):
            for value in node:
                yield from types(value)

    assert "number" not in set(types(_load(SCHEMAS / "specification.v1.json")))
    for directory in ("commands", "queries", "results", "views", "events"):
        for path in (SCHEMAS / directory).glob("*.json"):
            assert "number" not in set(types(_load(path))), path.name
    for name in ("defs.v1.json", "change-replace-text.v1.json"):
        assert "number" not in set(types(_load(SCHEMAS / name))), name


# --- SCHEMA_INVALID corpus ---------------------------------------------------------------------------


def test_schema_invalid_table_matches_the_corpus_files():
    assert {
        name.removeprefix("SCHEMA_INVALID--").removesuffix(".json") for name in SCHEMA_INVALID_FILES
    } == set(SCHEMA_INVALID)


@pytest.mark.parametrize("name", SCHEMA_INVALID_FILES)
def test_schema_invalid_fixture_is_rejected_at_its_pointer(registry, name):
    pointer, keyword = SCHEMA_INVALID[name.removeprefix("SCHEMA_INVALID--").removesuffix(".json")]
    issues = _issues(registry, _load(FIXTURES / "invalid" / name))
    assert issues, name
    assert (issues[0].pointer, issues[0].code) == (pointer, keyword)


# --- semantic findings manifest ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return _load(FIXTURES / "expected-semantic-findings.json")


@pytest.fixture(scope="module")
def catalog() -> dict[str, Any]:
    return _load(SCHEMAS / "data/finding-codes.json")


def test_finding_catalog_data_matches_its_schema(registry, catalog):
    assert _issues(registry, catalog, FINDING_CATALOG) == ()
    codes = [entry["code"] for entry in catalog["codes"]]
    assert len(codes) == len(set(codes))


def test_finding_catalog_names_only_registered_config_keys(catalog):
    registry = settings_registry()
    named = {entry["configurable_by"] for entry in catalog["codes"] if "configurable_by" in entry}
    assert named
    assert {key for key in named if registry.find(key) is None} == set()


def test_manifest_lists_exactly_the_semantic_fixtures(manifest):
    assert sorted(Path(entry["file"]).name for entry in manifest["fixtures"]) == SEMANTIC_FILES
    assert all(entry["file"].startswith("invalid/") for entry in manifest["fixtures"])
    assert manifest["base"] == "valid/auth-refresh.specification.json"
    assert (FIXTURES / manifest["base"]).is_file()


@pytest.mark.parametrize("name", SEMANTIC_FILES)
def test_semantic_fixture_is_schema_valid_and_listed_with_its_filename_code(
    registry, manifest, catalog, name
):
    entries = [entry for entry in manifest["fixtures"] if Path(entry["file"]).name == name]
    assert len(entries) == 1
    entry = entries[0]
    raw = _load(FIXTURES / entry["file"])
    assert _issues(registry, raw) == ()
    assert entry["code"] == name.split("--", 1)[0]
    by_code = {item["code"]: item for item in catalog["codes"]}
    assert entry["severity"] == by_code[entry["code"]]["severity"] == "error"
    assert set(entry["allowed_companion_codes"]) <= set(by_code)
    assert entry["code"] not in entry["allowed_companion_codes"]


ABSENT = object()


def _at(document: Any, pointer: str) -> Any:
    """Value at ``pointer``; ABSENT when only the last step is missing (the defect is a removed field)."""
    parts = pointer.split("/")[1:]
    node = document
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        index = int(parts[-1])
        return node[index] if index < len(node) else ABSENT
    return node.get(parts[-1], ABSENT)


@pytest.mark.parametrize("name", SEMANTIC_FILES)
def test_semantic_fixture_locus_and_entity_key_exist_in_the_document(manifest, name):
    entry = next(item for item in manifest["fixtures"] if Path(item["file"]).name == name)
    raw = _load(FIXTURES / entry["file"])
    assert entry["entity_key"] in _keys(raw)
    assert _at(raw, entry["locus"]) != _at(_auth_refresh(), entry["locus"])


def test_semantic_fixtures_are_not_schema_invalid_variants_of_each_other(registry):
    # The schema/semantic distinction: a dangling reference is not a schema error.
    raw = _load(FIXTURES / "invalid/ref_unknown--depends-on-missing-item.json")
    assert raw["items"][1]["depends_on"] == ["P1.9"]
    assert "P1.9" not in _keys(raw)
    assert _issues(registry, raw) == ()


# --- work_policy (planning §4.2.1) ------------------------------------------------------------------


def test_work_policy_declares_exactly_seven_roles_and_three_levels():
    defs = _defs()
    assert tuple(defs["intensity"]["enum"]) == LEVELS
    policy = defs["work_policy"]
    assert policy["additionalProperties"] is False
    assert set(policy["properties"]) == {"role_intensity", "verification_intensity"}
    assert not policy.get("required")
    roles = policy["properties"]["role_intensity"]
    assert roles["additionalProperties"] is False
    assert tuple(roles["properties"]) == ROLES
    assert not roles.get("required")


def test_work_policy_is_allowed_on_items_and_units_only():
    defs = _defs()
    for name in ("item", "unit"):
        assert defs[name]["properties"]["work_policy"] == {"$ref": "#/$defs/work_policy"}
    for name in ("phase", "decision", "check", "requirement", "criterion", "material"):
        node = defs[name]
        variants = node.get("oneOf", [node])
        assert all("work_policy" not in variant["properties"] for variant in variants), name


@pytest.mark.parametrize("name", ["work-policy-full", "work-policy-partial", "work-policy-empty"])
def test_work_policy_fixture_is_stored_exactly_as_declared(registry, name):
    raw = _load(FIXTURES / "valid" / f"{name}.json")
    declared = [e["work_policy"] for e in (*raw["items"], *raw.get("units", ())) if "work_policy" in e]
    assert declared
    restored = documents.specification_doc_to_json(documents.specification_doc_from_json(raw))
    assert [
        e["work_policy"] for e in (*restored["items"], *restored.get("units", ())) if "work_policy" in e
    ] == declared


def test_work_policy_does_not_touch_the_route():
    raw = _load(FIXTURES / "valid/work-policy-partial.json")
    third = raw["items"][2]
    assert third["route"] == {"class": "frontier", "effort": "max"}
    assert third["work_policy"] == {"role_intensity": {"executor": "light"}}


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("level", LEVELS)
def test_each_role_and_level_is_accepted_on_item_and_unit(registry, role, level):
    raw = _load(FIXTURES / "valid/work-policy-full.json")
    raw["items"][0]["work_policy"] = {"role_intensity": {role: level}}
    raw["units"][0]["work_policy"] = {"role_intensity": {role: level}, "verification_intensity": level}
    assert _issues(registry, raw) == ()


@pytest.mark.parametrize(
    "policy",
    [
        {"role_intensity": {"planner": "light"}},
        {"role_intensity": {"Executor": "light"}},
        {"role_intensity": {"executor": "extreme"}},
        {"role_intensity": {"executor": "HEAVY"}},
        {"role_intensity": {"executor": None}},
        {"role_intensity": {"executor": 2}},
        {"role_intensity": None},
        {"role_intensity": ["executor"]},
        {"verification_intensity": None},
        {"verification_intensity": "none"},
        {"verification_intensity": 1.5},
        {"effort": "high"},
        {"script": "echo"},
        None,
        "light",
        [],
    ],
)
@pytest.mark.parametrize("owner", ["items", "units"])
def test_malformed_work_policy_is_rejected(registry, owner, policy):
    raw = _load(FIXTURES / "valid/work-policy-full.json")
    raw[owner][0]["work_policy"] = policy
    issues = _issues(registry, raw)
    assert issues
    assert all(issue.pointer.startswith(f"/{owner}/0/work_policy") for issue in issues)


def test_work_policy_is_rejected_on_a_phase_and_at_the_root(registry):
    raw = _load(FIXTURES / "valid/minimal.json")
    raw["phases"][0]["work_policy"] = {"verification_intensity": "light"}
    assert [issue.pointer for issue in _issues(registry, raw)] == ["/phases/0"]
    raw = _load(FIXTURES / "valid/minimal.json")
    raw["work_policy"] = {}
    assert [issue.pointer for issue in _issues(registry, raw)] == [""]


# --- review, authority, checks, materials -----------------------------------------------------------


def test_every_review_mode_is_explicit_and_absence_is_not_a_waiver(registry):
    raw = _load(FIXTURES / "valid/review-modes.json")
    assert [item["review"]["mode"] for item in raw["items"]] == ["required", "required", "self", "waived"]
    del raw["items"][2]["review"]
    assert [(i.pointer, i.code) for i in _issues(registry, raw)] == [("/items/2", "required")]


@pytest.mark.parametrize(
    "review",
    [
        {"mode": "required", "independence": "same_session"},
        {"mode": "required", "max_rounds": 0},
        {"mode": "required", "max_rounds": 11},
        {"mode": "required", "required_evidence": ["diff", "diff"]},
        {"mode": "required", "required_evidence": ["screenshot"]},
        {"mode": "required", "covers": ["P1.1", "P1.1"]},
        {"mode": "required", "reason": "not allowed on required"},
        {"mode": "self", "reason": "x", "waived_by": "owner"},
        {"mode": "waived", "reason": "x"},
        {"mode": "waived", "waived_by": "owner"},
    ],
)
def test_malformed_review_requirement_is_rejected(registry, review):
    raw = _load(FIXTURES / "valid/review-modes.json")
    raw["items"][0]["review"] = review
    issues = _issues(registry, raw)
    assert issues
    assert all(issue.pointer.startswith("/items/0/review") for issue in issues)


def test_check_owner_is_a_phase_or_an_item(registry):
    raw = _load(FIXTURES / "valid/check-kinds.json")
    assert {check["owner"] for check in raw["checks"]} == {"P1", "P1.1"}
    for owner in ("P1.1/U1", "AC1", "material/x", "P1:V1", ""):
        broken = copy.deepcopy(raw)
        broken["checks"][0]["owner"] = owner
        assert [issue.pointer for issue in _issues(registry, broken)] == ["/checks/0"], owner


def test_every_check_kind_is_declared_and_shell_needs_an_acknowledged_risk(registry):
    raw = _load(FIXTURES / "valid/check-kinds.json")
    assert {check["kind"] for check in raw["checks"]} == {"command", "shell", "manual", "external"}
    for kind, field in (
        ("shell", "risk_ack"),
        ("manual", "actor_role"),
        ("external", "provider"),
        ("command", "argv"),
    ):
        broken = copy.deepcopy(raw)
        check = next(c for c in broken["checks"] if c["kind"] == kind)
        del check["definition"][field]
        assert [issue.pointer for issue in _issues(registry, broken)] == [
            f"/checks/{broken['checks'].index(check)}"
        ]


def test_command_budgets_are_integers_within_bounds(registry):
    raw = _load(FIXTURES / "valid/check-kinds.json")
    for value in (0, 86401, 1.5, "600", True, None):
        broken = copy.deepcopy(raw)
        broken["checks"][0]["definition"]["timeout_seconds"] = value
        assert _issues(registry, broken), value
    for value in (1, 86400):
        fine = copy.deepcopy(raw)
        fine["checks"][0]["definition"]["timeout_seconds"] = value
        assert _issues(registry, fine) == (), value
    for value in (0, 65, 1.5):
        broken = _load(FIXTURES / "valid/decisions-sections-extensions.json")
        broken["execution_constraints"]["max_parallel_units"] = value
        assert _issues(registry, broken), value


def test_every_read_kind_is_declared(registry):
    raw = _load(FIXTURES / "valid/read-kinds.json")
    assert [read["kind"] for read in raw["items"][0]["reads"]] == [
        "repository_path",
        "material",
        "plan_entity",
        "artifact",
        "external_source",
    ]
    broken = copy.deepcopy(raw)
    del broken["items"][0]["reads"][4]["external_source_id"]
    assert _issues(registry, broken)
    broken = copy.deepcopy(raw)
    broken["items"][0]["reads"][0]["path"] = "../escape"
    assert [issue.pointer for issue in _issues(registry, broken)] == ["/items/0/reads/0"]


def test_material_stage_and_freshness_rules(registry):
    raw = _load(FIXTURES / "valid/material-kinds.json")
    assert {m["kind"] for m in raw["materials"]} == {"file_version", "repository_path", "external_source"}
    assert {s for m in raw["materials"] for s in m.get("required_for", ())} == {
        "execution",
        "review",
        "acceptance",
    }
    assert {m["freshness"]["policy"] for m in raw["materials"]} == {
        "pinned",
        "latest_at_publish",
        "must_refresh",
    }
    for value in (59, 31536001, 1.5):
        broken = copy.deepcopy(raw)
        broken["materials"][2]["freshness"]["max_age_seconds"] = value
        assert _issues(registry, broken), value
    broken = copy.deepcopy(raw)
    broken["materials"][4]["freshness"] = {"policy": "latest_at_publish"}
    assert _issues(registry, broken)
    broken = copy.deepcopy(raw)
    broken["materials"][0]["required_for"] = ["execution", "execution"]
    assert _issues(registry, broken)


def test_authority_requires_exactly_one_of_gate_or_label(registry):
    raw = _load(FIXTURES / "valid/authority-gates.json")
    assert [item["authority"]["kind"] for item in raw["items"]] == [
        "routine",
        "owner_gate",
        "owner_gate",
        "external_gate",
        "external_gate",
    ]
    for index in (1, 3):
        both = copy.deepcopy(raw)
        both["items"][index]["authority"]["label"] = "Both"
        neither = copy.deepcopy(raw)
        del neither["items"][index]["authority"]["gate"]
        no_scope = copy.deepcopy(raw)
        del no_scope["items"][index]["authority"]["scope"]
        for broken in (both, neither, no_scope):
            assert [issue.pointer for issue in _issues(registry, broken)] == [f"/items/{index}/authority"]


@pytest.mark.parametrize("path", ["src/", "a/./b", "**/*.py", "docs/api/refresh.md", "src/[ab]?.py"])
def test_mount_relative_paths_and_globs_are_accepted(registry, path):
    raw = _load(FIXTURES / "valid/minimal.json")
    raw["units"] = [
        {"key": "P1.1/U1", "title": "U", "goal": "G", "write_scope": [{"mount": "api", "pattern": path}]}
    ]
    assert _issues(registry, raw) == ()


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../x", "a/../b", "a/..", "~/x", "C:/x", "c:x", "a b", "a\tb", "a\x00b", ""]
)
def test_mount_relative_paths_reject_escape_forms(registry, path):
    raw = _load(FIXTURES / "valid/minimal.json")
    raw["units"] = [
        {"key": "P1.1/U1", "title": "U", "goal": "G", "write_scope": [{"mount": "api", "pattern": path}]}
    ]
    assert _issues(registry, raw), path


# --- draft-change (planning §5.3), carried by save-draft --------------------------------------------


def _save(changes: list[Any]) -> dict[str, Any]:
    return {
        "plan_id": str(uuid4()),
        "draft_id": str(uuid4()),
        "expected_edit_version": 3,
        "changes": changes,
    }


def _replace(**overrides: Any) -> dict[str, Any]:
    change = {
        "op": "replace_text",
        "target": "plan",
        "pointer": "/context_md",
        "expected_text_digest": "sha256:" + "0" * 64,
        "old_text": "old",
        "new_text": "new",
    }
    return {**change, **overrides}


def test_replace_text_is_one_of_the_draft_change_operations(registry):
    defs = _load(SCHEMAS / "defs.v1.json")["$defs"]["draft-change"]["oneOf"]
    ops = [v["properties"]["op"]["const"] for v in defs if "properties" in v]
    assert ops == ["patch", "add", "remove", "move", "rekey"]
    assert defs[-1] == {"$ref": "urn:skm:planning:change:replace-text:v1"}
    assert _issues(registry, _save([_replace()]), SAVE_DRAFT) == ()


def test_standalone_replace_text_example_is_the_same_contract():
    owner = _load(SCHEMAS / "change-replace-text.v1.json")
    assert owner["$id"] == "urn:skm:planning:change:replace-text:v1"
    assert owner["additionalProperties"] is False
    assert owner["required"] == ["op", "target", "pointer", "expected_text_digest", "old_text", "new_text"]
    assert owner["properties"]["old_text"]["minLength"] == 1
    assert "minLength" not in owner["properties"]["new_text"]


def test_stable_entity_references_are_accepted_for_target_after_and_before(registry):
    ref = f"entity:{uuid4()}"
    other = f"entity:{uuid4()}"
    changes = [
        {"op": "patch", "target": ref, "merge_patch": {"title": "t"}},
        {"op": "add", "kind": "item", "entity": {"key": "P1.9"}, "after": ref},
        {"op": "remove", "target": ref, "cascade": True},
        {"op": "move", "target": ref, "after": other},
        {"op": "move", "target": ref, "before": other},
        {"op": "rekey", "target": ref, "new_key": "P1.8"},
        _replace(target=ref, pointer="/title"),
        _replace(target="brief", pointer="/constraints/0"),
    ]
    assert _issues(registry, _save(changes), SAVE_DRAFT) == ()


@pytest.mark.parametrize(
    "change",
    [
        _replace(old_text=""),
        _replace(expected_text_digest="sha256:abc"),
        _replace(expected_text_digest="0" * 64),
        _replace(expected_text_digest="sha256:" + "A" * 64),
        _replace(pointer="context_md"),
        _replace(pointer="/a~2b"),
        _replace(target=""),
        _replace(new_text=None),
        _replace(extra=1),
        {k: v for k, v in _replace().items() if k != "pointer"},
        {k: v for k, v in _replace().items() if k != "expected_text_digest"},
        {"op": "replace", "target": "plan"},
    ],
)
def test_malformed_replace_text_is_rejected(registry, change):
    assert _issues(registry, _save([change]), SAVE_DRAFT)


def test_replace_text_may_delete_text(registry):
    assert _issues(registry, _save([_replace(new_text="")]), SAVE_DRAFT) == ()
