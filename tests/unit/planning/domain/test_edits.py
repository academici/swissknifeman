"""Atomic batch authoring: patch / add / remove / move / rekey, owned fields, RFC 7396 (planning §5.3)."""

import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, SkmError, ValidationFailed
from skm.kernel.json_types import JsonObject
from skm.modules.planning.domain.changes import (
    AddChange,
    ItemDefaults,
    MoveChange,
    PatchChange,
    RekeyChange,
    RemoveChange,
    apply_changes,
    merge_patch,
)
from skm.modules.planning.domain.identity import assign_missing_ids
from skm.modules.planning.domain.item import (
    Effort,
    Intensity,
    Item,
    ModelClass,
    RoleName,
    WorkPolicyOverride,
)
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.domain.specification import (
    EntityKind,
    Specification,
    from_document,
    to_document,
)
from skm.modules.planning.domain.unit import Unit
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = ROOT / "tests/fixtures/corpus/examples/plans"
SPECIFICATION = "urn:skm:planning:specification:v1"
DEFAULTS = ItemDefaults(ModelClass.IMPLEMENTATION, Effort.MEDIUM, ReviewMode.REQUIRED)


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _doc() -> dict[str, Any]:
    return json.loads((EXAMPLES / "auth-refresh.specification.json").read_text())


def _entity(doc: dict[str, Any], array: str, key: str, owner: str | None = None) -> dict[str, Any]:
    return next(e for e in doc[array] if e["key"] == key and (owner is None or e["owner"] == owner))


def _typed[T](spec: Specification, key: str, kind: type[T]) -> T:
    entity = spec.by_key(key)
    assert isinstance(entity, kind), key
    return entity


def _keys(doc: dict[str, Any], array: str) -> list[str]:
    return [e["key"] for e in doc[array]]


def _change(raw: dict):
    match raw["op"]:
        case "patch":
            return PatchChange(raw["target"], raw["merge_patch"])
        case "add":
            return AddChange(raw["kind"], raw["entity"], raw.get("after"))
        case "remove":
            return RemoveChange(raw["target"], raw["cascade"])
        case "move":
            return MoveChange(raw["target"], raw.get("after"), raw.get("before"))
        case "rekey":
            return RekeyChange(raw["target"], raw["new_key"])
    raise AssertionError(raw)


def _apply(doc, changes, registry=None):
    validate = None if registry is None else (lambda d: registry.require_valid(SPECIFICATION, d))
    return apply_changes(doc, changes, defaults=DEFAULTS, validate=validate)


def _failure(doc, changes, registry=None) -> SkmError:
    with pytest.raises(SkmError) as raised:
        _apply(doc, changes, registry)
    return raised.value


# ---------------------------------------------------------------------------------------- the owner example


def test_owner_example_batch_applies_in_order_and_the_result_is_schema_valid(registry):
    doc = _doc()
    before = copy.deepcopy(doc)
    batch = json.loads((EXAMPLES / "draft-merge-patch.json").read_text())
    out: dict[str, Any] = _apply(doc, [_change(c) for c in batch["changes"]], registry).document
    assert doc == before
    assert _keys(out, "items") == ["P1.1", "P1.2", "P2.1", "P2.2", "P2.4", "P2.5"]
    assert _entity(out, "items", "P1.2")["title"] == "Token rotation service"
    assert "guidance_md" not in _entity(out, "items", "P1.2")
    assert _entity(out, "checks", "V1", "P1.2")["definition"]["timeout_seconds"] == 300
    assert (
        _entity(out, "checks", "V1", "P1.2")["definition"]["argv"]
        == _entity(doc, "checks", "V1", "P1.2")["definition"]["argv"]
    )
    assert len(out["rules"]) == 3
    added = _entity(out, "items", "P2.4")
    assert added["route"] == {"class": "implementation", "effort": "medium"}
    assert added["review"]["mode"] == "self"
    assert "P2.2/U2" not in _keys(out, "units")
    assert _entity(out, "items", "P2.5")["depends_on"] == ["P2.1", "P2.2", "P2.4"]
    assert _entity(out, "items", "P2.5")["id"] == _entity(doc, "items", "P2.3")["id"]
    assert {c["owner"] for c in out["checks"] if c["owner"].startswith("P2.")} == {"P2.1", "P2.2", "P2.5"}
    assert [c["owner"] for c in out["criteria"] if c["key"] == "AC4"] == ["P2.5"]


