"""Pure three-way rebase of a draft onto the current revision (planning §5.10, G1)."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.planning.domain.canonical import normalize_document
from skm.modules.planning.domain.rebase import (
    ABSENT,
    ConflictKind,
    RebaseConflict,
    RebaseOutcome,
    RebaseResolution,
    SchemaValidator,
    _merge3,
    rebase_document,
)
from skm.modules.planning.domain.specification import EntityKind
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/rebase-three-way.json"
SPECIFICATION = "urn:skm:planning:specification:v1"

P2 = "0192f5c4-0000-7000-8000-00000000000b"
ITEM_1 = "0192f5c4-0000-7000-8000-000000000014"
ITEM_2 = "0192f5c4-0000-7000-8000-000000000015"
ITEM_3 = "0192f5c4-0000-7000-8000-000000000016"
DRAFT_ITEM = "0192f5c4-0000-7000-8000-000000000101"
CURRENT_ITEM = "0192f5c4-0000-7000-8000-000000000201"
CHECK = "0192f5c4-0000-7000-8000-000000000028"
TITLE_CONFLICT = "rc-9cbaaa46efcf"
KEY_CONFLICT = "rc-f29269c02890"


@pytest.fixture(scope="module")
def schema() -> SchemaValidator:
    return SchemaRegistry.load_default().validator(SPECIFICATION)


class _AcceptAll:
    """A validator for structural cases whose documents are not full specifications."""

    def issues(self, instance: object) -> tuple[()]:
        return ()


class _Issue:
    pointer = "/items/0/title"
    schema_pointer = "#/properties/items"
    message = "too short"


class _Rejects:
    def issues(self, instance: object) -> tuple[_Issue]:
        return (_Issue(),)


ACCEPT_ALL = _AcceptAll()


def _example() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


def _three() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """``(base, yours, theirs)`` of the normative example."""
    example = _example()
    return (
        example["base_revision"]["document"],
        example["draft"]["document"],
        example["theirs_revision"]["document"],
    )


def _resolutions(raw: list[dict[str, Any]]) -> list[RebaseResolution]:
    return [RebaseResolution(r["conflict_id"], r.get("keep"), r.get("new_key")) for r in raw]


def _keep(conflict_id: str, side: str) -> RebaseResolution:
    return RebaseResolution(conflict_id, cast("Any", side), None)


def _rekey(conflict_id: str, new_key: str) -> RebaseResolution:
    return RebaseResolution(conflict_id, None, new_key)


def _merged(outcome: RebaseOutcome) -> dict[str, Any]:
    """The document of a rebase that must have succeeded."""
    assert outcome.conflicts == ()
    assert outcome.document is not None
    return cast("dict[str, Any]", outcome.document)


def _value(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast("dict[str, Any]", value)


def _wire(conflict: RebaseConflict) -> dict[str, Any]:
    """The ``details.conflicts`` form: absent values, empty lists and unset ids are left out."""
    out: dict[str, Any] = {
        "conflict_id": conflict.conflict_id,
        "kind": conflict.kind.value,
        "entity_id": None if conflict.entity_id is None else str(conflict.entity_id),
        "entity_kind": None if conflict.entity_kind is None else conflict.entity_kind.value,
        "key": conflict.key,
        "field": conflict.field,
        "pointer": conflict.pointer,
        "resolutions": list(conflict.resolutions),
    }
    for name in ("base", "yours", "theirs"):
        value = getattr(conflict, name)
        if value is not ABSENT:
            out[name] = value
    if conflict.colliding_entity_id is not None:
        out["colliding_entity_id"] = str(conflict.colliding_entity_id)
    if conflict.children_kept:
        out["children_kept"] = [str(i) for i in conflict.children_kept]
    if conflict.issues:
        out["issues"] = list(conflict.issues)
    return out


def _item(entity_id: str, key: str, phase: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": entity_id,
        "key": key,
        "phase": phase,
        "title": title,
        "summary": f"{title}.",
        "why": "Part of the rotation work.",
        "review": {"mode": "required", "profile": "code-review", "max_rounds": 2},
        **extra,
    }


def _new_phase(entity_id: str, key: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": entity_id,
        "key": key,
        "title": title,
        "goal": f"{title}.",
        "design_state": "detailed",
        **extra,
    }


def _by_id(doc: dict[str, Any], array: str, entity_id: str) -> dict[str, Any]:
    return next(e for e in doc[array] if e["id"] == entity_id)


def _phase(doc: dict[str, Any], key: str) -> dict[str, Any]:
    return next(p for p in doc["phases"] if p["key"] == key)


def _two_phases() -> dict[str, Any]:
    """The example base with a second phase P2 (depends on P1) holding item P2.1."""
    base = _three()[0]
    base["phases"].append(_new_phase(P2, "P2", "Roll the rotation out", depends_on=["P1"]))
    base["items"].append(_item("0192f5c4-0000-7000-8000-000000000301", "P2.1", "P2", "Flag rollout"))
    return base


def _agreeing() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The example without its two conflicts (current's P1.4 and title of P1.3 dropped)."""
    base, yours, theirs = _three()
    del yours["items"][3], theirs["items"][3]
    yours["items"][2]["title"] = theirs["items"][2]["title"]
    return base, yours, theirs


# ---------------------------------------------------------------------------------------------- golden


def test_first_attempt_reports_exactly_the_example_conflicts_and_no_document(schema):
    base, yours, theirs = _three()
    outcome = rebase_document(base, yours, theirs, [], schema=schema)

    expected = _example()["attempts"][0]["outcome"]["error"]["details"]["conflicts"]
    assert outcome.document is None
    assert [_wire(c) for c in outcome.conflicts] == expected
    assert outcome.resolved == 0


