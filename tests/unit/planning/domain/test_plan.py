"""Plan aggregate transitions and the planning event payloads (planning §4.4, §9)."""

import json
from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import Schema

from skm.application_bus.registry import BusRegistry
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.events import STREAM_KINDS, DomainEvent
from skm.kernel.ids import PlanId, PrincipalId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.planning.domain import events
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.plan import (
    Plan,
    PlanLifecycle,
    PlanPurpose,
    archive,
    new_plan,
    record_publication,
    require_active,
    require_editable,
)
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.module import MODULE
from skm.modules.workspace.public import ProjectView
from skm.platform.schema.registry import SchemaRegistry

SCHEMAS = Path(__file__).resolve().parents[4] / "src/skm/schemas"
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def uid(n: int) -> UUID:
    return UUID(f"01900000-0000-7000-8000-{n:012d}")


@dataclass(frozen=True)
class Project:
    workspace_id: WorkspaceId
    project_id: ProjectId


PROJECT = Project(WorkspaceId(uid(1)), ProjectId(uid(2)))
ACTOR = PrincipalId(uid(3))


def make_plan(**changes: object) -> Plan:
    plan = new_plan(PlanId(uid(10)), PROJECT, "PLAN1", "  Auth refresh  ", ACTOR, NOW)
    return replace(plan, **changes)


def test_new_plan_starts_without_a_revision() -> None:
    plan = make_plan()
    assert plan.title == "Auth refresh"  # stripped
    assert (plan.workspace_id, plan.project_id) == (PROJECT.workspace_id, PROJECT.project_id)
    assert plan.lifecycle is PlanLifecycle.ACTIVE
    assert plan.purpose is PlanPurpose.STANDARD
    assert plan.current_revision_id is None
    assert (plan.next_revision_no, plan.row_version) == (1, 1)
    assert plan.created_by == ACTOR
    assert (plan.created_at, plan.updated_at, plan.archived_at) == (NOW, NOW, None)