def test_the_typed_model_round_trips_every_batch_result(registry):
    batch = json.loads((EXAMPLES / "draft-merge-patch.json").read_text())
    out = _apply(_doc(), [_change(c) for c in batch["changes"]], registry).document
    with pytest.raises(
        ValidationFailed
    ):  # the added item has no id yet: ids are assigned before the typed model
        from_document(out)
    ids = iter(range(1, 100))

    class Ids:
        def new_id(self) -> UUID:
            return UUID(f"0192f5c9-0000-7000-8000-{next(ids):012d}")

    generator = Ids()
    assigned, new_ids = assign_missing_ids(out, generator)
    assert [a.key for a in new_ids] == ["P2.4"]
    spec, findings = from_document(assigned)
    assert findings == ()
    canonical: dict[str, Any] = to_document(spec)
    assert canonical["items"][4]["key"] == "P2.4"
    assert to_document(from_document(to_document(spec))[0]) == to_document(spec)  # canonical form is stable


# ------------------------------------------------------------------------------------------- atomicity


def test_invalid_edit_n_leaves_the_document_unchanged_without_a_successful_prefix():
    doc = _doc()
    before = copy.deepcopy(doc)
    changes = [
        PatchChange("P1.2", {"title": "renamed"}),
        PatchChange("plan", {"title": "New title"}),
        PatchChange("P9.9", {"title": "x"}),
        PatchChange("P1.1", {"title": "never reached"}),
    ]
    error = _failure(doc, changes)
    assert isinstance(error, NotFound)
    assert error.code is ErrorCode.NOT_FOUND
    assert dict(error.details) == {"kind": "entity", "ref": "P9.9", "change_index": 2, "applied": False}
    assert doc == before


def test_operation_errors_carry_the_zero_based_index_and_applied_false():
    doc = _doc()
    for index, (change, code) in enumerate(
        [
            (PatchChange("P1.1", {"key": "P1.9"}), ErrorCode.FIELD_OWNED),
            (RekeyChange("P1.1", "P1.2"), ErrorCode.ALREADY_EXISTS),
            (MoveChange("P1.1", "P2.1", None), ErrorCode.INVALID_REFERENCE),
        ]
    ):
        error = _failure(doc, [PatchChange("plan", {})] * index + [change])
        assert error.code is code
        assert (error.details["change_index"], error.details["applied"]) == (index, False)


def test_final_schema_error_belongs_to_the_final_document_and_names_no_operation(registry):
    doc = _doc()
    error = _failure(
        doc, [PatchChange("P1.1", {"title": "ok"}), PatchChange("P1.2", {"title": ""})], registry
    )
    assert error.code is ErrorCode.SCHEMA_INVALID
    assert "change_index" not in error.details
    assert error.details["applied"] is False
    assert error.details["issues"]


def test_schema_is_checked_once_after_the_whole_group(registry):
    calls: list[int] = []
    doc = _doc()
    # P2.3 is invalid after the first change and valid again after the second: only the final state is checked
    changes = [PatchChange("P2.3", {"title": ""}), PatchChange("P2.3", {"title": "Back"})]

    def validate(d: JsonObject) -> None:
        calls.append(1)
        registry.require_valid(SPECIFICATION, d)

    apply_changes(doc, changes, defaults=DEFAULTS, validate=validate)
    assert calls == [1]


def test_semantic_findings_such_as_a_cycle_do_not_reject_the_batch(registry):
    out = _apply(_doc(), [PatchChange("P1.1", {"depends_on": ["P1.2"]})], registry).document
    assert _entity(out, "items", "P1.1")["depends_on"] == [
        "P1.2"
    ]  # a cycle is a finding that blocks publish only


# ------------------------------------------------------------------------------------------ merge patch


