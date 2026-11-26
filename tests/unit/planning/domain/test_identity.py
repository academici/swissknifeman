"""Stable entity identities: assignment order, no guessing, no kind changes (planning §5.2)."""

import copy
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from skm.kernel.ids import EntityId
from skm.modules.planning.domain.identity import (
    assign_missing_ids,
    identity_findings,
    missing_existing_ids,
)
from skm.modules.planning.domain.specification import EntityKind

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/auth-refresh.specification.json"


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def new_id(self) -> UUID:
        self.n += 1
        return UUID(f"0192f5c9-0000-7000-8000-{self.n:012d}")


def _stripped() -> dict[str, Any]:
    doc = json.loads(EXAMPLE.read_text())
    for field in ("phases", "items", "units", "requirements", "criteria", "checks", "decisions", "materials"):
        for entity in doc[field]:
            entity.pop("id")
    return doc


def test_ids_are_assigned_in_the_normative_traversal_order():
    doc = _stripped()
    result: dict[str, Any]
    result, assigned = assign_missing_ids(doc, _Ids())
    order = []
    for entry in assigned:
        if entry.entity_kind not in order:
            order.append(entry.entity_kind)
    assert order == [
        EntityKind.PHASE,
        EntityKind.ITEM,
        EntityKind.UNIT,
        EntityKind.REQUIREMENT,
        EntityKind.CRITERION,
        EntityKind.CHECK,
        EntityKind.DECISION,
        EntityKind.MATERIAL,
    ]
    numbers = [int(str(entry.entity_id).rsplit("-", 1)[1]) for entry in assigned]
    assert numbers == list(range(1, len(assigned) + 1))
    first = assigned[0]
    assert (first.pointer, first.key) == ("/phases/0/id", "P1")
    assert result["phases"][0]["id"] == str(first.entity_id)
    check = next(a for a in assigned if a.entity_kind is EntityKind.CHECK)
    assert check.key == "P1.1:V1"  # a check is identified by owner:key, never by the bare local key


def test_assignment_does_not_mutate_the_input_and_keeps_existing_ids():
    doc = _stripped()
    doc["phases"][1]["id"] = "0192f5c4-0000-7000-8000-00000000000b"
    before = copy.deepcopy(doc)
    result: dict[str, Any]
    result, assigned = assign_missing_ids(doc, _Ids())
    assert doc == before
    assert result["phases"][1]["id"] == "0192f5c4-0000-7000-8000-00000000000b"
    assert all(a.pointer != "/phases/1/id" for a in assigned)
    again, none_left = assign_missing_ids(result, _Ids())
    assert none_left == ()
    assert again == result


def test_missing_id_of_an_existing_entity_is_reported_not_guessed():
    previous = json.loads(EXAMPLE.read_text())
    sent = copy.deepcopy(previous)
    del sent["items"][1]["id"]
    sent["items"].append({"key": "P2.9", "phase": "P2", "title": "t", "summary": "s", "why": "w"})
    assert missing_existing_ids(previous, sent) == ("/items/1/id",)  # P2.9 is new: no id is required of it


def test_check_with_same_local_key_under_another_owner_is_not_the_same_entity():
    previous = json.loads(EXAMPLE.read_text())
    sent = copy.deepcopy(previous)
    sent["checks"][0].pop("id")
    sent["checks"][0]["owner"] = "P2.1"  # P2.1:V1 exists already, so the lookup is by owner:key
    assert missing_existing_ids(previous, sent) == ("/checks/0/id",)
    sent["checks"][0]["key"] = "V9"
    assert missing_existing_ids(previous, sent) == ()


def test_import_ids_cannot_change_the_entity_kind():
    doc = json.loads(EXAMPLE.read_text())
    known = {EntityId(UUID(e["id"])): EntityKind.ITEM for e in doc["items"]}
    assert identity_findings(doc, known) == ()
    swapped = copy.deepcopy(doc)
    swapped["units"][0]["id"] = doc["items"][0]["id"]
    codes = sorted(f.code for f in identity_findings(swapped, known))
    assert codes == ["duplicate_id", "entity_kind_changed"]
    reassigned: dict[str, Any] = assign_missing_ids(swapped, _Ids())[0]
    assert reassigned["units"][0]["id"] == doc["items"][0]["id"]


def test_two_objects_with_one_id_are_a_duplicate_id_finding():
    doc = json.loads(EXAMPLE.read_text())
    doc["requirements"][1]["id"] = doc["requirements"][0]["id"]
    (finding,) = identity_findings(doc)
    assert (finding.code, finding.entity_key, finding.pointer) == ("duplicate_id", "R2", "/requirements/1/id")
