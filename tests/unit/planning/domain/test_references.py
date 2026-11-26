"""Display keys, typed references and rekey (planning §4.3, §5.3 items 4 and 6)."""

import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.modules.planning.domain.changes import (
    AddChange,
    ItemDefaults,
    RekeyChange,
    RemoveChange,
    apply_changes,
    rekey,
)
from skm.modules.planning.domain.display_keys import (
    DisplayKey,
    IdRef,
    KeyKind,
    LocalRef,
    QualifiedRef,
    key_sort_key,
    parse_check_ref,
    parse_cli_ref,
    parse_key,
    parse_unit_ref,
)
from skm.modules.planning.domain.item import Effort, ModelClass
from skm.modules.planning.domain.references import REFERENCE_FIELDS, RefKind, find_entity, resolve_ref
from skm.modules.planning.domain.review_requirement import ReviewMode
from skm.modules.planning.domain.specification import EntityKind

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/auth-refresh.specification.json"
DEFAULTS = ItemDefaults(ModelClass.IMPLEMENTATION, Effort.MEDIUM, ReviewMode.REQUIRED)


def _doc() -> dict[str, Any]:
    return json.loads(EXAMPLE.read_text())


def _entity(doc: dict[str, Any], array: str, key: str, owner: str | None = None) -> dict[str, Any]:
    return next(e for e in doc[array] if e["key"] == key and (owner is None or e["owner"] == owner))


def _string_values(node):
    """Every string of the document except ``decision.origin``: its ``ref`` is free text, not a reference."""
    if isinstance(node, dict) and "origin" in node and "state" in node:
        node = {name: value for name, value in node.items() if name != "origin"}
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for child in node:
            yield from _string_values(child)
    elif isinstance(node, dict):
        for child in node.values():
            yield from _string_values(child)


# ------------------------------------------------------------------------------------------ display keys


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("P1", KeyKind.PHASE),
        ("P2.4", KeyKind.ITEM),
        ("P2.4/U1", KeyKind.UNIT),
        ("D3", KeyKind.DECISION),
        ("R7", KeyKind.REQUIREMENT),
        ("AC1", KeyKind.CRITERION),
        ("P2.4:V1", KeyKind.CHECK),
        ("P2:V1", KeyKind.CHECK),
        ("material/storage-design", KeyKind.MATERIAL),
        ("PLAN7", KeyKind.PLAN),
    ],
)
def test_parse_key_classifies_every_display_key(text, kind):
    assert parse_key(text) == DisplayKey(kind, text)


@pytest.mark.parametrize(
    "text", ["", "p1", "P", "P1.", "P1.2/U", "V1", "AC", "PLAN0", "P1.2:V", "material/", "x y"]
)
def test_parse_key_rejects_what_is_not_a_key(text):
    with pytest.raises(ValidationFailed) as raised:
        parse_key(text)
    assert raised.value.code is ErrorCode.INVALID_REFERENCE
    assert raised.value.details["text"] == text


def test_ac_is_a_criterion_in_entity_position_and_never_a_plan_alias():
    assert parse_key("AC1").kind is KeyKind.CRITERION
    assert parse_key("ACD1").kind is KeyKind.PLAN  # only the exact AC<digits> shape is reserved


def test_display_key_parts():
    assert (parse_key("P2.4/U1").phase_key, parse_key("P2.4/U1").item_key, parse_key("P2.4/U1").local) == (
        "P2",
        "P2.4",
        "U1",
    )
    assert (parse_key("P2.4:V1").item_key, parse_key("P2:V1").item_key) == ("P2.4", None)
    assert parse_key("P2.4:V1").local == "V1"
    assert parse_key("P2").local is None


def test_local_forms_are_completed_by_their_owner():
    assert parse_unit_ref("U2", owner_item="P1.2") == "P1.2/U2"
    assert parse_unit_ref("P3.1/U2", owner_item="P1.2") == "P3.1/U2"
    assert parse_check_ref("V1", default_owner="P1.2") == "P1.2:V1"
    assert parse_check_ref("P1:V1", default_owner="P1.2") == "P1:V1"
    with pytest.raises(ValidationFailed):
        parse_unit_ref("P1", owner_item="P1.2")


def test_cli_references():
    uid = "0192f5c4-0000-7000-8000-000000000014"
    assert parse_cli_ref("PLAN7.P2.4/U1") == QualifiedRef("PLAN7", parse_key("P2.4/U1"))
    assert parse_cli_ref("AC1") == LocalRef(parse_key("AC1"))
    assert parse_cli_ref(f"entity:{uid}") == IdRef("entity", UUID(uid))
    assert parse_cli_ref(f"revision:{uid}") == IdRef("revision", UUID(uid))
    with pytest.raises(ValidationFailed):
        parse_cli_ref("entity:not-a-uuid")