def test_second_attempt_matches_the_example_document_and_counters(schema):
    base, yours, theirs = _three()
    attempt = _example()["attempts"][1]
    outcome = rebase_document(
        base, yours, theirs, _resolutions(attempt["command"]["dto"]["resolutions"]), schema=schema
    )

    assert _merged(outcome) == normalize_document(attempt["outcome"]["document"])
    result = attempt["outcome"]["result"]
    assert (outcome.taken_from_current, outcome.kept_from_draft, outcome.resolved) == (
        result["taken_from_current"],
        result["kept_from_draft"],
        result["resolved"],
    )


def test_reference_survives_rekey_through_id_and_check_groups_merge_separately(schema):
    base, yours, theirs = _three()
    resolutions = [_keep(TITLE_CONFLICT, "theirs"), _rekey(KEY_CONFLICT, "P1.6")]
    document = _merged(rebase_document(base, yours, theirs, resolutions, schema=schema))

    draft_item = _by_id(document, "items", DRAFT_ITEM)
    assert (draft_item["key"], draft_item["depends_on"]) == ("P1.6", ["P1.5"])  # P1.2 -> P1.5 in current
    assert _by_id(document, "items", ITEM_2)["depends_on"] == ["P1.1", "P1.3"]
    check = _by_id(document, "checks", CHECK)
    assert check["title"] == "Repository and migration tests"  # draft
    assert check["definition"]["timeout_seconds"] == 900  # current
    assert [i["key"] for i in document["items"]] == ["P1.1", "P1.5", "P1.3", "P1.6", "P1.4"]


def test_inputs_are_not_mutated_with_or_without_resolutions(schema):
    base, yours, theirs = _three()
    snapshot = copy.deepcopy((base, yours, theirs))

    rebase_document(base, yours, theirs, [], schema=schema)
    resolutions = [_keep(TITLE_CONFLICT, "theirs"), _rekey(KEY_CONFLICT, "P1.6")]
    document = _merged(rebase_document(base, yours, theirs, resolutions, schema=schema))

    assert (base, yours, theirs) == snapshot
    document["items"][0]["title"] = "changed"
    assert theirs["items"][0]["title"] == yours["items"][0]["title"] == "Token table"


def test_conflict_ids_are_the_canonical_hash_and_stable_across_runs(schema):
    base, yours, theirs = _three()
    first = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    second = rebase_document(
        copy.deepcopy(base), copy.deepcopy(yours), copy.deepcopy(theirs), [], schema=schema
    )

    assert first == second.conflicts
    for conflict in first:
        text = json.dumps(
            [conflict.kind.value, str(conflict.entity_id), conflict.field], separators=(",", ":")
        )
        assert conflict.conflict_id == "rc-" + hashlib.sha256(text.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------------------------- resolutions


def test_unknown_resolution_id_is_an_invalid_reference(schema):
    base, yours, theirs = _three()
    resolutions = [
        _keep(TITLE_CONFLICT, "theirs"),
        _rekey(KEY_CONFLICT, "P1.6"),
        _keep("rc-000000000000", "yours"),
    ]

    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, resolutions, schema=schema)
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    assert caught.value.details["conflict_id"] == "rc-000000000000"


@pytest.mark.parametrize(
    ("title", "rekey"),
    [
        (_rekey(TITLE_CONFLICT, "P1.7"), _rekey(KEY_CONFLICT, "P1.6")),
        (_keep(TITLE_CONFLICT, "theirs"), _keep(KEY_CONFLICT, "yours")),
        (RebaseResolution(TITLE_CONFLICT, None, None), _rekey(KEY_CONFLICT, "P1.6")),
        (_keep(TITLE_CONFLICT, "theirs"), _rekey(KEY_CONFLICT, "P1.5")),
        (_keep(TITLE_CONFLICT, "theirs"), _rekey(KEY_CONFLICT, "P2")),
        (_keep(TITLE_CONFLICT, "theirs"), _rekey(KEY_CONFLICT, "P2.6")),
        (_keep(TITLE_CONFLICT, "theirs"), _keep(TITLE_CONFLICT, "yours")),
    ],
    ids=["new-key-on-field", "keep-on-collision", "empty", "taken-key", "other-kind", "no-phase", "twice"],
)
def test_resolution_of_the_wrong_shape_or_with_a_bad_new_key_is_schema_invalid(schema, title, rekey):
    base, yours, theirs = _three()
    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [title, rekey], schema=schema)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["issues"]


def test_keep_yours_on_a_field_takes_the_draft_value(schema):
    base, yours, theirs = _three()
    resolutions = [_keep(TITLE_CONFLICT, "yours"), _rekey(KEY_CONFLICT, "P1.6")]
    outcome = rebase_document(base, yours, theirs, resolutions, schema=schema)
    assert _by_id(_merged(outcome), "items", ITEM_3)["title"] == "Operator docs"
    assert outcome.resolved == 2


def test_partial_resolutions_leave_the_rest_open_and_no_document(schema):
    base, yours, theirs = _three()
    outcome = rebase_document(base, yours, theirs, [_keep(TITLE_CONFLICT, "theirs")], schema=schema)
    assert outcome.document is None
    assert [c.kind for c in outcome.conflicts] == [ConflictKind.KEY_COLLISION]
    assert outcome.resolved == 1


def test_schema_errors_of_the_result_are_one_schema_conflict_without_resolutions():
    base, yours, theirs = _agreeing()

    outcome = rebase_document(base, yours, theirs, [], schema=_Rejects())

    assert outcome.document is None
    (conflict,) = outcome.conflicts
    assert (conflict.kind, conflict.resolutions, conflict.entity_id) == (ConflictKind.SCHEMA, (), None)
    issue = {"pointer": "/items/0/title", "schema_pointer": "#/properties/items", "message": "too short"}
    assert conflict.issues == (issue,)
    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=_Rejects())
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