@pytest.mark.parametrize(
    ("target", "patch", "result"),
    [  # RFC 7396 appendix A
        ({"a": "b"}, {"a": "c"}, {"a": "c"}),
        ({"a": "b"}, {"b": "c"}, {"a": "b", "b": "c"}),
        ({"a": "b"}, {"a": None}, {}),
        ({"a": "b", "b": "c"}, {"a": None}, {"b": "c"}),
        ({"a": ["b"]}, {"a": "c"}, {"a": "c"}),
        ({"a": "c"}, {"a": ["b"]}, {"a": ["b"]}),
        ({"a": {"b": "c"}}, {"a": {"b": "d", "c": None}}, {"a": {"b": "d"}}),
        ({"a": [{"b": "c"}]}, {"a": [1]}, {"a": [1]}),
        (["a", "b"], ["c", "d"], ["c", "d"]),
        ({"a": "b"}, ["c"], ["c"]),
        ({"a": "foo"}, None, None),
        ({"a": "foo"}, "bar", "bar"),
        ({"e": None}, {"a": 1}, {"e": None, "a": 1}),
        ([1, 2], {"a": "b", "c": None}, {"a": "b"}),
        ({}, {"a": {"bb": {"ccc": None}}}, {"a": {"bb": {}}}),
    ],
)
def test_merge_patch_follows_rfc_7396(target, patch, result):
    original = copy.deepcopy(target)
    assert merge_patch(target, patch) == result
    assert target == original


def test_arrays_are_replaced_whole_and_null_deletes_the_key():
    out = _apply(_doc(), [PatchChange("P1.2", {"implements": ["R2"], "decisions": None})]).document
    assert _entity(out, "items", "P1.2")["implements"] == ["R2"]
    assert "decisions" not in _entity(out, "items", "P1.2")


def test_phase_depends_on_null_is_the_implicit_previous_phase_and_empty_is_none():
    doc = _doc()
    cleared = _apply(doc, [PatchChange("P1", {"depends_on": None})]).document
    assert "depends_on" not in _entity(cleared, "phases", "P1")
    rebuilt: dict[str, Any] = to_document(from_document(cleared)[0])
    assert rebuilt["phases"][0].get("depends_on") is None
    emptied = _apply(doc, [PatchChange("P2", {"depends_on": []})]).document
    assert _entity(emptied, "phases", "P2")["depends_on"] == []
    typed = from_document(emptied)[0]
    assert typed.phases[1].depends_on == ()
    assert from_document(cleared)[0].phases[0].depends_on is None


def test_unit_route_null_returns_the_inheritance_from_the_item():
    doc = _doc()
    routed = _apply(doc, [PatchChange("P1.1/U1", {"route": {"class": "frontier", "effort": "max"}})]).document
    spec = from_document(routed)[0]
    unit = spec.by_key("P1.1/U1")
    route = spec.route_for(unit.id)
    assert route is not None
    assert route.model_class is ModelClass.FRONTIER
    reset = from_document(_apply(routed, [PatchChange("P1.1/U1", {"route": None})]).document)[0]
    assert reset.route_for(reset.by_key("P1.1/U1").id) == _typed(reset, "P1.1", Item).route


# --------------------------------------------------------------------------------------- owned fields


@pytest.mark.parametrize(
    ("target", "patch", "field"),
    [
        ("P1.1", {"id": "0192f5c4-0000-7000-8000-0000000000ff"}, "id"),
        ("P1.1", {"key": "P1.9"}, "key"),
        ("P1.1", {"phase": "P2"}, "phase"),
        ("P1.1:V1", {"owner": "P1.2"}, "owner"),
        ("P1.1:V1", {"key": "V9"}, "key"),
        ("P1.1/U1", {"key": "P1.1/U9"}, "key"),
        ("D1", {"id": None}, "id"),
        ("plan", {"schema": "urn:other"}, "schema"),
        ("plan", {"phases": []}, "phases"),
        ("plan", {"items": None}, "items"),
        ("plan", {"checks": []}, "checks"),
    ],
)
def test_changing_an_owned_field_is_field_owned(target, patch, field):
    error = _failure(_doc(), [PatchChange(target, patch)])
    assert error.code is ErrorCode.FIELD_OWNED
    assert (error.details["target"], error.details["field"]) == (target, field)