def test_keys_sort_naturally_and_a_phase_precedes_its_items():
    keys = ["P1.10", "P1.9", "P1", "P2", "P1.9/U10", "P1.9/U2"]
    assert sorted(keys, key=key_sort_key) == ["P1", "P1.9", "P1.9/U2", "P1.9/U10", "P1.10", "P2"]


# --------------------------------------------------------------------------------------------- resolving


def test_entities_resolve_by_display_key_or_by_id_to_the_same_location():
    doc = _doc()
    by_key = resolve_ref(doc, "P2.3")
    by_id = resolve_ref(doc, f"entity:{_entity(doc, 'items', 'P2.3')['id']}")
    assert by_key == by_id
    assert by_key.pointer == "/items/4"
    assert (
        resolve_ref(doc, "P2.1:V1").key == "P2.1:V1"
    )  # the same local key under another owner is another check
    assert find_entity(doc, "P9.9") is None


def test_unknown_reference_is_not_found_with_the_batch_position():
    with pytest.raises(NotFound) as raised:
        resolve_ref(_doc(), "P9.9", change_index=3)
    assert dict(raised.value.details) == {"kind": "entity", "ref": "P9.9", "change_index": 3}


# ------------------------------------------------------------------------------------------------ rekey


def test_item_rekey_keeps_the_id_and_rewrites_every_reference():
    doc = _doc()
    entity_id = _entity(doc, "items", "P2.3")["id"]
    out: dict[str, Any] = rekey(doc, "P2.3", "P2.5").document
    renamed = _entity(out, "items", "P2.5")
    assert renamed["id"] == entity_id
    assert renamed["phase"] == "P2"
    assert "P2.3" not in set(_string_values(out))
    assert "P2.3:V1" not in set(_string_values(out))
    assert _entity(out, "checks", "V1", "P2.5")["id"] == _entity(doc, "checks", "V1", "P2.3")["id"]
    assert next(c for c in out["criteria"] if c["key"] == "AC4")["owner"] == "P2.5"
    assert next(c for c in out["criteria"] if c["key"] == "AC4")["checks"] == ["P2.5:V1"]
    assert "P2.5" in next(b for b in out["phases"][1]["batches"] if b["key"] == "B2")["items"]
    assert doc == _doc()  # the input is untouched


def test_every_declared_reference_field_is_rewritten_by_rekey_of_each_target():
    doc = _doc()
    targets = [
        e["key"]
        for a in ("phases", "items", "units", "requirements", "criteria", "decisions")
        for e in doc[a]
    ]
    for target in targets:
        fresh = {"P": "P9", "D": "D9", "R": "R9", "A": "AC9"}[target[:1] if target[:2] != "AC" else "A"]
        if target.startswith("P") and "." in target:
            fresh = (
                "P" + target[1:].replace(target[1], "9", 1)
                if "/" not in target
                else target.replace("U", "U9", 1)
            )
        out = rekey(doc, target, fresh).document
        assert target not in set(_string_values(out)), target


def test_phase_rekey_moves_its_items_units_and_checks_with_it():
    doc = _doc()
    out: dict[str, Any] = rekey(doc, "P2", "P7").document
    assert [i["key"] for i in out["items"] if i["phase"] == "P7"] == ["P7.1", "P7.2", "P7.3"]
    assert {u["key"] for u in out["units"] if u["key"].startswith("P7.1/")} == {"P7.1/U1", "P7.1/U2"}
    assert any(c["owner"] == "P7.1" and c["key"] == "V1" for c in out["checks"])
    assert not any(v == "P2" or v.startswith(("P2.", "P2:")) for v in _string_values(out))


def test_unit_rekey_rewrites_local_and_full_dependencies():
    doc = _doc()
    out = rekey(doc, "P1.1/U1", "P1.1/U5").document
    assert _entity(out, "units", "P1.1/U2")["depends_on"] == ["U5"]  # a local reference stays local
    assert _entity(out, "units", "P1.1/U5")["id"] == _entity(doc, "units", "P1.1/U1")["id"]


def test_requirement_decision_criterion_and_material_rekey_rewrite_their_own_fields():
    doc = _doc()
    out = rekey(doc, "R1", "R10").document
    assert _entity(out, "items", "P1.1")["implements"] == ["R10"]
    assert _entity(out, "criteria", "AC1")["requirements"] == ["R10"]
    out = rekey(doc, "D1", "D11").document
    assert "D11" in _entity(out, "items", "P1.2")["decisions"]
    out = rekey(doc, "material/storage-design", "material/storage-v2").document
    ref = _entity(out, "items", "P1.1")["reads"][0]["ref"]
    assert ref == "material/storage-v2#schema"  # the section id is kept
    assert _entity(out, "materials", "storage-v2")["id"] == _entity(doc, "materials", "storage-design")["id"]
    assert rekey(doc, "material/storage-design", "storage-v2").document == out  # bare key form


