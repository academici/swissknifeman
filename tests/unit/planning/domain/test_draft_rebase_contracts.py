"""Contract regressions: the ``Draft`` aggregate shape and the rebase conflict schema's ``entity_kind``."""

import json
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.protocols import Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from skm.kernel.ids import PlanId, PrincipalId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.planning.domain.draft import Draft, DraftId, DraftState


def test_draft_is_a_frozen_slotted_aggregate() -> None:
    assert tuple(field.name for field in fields(Draft)) == (
        "id",
        "plan_id",
        "workspace_id",
        "base_revision_id",
        "edit_version",
        "document",
        "state",
        "published_revision_id",
        "created_by",
        "created_at",
        "updated_by",
        "updated_at",
        "closed_at",
    )
    uid = UUID("01900000-0000-7000-8000-000000000001")
    now = datetime(2026, 10, 26, tzinfo=UTC)
    draft = Draft(
        id=DraftId(uid),
        plan_id=PlanId(uid),
        workspace_id=WorkspaceId(uid),
        base_revision_id=None,
        edit_version=1,
        document={},
        state=DraftState.OPEN,
        published_revision_id=None,
        created_by=PrincipalId(uid),
        created_at=now,
        updated_by=PrincipalId(uid),
        updated_at=now,
        closed_at=None,
    )
    updated = replace(draft, edit_version=2)
    assert updated.edit_version == 2
    assert draft.edit_version == 1
    assert updated.id == draft.id
    with pytest.raises(FrozenInstanceError):
        setattr(draft, "edit_version", 3)  # noqa: B010 -- exercise the generated frozen setter at runtime.
    assert not hasattr(draft, "__dict__")


def conflict_validator() -> Validator:
    schemas = Path(__file__).resolve().parents[4] / "src/skm/schemas"
    resources: list[tuple[str, Resource[Schema]]] = []
    for relative in ("kernel/defs.v1.json", "planning/defs.v1.json", "planning/specification.v1.json"):
        document: JsonObject = json.loads((schemas / relative).read_text())
        resources.append((str(document["$id"]), Resource[Schema].from_contents(document)))
    return Draft202012Validator(
        {"$ref": "urn:skm:planning:defs:v1#/$defs/rebase-conflict"},
        registry=Registry[Schema]().with_resources(resources),
    )


def conflict(entity_kind: JsonValue) -> JsonObject:
    return {
        "conflict_id": "rc-0123456789ab",
        "kind": "field",
        "entity_id": None,
        "entity_kind": entity_kind,
        "key": "P1.2",
        "field": "title",
        "pointer": "/items/0/title",
        "base": "before",
        "yours": "mine",
        "theirs": "current",
        "resolutions": ["yours", "theirs"],
        "colliding_entity_id": None,
        "children_kept": [],
        "issues": [],
    }


@pytest.mark.parametrize(
    "entity_kind",
    ["phase", "item", "unit", "requirement", "criterion", "check", "decision", "material", None],
)
def test_rebase_conflict_accepts_entity_kind_or_null(entity_kind: JsonValue) -> None:
    conflict_validator().validate(conflict(entity_kind))


@pytest.mark.parametrize("entity_kind", ["P1", "P1.2", "unknown", "", 1, {}])
def test_rebase_conflict_rejects_display_keys_and_invalid_kinds(entity_kind: JsonValue) -> None:
    with pytest.raises(ValidationError):
        conflict_validator().validate(conflict(entity_kind))