def test_the_same_value_of_an_owned_field_is_a_no_op():
    doc = _doc()
    item = _entity(doc, "items", "P1.1")
    out = _apply(
        doc,
        [
            PatchChange("P1.1", {"id": item["id"], "key": "P1.1", "phase": "P1", "title": "T"}),
            PatchChange("plan", {"schema": doc["schema"], "phases": doc["phases"]}),
        ],
    ).document
    assert _entity(out, "items", "P1.1")["title"] == "T"
    assert out["phases"] == doc["phases"]


def test_plan_patch_changes_only_root_fields_and_keeps_the_entity_arrays():
    doc = _doc()
    out = _apply(
        doc, [PatchChange("plan", {"goal": "New goal", "context_md": None, "rules": ["only one"]})]
    ).document
    assert out["goal"] == "New goal"
    assert "context_md" not in out
    assert out["rules"] == ["only one"]
    assert out["items"] == doc["items"]
    assert out["phases"] == doc["phases"]


def test_brief_and_execution_constraints_patch_their_sections(registry):
    out: dict[str, Any] = _apply(
        _doc(),
        [
            PatchChange("execution_constraints", {"max_parallel_units": 8, "required_isolation": None}),
            PatchChange("brief", {"constraints": ["one"]}),
        ],
        registry,
    ).document
    assert out["execution_constraints"] == {
        "strategy": "dag",
        "forbidden_paths": _doc()["execution_constraints"]["forbidden_paths"],
        "max_parallel_units": 8,
    }
    assert out["brief"]["constraints"] == ["one"]
    assert out["brief"]["messages"] == _doc()["brief"]["messages"]


# --------------------------------------------------------------------------------------- identity


def test_rekey_keeps_the_entity_id_and_a_later_edit_by_id_addresses_the_same_entity():
    doc = _doc()
    uid = f"entity:{_entity(doc, 'items', 'P2.3')['id']}"
    out = _apply(
        doc,
        [
            RekeyChange("P2.3", "P2.5"),
            PatchChange(uid, {"title": "Sign-off"}),
            MoveChange(uid, "P2.1", None),
            RekeyChange(uid, "P2.6"),
            PatchChange(uid, {"summary": "after two renames"}),
        ],
    ).document
    renamed = _entity(out, "items", "P2.6")
    assert renamed["id"] == _entity(doc, "items", "P2.3")["id"]
    assert (renamed["title"], renamed["summary"]) == ("Sign-off", "after two renames")
    assert _keys(out, "items") == ["P1.1", "P1.2", "P2.1", "P2.6", "P2.2"]


def test_added_objects_are_addressed_by_their_display_key_before_ids_exist():
    new: JsonObject = {"key": "P2.4", "phase": "P2", "title": "t", "summary": "s", "why": "w"}
    out = _apply(
        _doc(),
        [
            AddChange(EntityKind.ITEM, new, None),
            PatchChange("P2.4", {"title": "patched"}),
            AddChange(EntityKind.UNIT, {"key": "P2.4/U1", "title": "u", "goal": "g"}, None),
        ],
    ).document
    assert _entity(out, "items", "P2.4")["title"] == "patched"
    assert "id" not in _entity(out, "items", "P2.4")
    assert "P2.4/U1" in _keys(out, "units")


def test_import_kind_is_not_changed_by_batch_edits():
    doc = _doc()
    out = _apply(doc, [PatchChange("R1", {"statement": "reworded"})]).document
    assert _entity(out, "requirements", "R1")["id"] == _entity(doc, "requirements", "R1")["id"]
    assert _keys(out, "items") == _keys(doc, "items")


# --------------------------------------------------------------------------------------------- add