def test_check_rekey_rewrites_qualified_and_unit_local_references():
    doc = _doc()
    out = rekey(doc, "P1.1:V1", "P1.1:V7").document
    assert _entity(out, "checks", "V7", "P1.1")["id"] == _entity(doc, "checks", "V1", "P1.1")["id"]
    assert _entity(out, "units", "P1.1/U2")["checks"] == ["V7"]


def test_check_moved_to_another_owner_drops_unit_local_references_with_a_note():
    doc = _doc()
    outcome = rekey(doc, "P1.1:V1", "P1.2:V4")
    assert _entity(outcome.document, "units", "P1.1/U2")["checks"] == []
    assert _entity(outcome.document, "checks", "V4", "P1.2")["owner"] == "P1.2"
    assert len(outcome.notes) == 1
    assert "P1.1" in outcome.notes[0]


def test_rekey_to_a_taken_key_is_a_conflict_and_a_wrong_kind_is_invalid():
    with pytest.raises(Conflict) as taken:
        rekey(_doc(), "P2.3", "P2.2")
    assert taken.value.code is ErrorCode.ALREADY_EXISTS
    assert taken.value.details["key"] == "P2.2"
    with pytest.raises(Conflict):
        rekey(_doc(), "P1", "P2")
    with pytest.raises(ValidationFailed) as kind:
        rekey(_doc(), "P2.3", "P3")
    assert kind.value.code is ErrorCode.INVALID_REFERENCE
    assert kind.value.details["reason"] == "kind_mismatch"
    with pytest.raises(Conflict):  # P1 -> P2 items would land on existing keys
        rekey(_doc(), "P1", "P2")


def test_rekey_is_addressable_by_id_before_and_after():
    doc = _doc()
    uid = f"entity:{_entity(doc, 'items', 'P2.3')['id']}"
    out = apply_changes(doc, [RekeyChange(uid, "P2.5"), RekeyChange(uid, "P2.6")], defaults=DEFAULTS).document
    found = find_entity(out, uid)
    assert found is not None
    assert found.key == "P2.6"
    assert "P2.5" not in set(_string_values(out))


def test_documents_declare_the_reference_field_table_completely():
    assert {f.array for f in REFERENCE_FIELDS} == {
        "phases",
        "items",
        "units",
        "checks",
        "criteria",
        "requirements",
        "decisions",
        "materials",
    }
    assert {f.ref for f in REFERENCE_FIELDS} == set(RefKind)


# ------------------------------------------------------------------------------- split / merge are explicit


def test_split_keeps_unrewritten_references_dangling_and_never_maps_by_title_or_path():
    doc = _doc()
    old = _entity(doc, "items", "P2.2")
    twin = {**copy.deepcopy(old), "key": "P2.6", "title": old["title"]}
    twin.pop("id")
    out: dict[str, Any] = apply_changes(
        doc,
        [RemoveChange("P2.2", False), AddChange(EntityKind.ITEM, twin, "P2.1")],
        defaults=DEFAULTS,
    ).document
    assert find_entity(out, "P2.2") is None
    assert find_entity(out, "P2.6") is not None
    # the incoming dependency, the owned criterion and the check still name P2.2: ref_unknown at validation
    assert "P2.2" in _entity(out, "items", "P2.3")["depends_on"]
    assert any(c["owner"] == "P2.2" for c in out["criteria"])
    assert any(c["owner"] == "P2.2" for c in out["checks"])
    assert "id" not in _entity(
        out, "items", "P2.6"
    )  # a new identity: the author chose it, nothing was mapped


def test_split_with_explicit_rewrites_in_one_batch_is_complete():
    from skm.modules.planning.domain.changes import PatchChange

    doc = _doc()
    out = apply_changes(
        doc,
        [
            AddChange(
                EntityKind.ITEM,
                {
                    "key": "P2.6",
                    "phase": "P2",
                    "title": "Split half",
                    "summary": "s",
                    "why": "w",
                    "review": {"mode": "self", "reason": "r"},
                },
                "P2.2",
            ),
            PatchChange("P2.3", {"depends_on": ["P2.1", "P2.6"]}),
            PatchChange("AC3", {"owner": "P2.6"}),
        ],
        defaults=DEFAULTS,
    ).document
    assert _entity(out, "items", "P2.3")["depends_on"] == ["P2.1", "P2.6"]
    assert _entity(out, "criteria", "AC3")["owner"] == "P2.6"
    assert (
        _entity(out, "items", "P2.2")["id"] == _entity(doc, "items", "P2.2")["id"]
    )  # the kept item keeps its id


def test_expected_output_write_scope_and_repository_inputs_stay_separate_declarations():
    doc = _doc()
    unit = _entity(doc, "units", "P2.1/U1")
    assert unit["write_scope"] != unit["outputs"]
    assert "reads" not in unit
    out = rekey(doc, "P2.1", "P2.8").document
    moved = _entity(out, "units", "P2.8/U1")
    assert moved["write_scope"] == unit["write_scope"]
    assert moved["outputs"] == unit["outputs"]