# ---------------------------------------------------------------------------------------------- values


def test_absent_is_a_value_of_its_own_and_not_null():
    assert _merge3(ABSENT, None, ABSENT) == (None, "yours")
    assert _merge3(None, None, ABSENT) == (ABSENT, "theirs")
    assert _merge3(ABSENT, ABSENT, ABSENT) == (ABSENT, None)
    assert _merge3(1, True, 1) == (True, "yours")  # canonical JSON equality, not Python equality
    assert _merge3("a", None, ABSENT) is None


def test_plan_fields_merge_whole_with_absent_as_a_value(schema):
    base, yours, theirs = _agreeing()
    base["context_md"] = yours["context_md"] = "Old context."  # current removed it, the draft kept it
    yours["non_goals"] = ["No SSO."]  # the draft added it

    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    assert "context_md" not in document
    assert document["non_goals"] == ["No SSO."]

    theirs["context_md"] = "New context."
    yours["context_md"] = "Draft context."
    del base["context_md"]
    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert (conflict.kind, conflict.entity_id, conflict.field, conflict.pointer) == (
        ConflictKind.FIELD, None, "context_md", "/context_md",
    )  # fmt: skip
    assert (conflict.base, conflict.yours, conflict.theirs) == (ABSENT, "Draft context.", "New context.")
    text = json.dumps(["field", "plan", "context_md"], separators=(",", ":"))
    assert conflict.conflict_id == "rc-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def test_check_kind_and_definition_merge_as_one_group(schema):
    base, _, theirs = _three()
    yours = copy.deepcopy(base)
    yours["checks"][0]["definition"]["argv"] = ["pytest", "-q"]  # the draft changes argv, current the timeout

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    conflict = next(c for c in outcome.conflicts if c.entity_kind is EntityKind.CHECK)
    assert (conflict.field, conflict.pointer, conflict.key) == ("kind", "/checks/0/kind", "P1.1:V1")
    assert set(_value(conflict.base)) == {"kind", "definition"}
    assert _value(conflict.yours)["definition"]["argv"] == ["pytest", "-q"]
    assert _value(conflict.theirs)["definition"]["timeout_seconds"] == 900


def test_reference_sets_merge_without_conflicts(schema):
    base = _three()[0]
    base["items"][2]["depends_on"] = ["P1.1"]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"][2]["depends_on"] = ["P1.2"]  # the draft drops P1.1 and adds P1.2
    theirs["items"][2]["depends_on"] = ["P1.1", "P1.2"]  # current adds P1.2 as well

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    assert _merged(outcome)["items"][2]["depends_on"] == ["P1.2"]
    assert (outcome.kept_from_draft, outcome.taken_from_current) == (1, 1)

    del yours["items"][2]["depends_on"]  # the draft empties it: an empty item set is left out
    theirs["items"][2]["depends_on"] = ["P1.1"]
    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    assert "depends_on" not in document["items"][2]


def test_reordering_a_set_is_not_a_change_of_the_set(schema):
    base = _three()[0]
    base["items"][2]["depends_on"] = ["P1.1", "P1.2"]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"][2]["depends_on"] = ["P1.2", "P1.1"]

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    assert (outcome.kept_from_draft, outcome.taken_from_current) == (0, 0)


def test_empty_phase_dependency_merge_preserves_explicit_empty(schema):
    base = _two_phases()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    _phase(yours, "P2")["depends_on"] = []  # the draft cuts the dependency: P2 runs without P1
    _phase(theirs, "P2")["goal"] = "Roll the rotation out in waves."  # an independent text edit

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    phase = _phase(_merged(outcome), "P2")
    assert phase["depends_on"] == []  # explicit: not left out, so the implicit P1 does not come back
    assert phase["goal"] == "Roll the rotation out in waves."
    assert (outcome.kept_from_draft, outcome.taken_from_current) == (1, 1)

    _phase(theirs, "P2")["depends_on"] = []  # both sides cut it
    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    assert _phase(document, "P2")["depends_on"] == []


def test_absent_phase_dependency_goes_through_merge3_not_set_coercion(schema):
    base = _two_phases()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    del _phase(yours, "P2")["depends_on"]  # the draft returns to the implicit previous phase

    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    assert "depends_on" not in _phase(document, "P2")

    _phase(theirs, "P2")["depends_on"] = []  # current makes it explicitly empty: absent and [] differ
    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert (conflict.kind, conflict.field) == (ConflictKind.FIELD, "depends_on")
    assert (conflict.base, conflict.yours, conflict.theirs) == (["P1"], ABSENT, [])

    del _phase(base, "P2")["depends_on"]  # absent in base and yours, [] in theirs: current's change
    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    assert _phase(document, "P2")["depends_on"] == []


# Authored JSON spelled like the markers the id space once used internally: data, never a reference.
LOOKALIKES = [{"\x00local": "a"}, {"\x00unresolved": "a"}, {"\x00as_written": "a"}, {"local": "a"}]