@pytest.mark.parametrize(
    ("mode", "review"),
    [
        (ReviewMode.REQUIRED, {"mode": "required"}),
        (ReviewMode.SELF, {"mode": "self", "reason": "planning.defaults.review_mode"}),
        (
            ReviewMode.WAIVED,
            {"mode": "waived", "reason": "planning.defaults.review_mode", "waived_by": "planning.defaults"},
        ),
    ],
)
def test_add_item_fills_route_and_review_from_defaults_only_when_absent(mode, review, registry):
    defaults = ItemDefaults(ModelClass.ECONOMY, Effort.LOW, mode)
    bare: JsonObject = {"key": "P1.3", "phase": "P1", "title": "t", "summary": "s", "why": "w"}
    out = apply_changes(_doc(), [AddChange(EntityKind.ITEM, bare, None)], defaults=defaults).document
    added = _entity(out, "items", "P1.3")
    assert added["route"] == {"class": "economy", "effort": "low"}
    assert added["review"] == review
    registry.require_valid(SPECIFICATION, out)
    explicit = {
        **bare,
        "route": {"class": "frontier", "effort": "max"},
        "review": {"mode": "self", "reason": "r"},
    }
    kept = apply_changes(_doc(), [AddChange(EntityKind.ITEM, explicit, None)], defaults=defaults).document
    assert _entity(kept, "items", "P1.3")["route"] == {"class": "frontier", "effort": "max"}
    assert _entity(kept, "items", "P1.3")["review"] == {"mode": "self", "reason": "r"}


def test_defaults_are_not_substituted_by_patch_or_other_kinds():
    out = _apply(_doc(), [PatchChange("P1.1", {"route": None})]).document
    assert "route" not in _entity(out, "items", "P1.1")
    out = _apply(
        _doc(), [AddChange(EntityKind.UNIT, {"key": "P1.2/U1", "title": "u", "goal": "g"}, None)]
    ).document
    assert "route" not in _entity(out, "units", "P1.2/U1")


def test_add_places_an_item_after_its_neighbour_or_at_the_end_of_its_phase():
    base = {"title": "t", "summary": "s", "why": "w", "review": {"mode": "self", "reason": "r"}}
    out = _apply(
        _doc(),
        [
            AddChange(EntityKind.ITEM, {**base, "key": "P1.3", "phase": "P1"}, None),
            AddChange(EntityKind.ITEM, {**base, "key": "P2.4", "phase": "P2"}, "P2.1"),
        ],
    ).document
    assert _keys(out, "items") == ["P1.1", "P1.2", "P1.3", "P2.1", "P2.4", "P2.2", "P2.3"]


def test_add_rejects_a_neighbour_of_another_kind_or_phase_and_an_existing_key():
    base = {"title": "t", "summary": "s", "why": "w"}
    for after in ("P2.1", "P1", "R1"):
        error = _failure(_doc(), [AddChange(EntityKind.ITEM, {**base, "key": "P1.3", "phase": "P1"}, after)])
        assert error.code is ErrorCode.INVALID_REFERENCE
        assert error.details["change_index"] == 0
    error = _failure(_doc(), [AddChange(EntityKind.ITEM, {**base, "key": "P1.1", "phase": "P1"}, None)])
    assert error.code is ErrorCode.ALREADY_EXISTS


def test_add_plan_relation_appends(registry):
    out: dict[str, Any] = _apply(
        _doc(), [AddChange("plan_relation", {"kind": "related", "target": "PLAN4"}, None)], registry
    ).document
    assert [r["target"] for r in out["plan_relations"]] == ["PLAN3", "PLAN4"]


# ------------------------------------------------------------------------------------------- remove


def test_remove_without_cascade_leaves_dangling_references_for_validation():
    out: dict[str, Any] = _apply(_doc(), [RemoveChange("P2.2", False)]).document
    assert "P2.2" not in _keys(out, "items")
    assert "P2.2" in _entity(out, "items", "P2.3")["depends_on"]
    assert any(c["owner"] == "P2.2" for c in out["checks"])
    assert "P2.2/U1" in _keys(out, "units")


def test_cascade_remove_takes_owned_entities_and_scrubs_the_references_to_them(registry):
    doc = _doc()
    out: dict[str, Any] = _apply(doc, [RemoveChange("P2.2", True)], registry).document
    assert "P2.2" not in _keys(out, "items")
    assert not any(k.startswith("P2.2/") for k in _keys(out, "units"))
    assert not any(c["owner"] == "P2.2" for c in out["checks"])
    assert "AC3" not in _keys(out, "criteria")
    assert _entity(out, "items", "P2.3")["depends_on"] == ["P2.1"]
    batches = _entity(out, "phases", "P2")["batches"]
    assert batches[0]["items"] == ["P2.1"]
    assert "P2.2" not in _entity(out, "requirements", "R2")["owners"]
    assert _entity(out, "decisions", "D1")["applies_to"] == ["P1.2"]