@pytest.mark.parametrize("title", ["", "   ", "x" * 301])
def test_new_plan_refuses_a_title_outside_1_to_300_characters(title: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        new_plan(PlanId(uid(10)), PROJECT, "PLAN1", title, ACTOR, NOW)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["field"] == "title"


def test_title_of_300_characters_after_strip_is_accepted() -> None:
    assert len(new_plan(PlanId(uid(10)), PROJECT, "PLAN1", " " + "x" * 300 + " ", ACTOR, NOW).title) == 300


def test_new_plan_accepts_the_workspace_project_view() -> None:
    view = ProjectView(
        project_id=uid(2),
        workspace_id=uid(1),
        slug="app",
        title="App",
        description="",
        state="active",
        row_version=1,
        mounts=(),
    )
    plan = new_plan(PlanId(uid(10)), view, "PLAN1", "Auth", ACTOR, NOW)  # type-checked: a ``ProjectView``
    assert (plan.workspace_id, plan.project_id) == (uid(1), uid(2))


def test_plan_is_a_frozen_slotted_aggregate() -> None:
    plan = make_plan()
    with pytest.raises(FrozenInstanceError):
        setattr(plan, "title", "other")  # noqa: B010 -- exercise the frozen setter at runtime.
    assert not hasattr(plan, "__dict__")


def test_require_active_refuses_an_archived_plan() -> None:
    require_active(make_plan())
    with pytest.raises(PreconditionFailed) as caught:
        require_active(archive(make_plan(), NOW))
    assert caught.value.code is ErrorCode.PLAN_ARCHIVED


def test_require_editable_refuses_the_system_plan_with_a_reason() -> None:
    require_editable(make_plan())
    system = make_plan(purpose=PlanPurpose.REVIEW_REQUESTS, alias="review-requests")
    with pytest.raises(PreconditionFailed) as caught:
        require_editable(system)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert caught.value.details["reason"] == "system_plan"


def test_require_editable_reports_an_archived_system_plan_as_archived() -> None:
    system = archive(make_plan(purpose=PlanPurpose.REVIEW_REQUESTS), NOW)
    with pytest.raises(PreconditionFailed) as caught:
        require_editable(system)
    assert caught.value.code is ErrorCode.PLAN_ARCHIVED


def test_archive_changes_the_plan_once_and_returns_the_same_object_afterwards() -> None:
    plan = make_plan()
    archived = archive(plan, LATER)
    assert archived is not plan
    assert archived.lifecycle is PlanLifecycle.ARCHIVED
    assert (archived.archived_at, archived.updated_at) == (LATER, LATER)
    assert archived.row_version == plan.row_version + 1
    assert plan.lifecycle is PlanLifecycle.ACTIVE  # the input is not mutated
    assert archive(archived, LATER + timedelta(days=1)) is archived  # no second archive, no event


def test_record_publication_moves_the_counters_and_the_title() -> None:
    plan = make_plan()
    revision_id = RevisionId(uid(20))
    published = record_publication(plan, revision_id, "Auth refresh v2", LATER)
    assert published.current_revision_id == revision_id
    assert published.title == "Auth refresh v2"
    assert published.next_revision_no == plan.next_revision_no + 1
    assert published.row_version == plan.row_version + 1
    assert published.updated_at == LATER
    second = record_publication(published, RevisionId(uid(21)), "Auth refresh v2", LATER)
    assert second.next_revision_no == 3


def test_record_publication_keeps_the_exact_revision_title() -> None:
    # the specification title is stored as authored; the plan shows what its current revision stores
    published = record_publication(make_plan(), RevisionId(uid(20)), "  Auth refresh v2 ", LATER)
    assert published.title == "  Auth refresh v2 "


def test_record_publication_refuses_an_archived_plan() -> None:
    with pytest.raises(PreconditionFailed) as caught:
        record_publication(archive(make_plan(), NOW), RevisionId(uid(20)), "t", LATER)
    assert caught.value.code is ErrorCode.PLAN_ARCHIVED


def test_the_system_plan_may_record_a_publication() -> None:
    # the review-request facade publishes into the system plan; only drafts, archive and restore are barred
    system = make_plan(purpose=PlanPurpose.REVIEW_REQUESTS)
    assert record_publication(system, RevisionId(uid(20)), "Review requests", LATER).next_revision_no == 2


# --- events ------------------------------------------------------------------------------------------------


def _validator(event: DomainEvent) -> Draft202012Validator:
    resources: list[tuple[str, Resource[Schema]]] = []
    for path in (SCHEMAS / "kernel").glob("*.json"):
        document: JsonObject = json.loads(path.read_text())
        resources.append((str(document["$id"]), Resource[Schema].from_contents(document)))
    schema_path = SCHEMAS / "planning/events" / (event.event_type.split(":")[-2] + ".v1.json")
    schema: JsonObject = json.loads(schema_path.read_text())
    assert schema["$id"] == event.event_type
    return Draft202012Validator(schema, registry=Registry[Schema]().with_resources(resources))


def _all_events() -> tuple[DomainEvent, ...]:
    workspace, plan, draft, rev, parent = (
        WorkspaceId(uid(1)),
        PlanId(uid(10)),
        DraftId(uid(30)),
        uid(40),
        uid(41),
    )
    digest = "sha256:" + "a" * 64
    return (
        events.PlanCreated(plan, workspace, ProjectId(uid(2)), "PLAN1", "Auth", PlanPurpose.STANDARD),
        events.DraftOpened(plan, workspace, draft, None, "empty", 1),
        events.DraftSaved(plan, workspace, draft, 2, digest, 1, 2, 3),
        events.DraftRebased(plan, workspace, draft, 3, RevisionId(parent), RevisionId(rev), 4, 5, 1),
        events.DraftAbandoned(plan, workspace, draft, 3, "plan_archived"),
        events.PlanRevisionPublished(
            plan,
            workspace,
            RevisionId(rev),
            2,
            RevisionId(parent),
            digest,
            "Auth",
            RevisionOrigin.DRAFT,
            draft,
        ),
        events.PlanRevisionRestored(plan, workspace, RevisionId(rev), 3, RevisionId(parent), 1, digest),
        events.PlanArchived(plan, workspace, ProjectId(uid(2)), "PLAN1", (draft,)),
    )


@pytest.mark.parametrize("event", _all_events(), ids=lambda e: type(e).__name__)
def test_event_payload_is_valid_against_its_schema_and_lives_in_the_plan_stream(event: DomainEvent) -> None:
    _validator(event).validate(event.payload())
    assert event.stream_kind == "plan"
    assert event.stream_kind in STREAM_KINDS
    assert event.stream_id() == uid(10)
    assert event.scope_workspace_id() == uid(1)


def test_event_inventory_matches_the_classes_and_the_schemas() -> None:
    classes = [getattr(events, name) for name in events.__all__ if name != "EVENT_TYPES"]
    declared = {cls.event_type for cls in classes}
    assert declared == set(events.EVENT_TYPES)
    assert {type(event).event_type for event in _all_events()} == declared
    on_disk = {
        json.loads(path.read_text())["$id"] for path in (SCHEMAS / "planning/events").glob("*.v1.json")
    }
    assert on_disk == declared


def test_publication_payload_carries_no_document() -> None:
    published = next(e for e in _all_events() if isinstance(e, events.PlanRevisionPublished))
    assert "document" not in published.payload()
    assert set(published.payload()) == {
        "plan_id",
        "revision_id",
        "revision_no",
        "parent_revision_id",
        "content_digest",
        "title",
        "origin",
        "draft_id",
    }


def test_event_with_an_unknown_closed_value_has_no_payload() -> None:
    unknown = cast("Literal['user', 'plan_archived']", "because")  # a stored value outside the closed set
    bad = events.DraftAbandoned(PlanId(uid(10)), WorkspaceId(uid(1)), DraftId(uid(30)), 1, unknown)
    with pytest.raises(ValueError, match="plan_archived"):
        bad.payload()


def test_bus_registry_registers_the_eight_planning_events() -> None:
    from skm.modules.access.permissions import PERMISSIONS

    registry = BusRegistry.build(
        (MODULE,),
        schemas=SchemaRegistry.load_default(),
        permission_catalog=frozenset(PERMISSIONS),
        disabled_modules=frozenset(),
    )
    registered = registry.event_types()
    assert set(registered) == set(events.EVENT_TYPES)
    assert len(registered) == 8
    assert all(event_type == cls.event_type for event_type, cls in registered.items())
    assert MODULE.events == tuple(registered[urn] for urn in (cls.event_type for cls in MODULE.events))


def test_bus_registry_refuses_a_second_registration_of_a_planning_event() -> None:
    from dataclasses import replace as clone

    from skm.application_bus.registry import BusRegistryError

    duplicate = clone(MODULE, events=(*MODULE.events, events.PlanCreated))
    with pytest.raises(BusRegistryError, match="already registered"):
        BusRegistry.build(
            (duplicate,),
            schemas=SchemaRegistry.load_default(),
            permission_catalog=frozenset(),
            disabled_modules=frozenset(),
        )