@pytest.mark.parametrize("lookalike", LOOKALIKES, ids=["local", "unresolved", "as-written", "plain"])
def test_extension_values_stay_literal_whatever_they_look_like(schema, lookalike):
    base, yours, theirs = _agreeing()
    for doc in (base, yours, theirs):
        doc["extensions"] = {"acme/tool": {"schema_version": 1, "value": "a"}}
    yours["extensions"]["acme/tool"]["value"] = lookalike  # a draft edit, not a respelling of "a"
    theirs["extensions"]["acme/tool"]["value"] = "b"

    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert (conflict.kind, conflict.field) == (ConflictKind.FIELD, "extensions")
    assert _value(conflict.yours)["acme/tool"]["value"] == lookalike

    kept = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=schema)
    assert _merged(kept)["extensions"]["acme/tool"]["value"] == lookalike

    theirs["extensions"]["acme/tool"]["value"] = "a"  # current leaves it: the draft's edit is taken
    unedited = copy.deepcopy(yours)
    unedited["extensions"]["acme/tool"]["value"] = "a"
    control = rebase_document(base, unedited, theirs, [], schema=schema)
    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    assert _merged(outcome)["extensions"]["acme/tool"]["value"] == lookalike
    assert outcome.kept_from_draft == control.kept_from_draft + 1


@pytest.mark.parametrize("lookalike", LOOKALIKES, ids=["local", "unresolved", "as-written", "plain"])
def test_lookalike_edit_of_an_entity_current_deleted_is_a_modify_delete_conflict(lookalike):
    base = _three()[0]
    base["items"][2]["extensions"] = {"acme/tool": {"schema_version": 1, "value": "a"}}
    yours = copy.deepcopy(base)
    yours["items"][2]["extensions"]["acme/tool"]["value"] = lookalike
    theirs = _without_item(base, ITEM_3)

    (conflict,) = rebase_document(base, yours, theirs, [], schema=ACCEPT_ALL).conflicts
    assert (conflict.kind, str(conflict.entity_id)) == (ConflictKind.MODIFY_DELETE, ITEM_3)

    kept = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=ACCEPT_ALL)
    item = _by_id(_merged(kept), "items", ITEM_3)
    assert item["extensions"]["acme/tool"]["value"] == lookalike


# ---------------------------------------------------------------------------------------------- presence


def _without_item(doc: dict[str, Any], entity_id: str) -> dict[str, Any]:
    out = copy.deepcopy(doc)
    out["items"] = [i for i in out["items"] if i["id"] != entity_id]
    return out


def _ids(doc: dict[str, Any], array: str) -> list[str]:
    return [e["id"] for e in doc[array]]


def test_one_sided_deletion_of_an_untouched_entity_is_taken(schema):
    base = _three()[0]
    outcome = rebase_document(base, copy.deepcopy(base), _without_item(base, ITEM_3), [], schema=schema)
    assert _ids(_merged(outcome), "items") == [ITEM_1, ITEM_2]
    assert (outcome.taken_from_current, outcome.kept_from_draft) == (1, 0)

    outcome = rebase_document(base, _without_item(base, ITEM_3), copy.deepcopy(base), [], schema=schema)
    assert _ids(_merged(outcome), "items") == [ITEM_1, ITEM_2]
    assert (outcome.taken_from_current, outcome.kept_from_draft) == (0, 1)


def test_delete_modify_conflict_and_its_resolutions(schema):
    base = _three()[0]
    yours = _without_item(base, ITEM_3)
    theirs = copy.deepcopy(base)
    theirs["items"][2]["title"] = "Runbook"

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    (conflict,) = outcome.conflicts
    assert (conflict.kind, conflict.key, conflict.pointer, conflict.field) == (
        ConflictKind.DELETE_MODIFY, "P1.3", "/items/2", None,
    )  # fmt: skip
    assert conflict.yours is ABSENT
    assert _value(conflict.theirs)["title"] == "Runbook"
    assert conflict.resolutions == ("yours", "theirs")
    assert outcome.document is None

    deleted = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=schema)
    assert ITEM_3 not in _ids(_merged(deleted), "items")
    kept = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "theirs")], schema=schema)
    assert _by_id(_merged(kept), "items", ITEM_3)["title"] == "Runbook"
    assert (kept.resolved, kept.taken_from_current, kept.kept_from_draft) == (1, 0, 0)


def test_modify_delete_conflict_and_its_resolutions(schema):
    base = _three()[0]
    yours = copy.deepcopy(base)
    yours["items"][2]["title"] = "Operator docs"
    theirs = _without_item(base, ITEM_3)

    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert conflict.kind is ConflictKind.MODIFY_DELETE
    assert conflict.theirs is ABSENT

    kept = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=schema)
    assert _by_id(_merged(kept), "items", ITEM_3)["title"] == "Operator docs"
    deleted = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "theirs")], schema=schema)
    assert ITEM_3 not in _ids(_merged(deleted), "items")


def test_container_removed_by_one_side_keeps_children_only_through_a_conflict(schema):
    base = _two_phases()
    p2_item = base["items"][-1]["id"]
    theirs = copy.deepcopy(base)
    theirs["phases"].pop()
    theirs["items"].pop()  # current removes phase P2 with its item
    yours = copy.deepcopy(base)
    new_item = "0192f5c4-0000-7000-8000-000000000302"
    yours["items"].append(_item(new_item, "P2.2", "P2", "Dashboards"))  # the draft adds an item to P2

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    (conflict,) = outcome.conflicts
    assert (conflict.kind, conflict.entity_id, conflict.key) == (ConflictKind.MODIFY_DELETE, UUID(P2), "P2")
    assert conflict.children_kept == (UUID(new_item),)
    assert outcome.document is None

    removed = _merged(
        rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "theirs")], schema=schema)
    )
    assert [p["key"] for p in removed["phases"]] == ["P1"]
    assert set(_ids(removed, "items")).isdisjoint({p2_item, new_item})

    restored = _merged(
        rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=schema)
    )
    assert [p["key"] for p in restored["phases"]] == ["P1", "P2"]
    p2_items = [i["id"] for i in restored["items"] if i["phase"] == "P2"]
    assert p2_items == [new_item]  # P2.1 stays removed: the draft did not touch it