def test_cascade_remove_of_a_phase_removes_its_items_units_checks_and_criteria(registry):
    out: dict[str, Any] = _apply(_doc(), [RemoveChange("P2", True)], registry).document
    assert _keys(out, "phases") == ["P1"]
    assert _keys(out, "items") == ["P1.1", "P1.2"]
    assert all(u.startswith("P1.") for u in _keys(out, "units"))
    assert {c["owner"] for c in out["checks"]} <= {"P1", "P1.1", "P1.2"}
    assert all(c["owner"].startswith("P1.") for c in out["criteria"])


def test_remove_by_id_and_unknown_target():
    doc = _doc()
    out = _apply(doc, [RemoveChange(f"entity:{_entity(doc, 'items', 'P2.2')['id']}", False)]).document
    assert "P2.2" not in _keys(out, "items")
    assert _failure(doc, [RemoveChange("P9.9", False)]).details["change_index"] == 0


# --------------------------------------------------------------------------------------------- move


def test_move_after_before_and_to_the_start_of_the_phase():
    assert _keys(_apply(_doc(), [MoveChange("P2.3", "P2.1", None)]).document, "items") == [
        "P1.1",
        "P1.2",
        "P2.1",
        "P2.3",
        "P2.2",
    ]
    assert _keys(_apply(_doc(), [MoveChange("P2.1", None, "P2.3")]).document, "items") == [
        "P1.1",
        "P1.2",
        "P2.2",
        "P2.1",
        "P2.3",
    ]
    assert _keys(_apply(_doc(), [MoveChange("P2.3", None, None)]).document, "items") == [
        "P1.1",
        "P1.2",
        "P2.3",
        "P2.1",
        "P2.2",
    ]
    assert _keys(_apply(_doc(), [MoveChange("P1.1", "P1.2", None)]).document, "items") == [
        "P1.2",
        "P1.1",
        "P2.1",
        "P2.2",
        "P2.3",
    ]


def test_move_rejects_both_anchors_itself_other_kinds_and_other_phases():
    for change in (
        MoveChange("P2.3", "P2.1", "P2.2"),
        MoveChange("P2.3", "P2.3", None),
        MoveChange("P2.3", "R1", None),
        MoveChange("P2.3", "P1.2", None),
    ):
        error = _failure(_doc(), [change])
        assert error.code is ErrorCode.INVALID_REFERENCE
        assert error.details["applied"] is False


# ---------------------------------------------------------------------------- split / merge / policy


def test_split_is_an_explicit_batch_with_author_chosen_ids_and_rewritten_references(registry):
    doc = _doc()
    kept = _entity(doc, "items", "P1.2")
    half = {
        "key": "P1.3",
        "phase": "P1",
        "title": "Second half",
        "summary": "s",
        "why": "w",
        "id": "0192f5c9-0000-7000-8000-000000000001",
        "review": {"mode": "self", "reason": "r"},
    }
    out = _apply(
        doc,
        [
            AddChange(EntityKind.ITEM, half, "P1.2"),
            PatchChange("P1.2", {"title": "First half"}),
            PatchChange("P1.3", {"depends_on": ["P1.2"]}),
            PatchChange("AC1", {"owner": "P1.3"}),
            RekeyChange("P1.2:V1", "P1.3:V1"),
        ],
        registry,
    ).document
    assert _entity(out, "items", "P1.2")["id"] == kept["id"]
    assert _entity(out, "items", "P1.3")["id"] == half["id"]
    assert _entity(out, "criteria", "AC1")["checks"] == [
        "P1.3:V1"
    ]  # the check moved: the reference followed it
    assert _entity(out, "criteria", "AC1")["owner"] == "P1.3"


def test_merge_leaves_the_removed_items_references_unrewritten_until_the_author_rewrites_them():
    doc = _doc()
    out = _apply(doc, [RemoveChange("P2.2", False)]).document
    assert "P2.2" in _entity(out, "phases", "P2")["batches"][0]["items"]  # not mapped to any survivor
    fixed = _apply(
        out, [PatchChange("P2", {"batches": [{"key": "B1", "items": ["P2.1"], "mode": "required"}]})]
    ).document
    assert _entity(fixed, "phases", "P2")["batches"][0]["items"] == ["P2.1"]