def test_edited_container_deleted_by_current_is_one_conflict_whose_deletion_cascades(schema):
    base = _two_phases()
    p2_item = base["items"][-1]["id"]
    theirs = copy.deepcopy(base)
    theirs["phases"].pop()
    theirs["items"].pop()  # current removes phase P2 with its item
    yours = copy.deepcopy(base)
    _phase(yours, "P2")["title"] = "Roll out in waves"  # step 5: the draft edited what current deleted
    new_item = "0192f5c4-0000-7000-8000-000000000302"
    yours["items"].append(_item(new_item, "P2.2", "P2", "Dashboards"))  # step 7: and gave it a child

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    (conflict,) = outcome.conflicts  # steps 5 and 7 name the same conflict: reported once, with the child
    assert (conflict.kind, conflict.entity_id, conflict.children_kept) == (
        ConflictKind.MODIFY_DELETE, UUID(P2), (UUID(new_item),),
    )  # fmt: skip
    assert _value(conflict.yours)["title"] == "Roll out in waves"

    removed = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "theirs")], schema=schema)
    document = _merged(removed)
    assert [p["key"] for p in document["phases"]] == ["P1"]
    assert set(_ids(document, "items")).isdisjoint({p2_item, new_item})  # the deletion cascades
    assert removed.resolved == 1

    restored = _merged(
        rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=schema)
    )
    assert _phase(restored, "P2")["title"] == "Roll out in waves"
    assert [i["id"] for i in restored["items"] if i["phase"] == "P2"] == [new_item]


def test_container_deleted_by_the_draft_and_edited_by_current_cascades_on_keep_yours():
    base = _three()[0]
    unit_1, unit_2 = "0192f5c4-0000-7000-8000-000000000501", "0192f5c4-0000-7000-8000-000000000502"
    base["units"] = [_unit(unit_1, "P1.3/U1")]
    yours = _without_item(base, ITEM_3)
    yours["units"] = []  # the draft deletes item P1.3 with its unit
    theirs = copy.deepcopy(base)
    theirs["items"][2]["title"] = "Runbook"  # step 5: current edited it
    theirs["units"].append(_unit(unit_2, "P1.3/U2"))  # step 7: and gave it a unit

    outcome = rebase_document(base, yours, theirs, [], schema=ACCEPT_ALL)
    (conflict,) = outcome.conflicts
    assert (conflict.kind, str(conflict.entity_id), conflict.children_kept) == (
        ConflictKind.DELETE_MODIFY, ITEM_3, (UUID(unit_2),),
    )  # fmt: skip

    deleted = rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "yours")], schema=ACCEPT_ALL)
    document = _merged(deleted)
    assert ITEM_3 not in _ids(document, "items")
    assert document.get("units", []) == []  # current's unit goes with its item
    assert deleted.resolved == 1

    kept = _merged(
        rebase_document(base, yours, theirs, [_keep(conflict.conflict_id, "theirs")], schema=ACCEPT_ALL)
    )
    assert _by_id(kept, "items", ITEM_3)["title"] == "Runbook"
    assert _ids(kept, "units") == [unit_2]


def test_draft_opened_before_the_first_publication_merges_against_an_empty_base(schema):
    _, yours, theirs = _agreeing()
    yours["checks"][0] = copy.deepcopy(theirs["checks"][0])
    yours["items"][0]["summary"] = theirs["items"][0]["summary"]
    yours["items"][1] = copy.deepcopy(theirs["items"][1])
    yours["items"].append(_item(DRAFT_ITEM, "P1.6", "P1", "Rotation metrics"))

    outcome = rebase_document(None, yours, theirs, [], schema=schema)
    assert [i["key"] for i in _merged(outcome)["items"]] == ["P1.1", "P1.5", "P1.3", "P1.6"]
    assert (outcome.kept_from_draft, outcome.taken_from_current) == (1, 0)

    yours["goal"] = "Rotate on every refresh."
    (conflict,) = rebase_document(None, yours, theirs, [], schema=schema).conflicts
    assert (conflict.field, conflict.base) == ("goal", ABSENT)


# ---------------------------------------------------------------------------------------------- order, keys


def test_order_takes_current_and_reinserts_what_the_draft_moved(schema):
    base, _, current = _three()
    theirs = copy.deepcopy(base)
    theirs["items"].append(_by_id(current, "items", CURRENT_ITEM))  # current only adds P1.4
    yours = copy.deepcopy(base)
    yours["items"] = [yours["items"][2], yours["items"][0], yours["items"][1]]  # the draft moves P1.3 first

    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    assert [i["key"] for i in document["items"]] == ["P1.3", "P1.1", "P1.2", "P1.4"]


def test_children_of_a_colliding_container_wait_for_its_rekey(schema):
    base = _three()[0]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    theirs["phases"].append(_new_phase(P2, "P2", "Rollout"))
    theirs["items"].append(_item("0192f5c4-0000-7000-8000-000000000301", "P2.1", "P2", "Flag rollout"))
    own_phase = "0192f5c4-0000-7000-8000-00000000000c"
    own_item = "0192f5c4-0000-7000-8000-000000000303"
    yours["phases"].append(_new_phase(own_phase, "P2", "Cleanup"))
    yours["items"].append(_item(own_item, "P2.1", "P2", "Purge job"))

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    (conflict,) = outcome.conflicts  # the item P2.1 of the draft is not reported: its phase key is open
    assert (conflict.kind, conflict.entity_id, conflict.colliding_entity_id) == (
        ConflictKind.KEY_COLLISION, UUID(own_phase), UUID(P2),
    )  # fmt: skip

    document = _merged(
        rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, "P3")], schema=schema)
    )
    assert _by_id(document, "items", own_item)["key"] == "P3.1"
    assert _phase(document, "P3")["id"] == own_phase


# ---------------------------------------------------------------------------------------------- units


def _unit(entity_id: str, key: str, **extra: Any) -> dict[str, Any]:
    return {"id": entity_id, "key": key, "title": key, **extra}


def test_local_and_full_unit_references_are_one_set_element():
    base = _three()[0]
    unit_1, unit_2 = "0192f5c4-0000-7000-8000-000000000501", "0192f5c4-0000-7000-8000-000000000502"
    base["units"] = [_unit(unit_1, "P1.1/U1"), _unit(unit_2, "P1.1/U2")]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["units"][1]["depends_on"] = ["U1"]
    theirs["units"][1]["depends_on"] = ["P1.1/U1"]

    outcome = rebase_document(base, yours, theirs, [], schema=ACCEPT_ALL)
    assert _by_id(_merged(outcome), "units", unit_2)["depends_on"] == ["P1.1/U1"]
    assert (outcome.kept_from_draft, outcome.taken_from_current) == (0, 0)


def test_unit_key_collision_takes_a_local_new_key_in_the_same_item():
    base = _three()[0]
    base["units"] = [_unit("0192f5c4-0000-7000-8000-000000000501", "P1.1/U1")]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    own = "0192f5c4-0000-7000-8000-000000000503"
    yours["units"].append(_unit(own, "P1.1/U2", depends_on=["U1"]))
    theirs["units"].append(_unit("0192f5c4-0000-7000-8000-000000000504", "P1.1/U2"))

    (conflict,) = rebase_document(base, yours, theirs, [], schema=ACCEPT_ALL).conflicts
    assert (conflict.kind, conflict.key, conflict.resolutions) == (
        ConflictKind.KEY_COLLISION,
        "P1.1/U2",
        ("rekey",),
    )

    document = _merged(
        rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, "U3")], schema=ACCEPT_ALL)
    )
    unit = _by_id(document, "units", own)
    assert (unit["key"], unit["depends_on"]) == ("P1.1/U3", ["U1"])
    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, "P1.9/U3")], schema=ACCEPT_ALL)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID  # no item P1.9 to hold the unit


def test_unit_rekeyed_into_another_item_keeps_naming_its_targets():
    base = _three()[0]
    base["units"] = [_unit("0192f5c4-0000-7000-8000-000000000501", "P1.1/U1")]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    own = "0192f5c4-0000-7000-8000-000000000503"
    yours["units"].append(_unit(own, "P1.1/U2", depends_on=["U1"]))
    theirs["units"].append(_unit("0192f5c4-0000-7000-8000-000000000504", "P1.1/U2"))
    (conflict,) = rebase_document(base, yours, theirs, [], schema=ACCEPT_ALL).conflicts

    moved = [_rekey(conflict.conflict_id, "P1.2/U3")]
    outcome = rebase_document(base, yours, theirs, moved, schema=ACCEPT_ALL)
    unit = _by_id(_merged(outcome), "units", own)
    assert (unit["key"], unit["depends_on"]) == ("P1.2/U3", ["P1.1/U1"])  # U1 alone would be P1.2/U1
    assert outcome.resolved == 1


# ---------------------------------------------------------------------------------------------- identity


def test_local_check_of_a_moved_unit_is_not_rebound_to_the_same_local_check_of_its_new_item(schema):
    base = _three()[0]
    other = copy.deepcopy(base["checks"][0])
    other.update(id="0192f5c4-0000-7000-8000-000000000029", owner="P1.2")  # P1.2:V1 besides P1.1:V1
    base["checks"].append(other)
    unit = "0192f5c4-0000-7000-8000-000000000501"
    base["units"] = [_unit(unit, "P1.1/U1", goal="Run the gate.")]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    theirs["units"][0]["checks"] = ["V1"]  # current binds P1.1:V1

    kept = _merged(rebase_document(base, yours, theirs, [], schema=schema))  # control: the unit stays
    assert _by_id(kept, "units", unit)["checks"] == ["V1"]

    yours["units"][0]["key"] = "P1.2/U1"  # the draft moves the unit: V1 there would be P1.2:V1
    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    assert outcome.document is None
    (conflict,) = outcome.conflicts
    assert conflict.kind is ConflictKind.SCHEMA
    assert any(str(i["pointer"]).startswith("/units/0/checks") for i in conflict.issues)


def test_repeated_id_keeps_every_occurrence_its_content_and_references(schema):
    base = _three()[0]
    yours = copy.deepcopy(base)
    yours["items"].append(dict(yours["items"][2], key="P1.4", title="Keep this authored edit"))
    yours["items"][0]["depends_on"] = ["P1.4"]  # names the second occurrence, not P1.3
    theirs = copy.deepcopy(base)
    theirs["items"][2]["summary"] = "Runbook for operators."  # current edits the first occurrence
    snapshot = copy.deepcopy((base, yours, theirs))

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    document = _merged(outcome)
    assert [(i["id"], i["key"]) for i in document["items"]] == [
        (ITEM_1, "P1.1"), (ITEM_2, "P1.2"), (ITEM_3, "P1.3"), (ITEM_3, "P1.4"),
    ]  # fmt: skip  # the repeated id stays for semantic validation (duplicate_id)
    first, second = document["items"][2], document["items"][3]
    assert (first["title"], first["summary"]) == (base["items"][2]["title"], "Runbook for operators.")
    assert (second["title"], second["summary"]) == ("Keep this authored edit", base["items"][2]["summary"])
    assert document["items"][0]["depends_on"] == ["P1.4"]
    assert (base, yours, theirs) == snapshot

    unchanged = _merged(rebase_document(base, yours, base, [], schema=schema))
    assert [i["title"] for i in unchanged["items"]][-1] == "Keep this authored edit"
    assert len(unchanged["items"]) == len(yours["items"]) == 4