def test_work_policy_absent_and_empty_are_distinct_and_survive_patching(registry):
    doc = _doc()
    empty = _apply(doc, [PatchChange("P1.1", {"work_policy": {}})], registry).document
    assert _entity(empty, "items", "P1.1")["work_policy"] == {}
    assert "work_policy" not in _entity(doc, "items", "P1.1")
    typed = from_document(empty)[0]
    assert _typed(typed, "P1.1", Item).work_policy == WorkPolicyOverride()
    assert _typed(typed, "P1.2", Item).work_policy is None
    rebuilt: dict[str, Any] = to_document(typed)
    assert rebuilt["items"][0]["work_policy"] == {}


def test_work_policy_roles_merge_by_key_and_null_resets(registry):
    doc = _doc()
    first = _apply(
        doc,
        [
            PatchChange(
                "P1.1", {"work_policy": {"role_intensity": {"executor": "light", "reviewer": "heavy"}}}
            )
        ],
        registry,
    ).document
    second = _apply(
        first,
        [
            PatchChange(
                "P1.1",
                {
                    "work_policy": {
                        "role_intensity": {"executor": "medium"},
                        "verification_intensity": "heavy",
                    }
                },
            )
        ],
        registry,
    ).document
    assert _entity(second, "items", "P1.1")["work_policy"] == {
        "role_intensity": {"executor": "medium", "reviewer": "heavy"},
        "verification_intensity": "heavy",
    }
    third = _apply(
        second, [PatchChange("P1.1", {"work_policy": {"role_intensity": {"reviewer": None}}})], registry
    ).document
    assert _entity(third, "items", "P1.1")["work_policy"]["role_intensity"] == {"executor": "medium"}
    reset = _apply(third, [PatchChange("P1.1", {"work_policy": None})], registry).document
    assert "work_policy" not in _entity(reset, "items", "P1.1")
    assert reset == doc


def test_unit_work_policy_does_not_touch_its_item_or_neighbours(registry):
    doc = _doc()
    out = _apply(
        doc, [PatchChange("P1.1/U1", {"work_policy": {"role_intensity": {"scout": "light"}}})], registry
    ).document
    assert "work_policy" not in _entity(out, "items", "P1.1")
    assert "work_policy" not in _entity(out, "units", "P1.1/U2")
    spec = from_document(out)[0]
    unit_policy = _typed(spec, "P1.1/U1", Unit).work_policy
    assert unit_policy is not None
    assert unit_policy.role_intensity == {RoleName.SCOUT: Intensity.LIGHT}
    item_policy = WorkPolicyOverride(
        {RoleName.SCOUT: Intensity.HEAVY, RoleName.EXECUTOR: Intensity.HEAVY}, Intensity.MEDIUM
    )
    effective = unit_policy.merged_over(item_policy)
    assert effective.role_intensity is not None
    assert dict(effective.role_intensity) == {
        RoleName.SCOUT: Intensity.LIGHT,
        RoleName.EXECUTOR: Intensity.HEAVY,
    }
    assert effective.verification_intensity is Intensity.MEDIUM
    assert unit_policy.merged_over(None) == unit_policy


def test_invalid_work_policy_is_a_final_schema_error(registry):
    error = _failure(
        _doc(), [PatchChange("P1.1", {"work_policy": {"role_intensity": {"boss": "light"}}})], registry
    )
    assert error.code is ErrorCode.SCHEMA_INVALID
    assert "change_index" not in error.details
    error = _failure(
        _doc(),
        [PatchChange("P1.1", {"work_policy": {"role_intensity": {"executor": None, "scout": "x"}}})],
        registry,
    )
    assert error.code is ErrorCode.SCHEMA_INVALID


def test_conflict_and_validation_errors_are_the_catalog_classes():
    assert isinstance(_failure(_doc(), [RekeyChange("P1.1", "P1.2")]), Conflict)
    assert isinstance(_failure(_doc(), [PatchChange("P1.1", {"key": "x"})]), ValidationFailed)