def _formula(kind: ConflictKind, entity_id: str, field: str) -> str:
    text = json.dumps([kind.value, entity_id, field], separators=(",", ":"))
    return "rc-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def test_conflict_of_a_repeated_id_occurrence_uses_the_authored_id_and_resolves_only_it(schema):
    base, _, current = _three()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"].append(dict(yours["items"][2], key="P1.4", title="Second occurrence"))
    theirs["items"].append(_by_id(current, "items", CURRENT_ITEM))  # current's own P1.4

    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert (conflict.kind, str(conflict.entity_id), conflict.pointer, conflict.key) == (
        ConflictKind.KEY_COLLISION, ITEM_3, "/items/3/key", "P1.4",
    )  # fmt: skip
    assert conflict.conflict_id == _formula(ConflictKind.KEY_COLLISION, ITEM_3, "key")  # not "<id>~<n>"

    resolution = [_rekey(conflict.conflict_id, "P1.5")]
    document = _merged(rebase_document(base, yours, theirs, resolution, schema=schema))
    assert [(i["id"], i["key"], i["title"]) for i in document["items"] if i["id"] == ITEM_3] == [
        (ITEM_3, "P1.3", base["items"][2]["title"]), (ITEM_3, "P1.5", "Second occurrence"),
    ]  # fmt: skip


def test_a_current_that_repeats_an_id_is_refused_instead_of_matching_the_draft_repeat(schema):
    base = _three()[0]
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"].append(dict(yours["items"][2], key="P1.4", title="Draft copy"))
    theirs["items"].append(dict(theirs["items"][2], key="P1.5", title="Current copy"))  # never published (I6)
    snapshot = copy.deepcopy((base, yours, theirs))

    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [], schema=schema)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.message == "a published revision repeats an entity id (duplicate_id)"
    assert caught.value.details["issues"] == [{
        "pointer": "/theirs/items/3/id",
        "schema_pointer": "",
        "message": f"theirs repeats entity id {ITEM_3} (duplicate_id)",
    }]  # fmt: skip
    assert (base, yours, theirs) == snapshot

    with pytest.raises(ValidationFailed) as caught:  # a repeat only current holds is refused as well
        rebase_document(base, base, theirs, [], schema=schema)
    assert [i["pointer"] for i in cast(list[dict[str, str]], caught.value.details["issues"])] == [
        "/theirs/items/3/id"
    ]

    with pytest.raises(ValidationFailed) as caught:  # also when the draft opened before the first publication
        rebase_document(None, yours, theirs, [], schema=schema)
    assert [i["pointer"] for i in cast(list[dict[str, str]], caught.value.details["issues"])] == [
        "/theirs/items/3/id"
    ]

    current = copy.deepcopy(base)
    current["items"][2]["summary"] = "Runbook for operators."
    document = _merged(rebase_document(base, yours, current, [], schema=schema))  # only the draft repeats
    assert [(i["key"], i["title"]) for i in document["items"] if i["id"] == ITEM_3] == [
        ("P1.3", base["items"][2]["title"]), ("P1.4", "Draft copy"),
    ]  # fmt: skip


def test_a_conflict_id_naming_two_occurrences_is_open_but_cannot_be_resolved(schema):
    base, _, current = _three()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"][2]["key"] = "P1.4"
    yours["items"].append(dict(yours["items"][2], key="P1.5", title="Second occurrence"))
    theirs["items"].append(_by_id(current, "items", CURRENT_ITEM))  # P1.4
    theirs["items"].append(_item("0192f5c4-0000-7000-8000-000000000202", "P1.5", "P1", "Current P1.5"))

    conflicts = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert [(c.kind, str(c.entity_id), c.pointer) for c in conflicts] == [
        (ConflictKind.KEY_COLLISION, ITEM_3, "/items/2/key"),
        (ConflictKind.KEY_COLLISION, ITEM_3, "/items/3/key"),
    ]
    assert conflicts[0].conflict_id == conflicts[1].conflict_id  # the formula holds the authored id only

    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [_rekey(conflicts[0].conflict_id, "P1.6")], schema=schema)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert (
        "more than one conflict" in cast(list[dict[str, str]], caught.value.details["issues"])[0]["message"]
    )


def test_a_base_that_repeats_an_id_is_refused_instead_of_duplicating_or_guessing(schema):
    published = _three()[0]
    base = copy.deepcopy(published)
    base["items"].append(dict(base["items"][2], key="P1.4", title="Repeat"))  # never published (I6)
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)  # both keep it: it would come back twice
    snapshot = copy.deepcopy((base, yours, theirs))

    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [], schema=schema)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    issues = cast(list[dict[str, str]], caught.value.details["issues"])
    assert [i["pointer"] for i in issues] == ["/base/items/3/id", "/theirs/items/3/id"]
    assert all(ITEM_3 in i["message"] and "duplicate_id" in i["message"] for i in issues)
    assert (base, yours, theirs) == snapshot

    theirs = copy.deepcopy(published)  # current dropped the repeat: base still cannot be read
    with pytest.raises(ValidationFailed) as caught:
        rebase_document(base, yours, theirs, [], schema=schema)
    assert [i["pointer"] for i in cast(list[dict[str, str]], caught.value.details["issues"])] == [
        "/base/items/3/id"
    ]

    assert _merged(rebase_document(published, yours, theirs, [], schema=schema))  # only the base decides


def test_item_key_with_a_prefix_mismatch_is_kept_as_written(schema):
    base = _two_phases()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"][2]["phase"] = "P2"  # the draft moves P1.3 to P2 but keeps its key: key_prefix_mismatch
    theirs["items"][2]["summary"] = "Runbook for operators."

    document = _merged(rebase_document(base, yours, theirs, [], schema=schema))
    item = _by_id(document, "items", ITEM_3)
    assert (item["key"], item["phase"], item["summary"]) == ("P1.3", "P2", "Runbook for operators.")

    unchanged = _merged(rebase_document(base, yours, base, [], schema=schema))
    assert _by_id(unchanged, "items", ITEM_3)["key"] == "P1.3"  # not repaired to P2.3


def test_rekey_of_an_item_with_a_prefix_mismatch_lands_in_the_container_of_its_new_key(schema):
    base = _two_phases()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"][2].update(key="P1.4", phase="P2")  # as written; its phase is P2
    theirs["items"].append(_item(CURRENT_ITEM, "P1.4", "P1", "Current item"))
    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert (conflict.kind, str(conflict.entity_id)) == (ConflictKind.KEY_COLLISION, ITEM_3)

    for new_key, phase in (("P1.6", "P1"), ("P2.6", "P2")):
        outcome = rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, new_key)], schema=schema)
        item = _by_id(_merged(outcome), "items", ITEM_3)
        assert (item["key"], item["phase"]) == (new_key, phase)


def _crossing_moves() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Items P1.1 and P2.2: the draft moves both to P3, current renumbers both to 3 — both land on P3.3."""
    base = _two_phases()
    base["items"] = [base["items"][0], base["items"][-1]]
    base["items"][1]["key"] = "P2.2"
    base.pop("checks")
    base.pop("criteria")
    base["phases"].append(_new_phase("0192f5c4-0000-7000-8000-00000000000c", "P3", "Third phase"))
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"][0].update(key="P3.1", phase="P3")
    yours["items"][1].update(key="P3.2", phase="P3")
    theirs["items"][0]["key"] = "P1.3"
    theirs["items"][1]["key"] = "P2.3"
    return base, yours, theirs


def test_rekey_of_one_colliding_entity_settles_the_other(schema):
    base, yours, theirs = _crossing_moves()
    first, second = base["items"][0]["id"], base["items"][1]["id"]

    conflicts = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert [(c.kind, str(c.entity_id), str(c.colliding_entity_id)) for c in conflicts] == [
        (ConflictKind.KEY_COLLISION, first, second), (ConflictKind.KEY_COLLISION, second, first),
    ]  # fmt: skip
    for conflict in conflicts:  # whichever is rekeyed, the other keeps P3.3
        outcome = rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, "P3.4")], schema=schema)
        keys = {i["id"]: i["key"] for i in _merged(outcome)["items"]}
        rekeyed = str(conflict.entity_id)
        assert keys[rekeyed] == "P3.4"
        assert keys[second if rekeyed == first else first] == "P3.3"
        assert outcome.resolved == 1

    both = [_rekey(conflicts[0].conflict_id, "P3.4"), _rekey(conflicts[1].conflict_id, "P3.5")]
    document = _merged(rebase_document(base, yours, theirs, both, schema=schema))
    assert [i["key"] for i in document["items"] if i["id"] in (first, second)] == ["P3.4", "P3.5"]


def test_collision_resolves_to_a_free_key_of_the_same_kind_in_another_container(schema):
    base = _two_phases()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["items"].append(_item(DRAFT_ITEM, "P1.4", "P1", "Draft item"))
    theirs["items"].append(_item(CURRENT_ITEM, "P1.4", "P1", "Current item"))
    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts

    outcome = rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, "P2.2")], schema=schema)
    document = _merged(outcome)
    draft = _by_id(document, "items", DRAFT_ITEM)
    assert (draft["key"], draft["phase"], draft["title"]) == ("P2.2", "P2", "Draft item")
    assert [i["key"] for i in document["items"] if i["phase"] == "P2"] == ["P2.1", "P2.2"]
    assert outcome.resolved == 1
    for new_key in ("P2", "P2.1", "P3.1"):  # another kind, a taken key, no such phase
        with pytest.raises(ValidationFailed) as caught:
            rebase_document(base, yours, theirs, [_rekey(conflict.conflict_id, new_key)], schema=schema)
        assert caught.value.code is ErrorCode.SCHEMA_INVALID


def _four_units() -> dict[str, Any]:
    base = _three()[0]
    base["units"] = [
        _unit(f"0192f5c4-0000-7000-8000-00000000050{i}", f"P1.1/U{i}", goal="Work.") for i in (1, 2, 3, 4)
    ]
    base["units"][2]["parent"] = "U1"
    return base


def test_scalar_unit_reference_respelled_local_or_full_is_the_same_target(schema):
    base = _four_units()
    yours, theirs = copy.deepcopy(base), copy.deepcopy(base)
    yours["units"][2]["parent"] = "P1.1/U1"  # the same parent, written in full
    theirs["units"][2]["parent"] = "U2"  # current changes the parent

    outcome = rebase_document(base, yours, theirs, [], schema=schema)
    assert _merged(outcome)["units"][2]["parent"] == "U2"
    assert (outcome.kept_from_draft, outcome.taken_from_current) == (0, 1)

    removed = copy.deepcopy(base)
    del removed["units"][2]  # current removes the unit the draft only respelled: no modify_delete
    assert len(_merged(rebase_document(base, yours, removed, [], schema=schema))["units"]) == 3

    yours["units"][2]["parent"] = "P1.1/U4"  # control: a different target is still a conflict
    (conflict,) = rebase_document(base, yours, theirs, [], schema=schema).conflicts
    assert (conflict.kind, conflict.field, conflict.base, conflict.yours, conflict.theirs) == (
        ConflictKind.FIELD, "parent", "U1", "P1.1/U4", "U2",
    )  # fmt: skip
