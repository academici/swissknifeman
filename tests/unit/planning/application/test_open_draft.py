"""Core authoring commands of planning on the real bus over the memory backend (planning §7.1 to §7.4, §7.6).

Everything is real: the planning manifest, bus, authorizer, config loader, the memory repositories, schema
validation. The revision a test needs is seeded through the repository port, because publication is another
leaf.
"""

import copy
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as ACCESS_REPOSITORIES
from skm.adapters.memory.artifacts import REPOSITORIES as ARTIFACT_REPOSITORIES
from skm.adapters.memory.config_store import MemoryConfigStore, write_config_entry
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.extensions import REPOSITORIES as EXTENSION_REPOSITORIES
from skm.adapters.memory.planning import REPOSITORIES as PLANNING_REPOSITORIES
from skm.adapters.memory.planning.state import planning_state
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as WORKSPACE_REPOSITORIES
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed, SkmError, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import EntityId, PlanId, PrincipalId, ProjectId, RevisionId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenPepperSource
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.artifacts.module import MODULE as ARTIFACTS
from skm.modules.artifacts.ports import BlobStore
from skm.modules.extensions.ports import PackRepository, QuarantineRepository, ResourceRepository
from skm.modules.planning.application.commands import save_draft
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.identity import iter_entities
from skm.modules.planning.domain.plan import Plan, PlanLifecycle, PlanPurpose, new_plan, record_publication
from skm.modules.planning.domain.revision import RevisionOrigin, new_revision_meta
from skm.modules.planning.domain.specification import EntityKind, from_document
from skm.modules.planning.generated.commands import (
    AbandonDraft,
    ArchivePlan,
    CreatePlan,
    OpenDraft,
    SaveDraft,
)
from skm.modules.planning.module import MODULE as PLANNING
from skm.modules.planning.ports import (
    AliasKind,
    DraftRepository,
    MaterialPin,
    PlanCounters,
    PlanRepository,
    RevisionRecord,
    RevisionRepository,
)
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import ArchiveProject, CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, StoredContribution
from support.registries import schemas, settings_registry

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
EVERYTHING = frozenset(CATALOG)
URN = "urn:skm:planning:specification:v1"
INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
MAX_OPEN = 3

PHASE: dict[str, Any] = {
    "key": "P1",
    "title": "Retries",
    "goal": "Reliable delivery",
    "design_state": "detailed",
}
ITEM: dict[str, Any] = {
    "key": "P1.1",
    "phase": "P1",
    "title": "Retry loop",
    "summary": "Retry failed deliveries",
    "why": "Lost webhooks",
    "review": {"mode": "required", "max_rounds": 2},
}
CHECK: dict[str, Any] = {
    "key": "V1",
    "owner": "P1.1",
    "title": "Tests",
    "category": "acceptance",
    "kind": "command",
    "required": True,
    "definition": {"argv": ["true"], "cwd": {"mount": "api", "path": "."}},
}


def document(**members: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": URN,
        "title": "Webhooks",
        "goal": "Deliveries are never lost",
        "phases": [copy.deepcopy(PHASE)],
        "items": [copy.deepcopy(ITEM)],
    }
    base.update(members)
    return base


class Packs:
    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: object) -> tuple[()]:
        return ()


@dataclass
class World:
    backend: InMemoryBackend
    bus: Bus
    clock: FrozenClock
    ids: SequentialIds
    owner: Actor | None = None
    counter: Iterator[int] = field(default_factory=count)

    def meta(self, key: str | None = None) -> RequestMeta:
        return RequestMeta(f"req_{next(self.counter):0>26}", Surface.TEST, key, self.clock.now())

    def run(self, dto: object, *, key: str | None = None) -> Any:
        assert self.owner is not None
        return self.bus.dispatch(dto, actor=self.owner, meta=self.meta(key or f"key-{uuid4()}"))

    def uow(self, *, readonly: bool = False) -> Any:
        return self.backend.uow_factory()(self.meta(), readonly=readonly)

    def workspace(self, slug: str = "personal") -> WorkspaceId:
        return WorkspaceId(self.run(CreateWorkspace(slug=slug, title=slug)).workspace_id)

    def project(self, workspace_id: WorkspaceId, slug: str = "skm") -> ProjectId:
        return ProjectId(self.run(CreateProject(workspace_id=workspace_id, slug=slug, title=slug)).project_id)

    def plan_row(self, plan_id: PlanId | UUID) -> Plan:
        with self.uow(readonly=True) as uow:
            return uow.repo(PlanRepository).get(PlanId(plan_id))

    def draft_row(self, draft_id: DraftId | UUID) -> Any:
        with self.uow(readonly=True) as uow:
            return uow.repo(DraftRepository).get(DraftId(draft_id))

    def events(self, name: str) -> list[Any]:
        urn = f"urn:skm:planning:event:{name}:v1"
        return [event for event in self.backend.committed.core.events if event.type == urn]

    def event_count(self) -> int:
        return len(self.backend.committed.core.events)

    def set_instance(self, key: str, value: int) -> None:
        entry = StoredContribution(uuid4(), key, cast("Any", "set"), value, False, 1)
        write_config_entry(self.backend.committed, INSTANCE, entry)

    def publish_revision_row(
        self, plan_id: UUID, doc: dict[str, Any], pins: tuple[MaterialPin, ...] = ()
    ) -> RevisionId:
        """The current revision of a plan, written through the ports the way publication writes it."""
        with self.uow() as uow:
            plans = uow.repo(PlanRepository)
            plan = plans.get(PlanId(plan_id))
            revision_id = RevisionId(self.ids.new_id())
            meta = new_revision_meta(
                revision_id,
                plan,
                content_digest=specification_digest(doc),
                origin=RevisionOrigin.DRAFT,
                restored_from=None,
                change_reason="seed",
                actor=plan.created_by,
                now=NOW,
            )
            spec, _ = from_document(doc)
            identities = tuple(
                (EntityId(UUID(str(entity["id"]))), kind) for kind, _, entity in iter_entities(doc)
            )
            uow.repo(RevisionRepository).add(RevisionRecord(meta, spec, doc, identities, pins, ()))
            plans.save(
                record_publication(plan, revision_id, str(doc["title"]), NOW),
                expected_version=plan.row_version,
            )
            uow.commit()
        return revision_id


def build_world() -> World:
    registry = BusRegistry.build(
        (ACCESS, WORKSPACE, ARTIFACTS, PLANNING),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    packs = Packs()
    authorizer = RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **CORE_REPOSITORIES,
        **ACCESS_REPOSITORIES,
        **WORKSPACE_REPOSITORIES,
        **ARTIFACT_REPOSITORIES,
        **PLANNING_REPOSITORIES,
        **EXTENSION_REPOSITORIES,  # save_draft validates against the skill and runtime catalogs
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    bus = Bus(
        registry=registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=ConfigLoader(settings_registry(), packs),
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=GatewayTable(
            {TokenPepperSource: cast("Any", object()), BlobStore: cast("Any", object())},
            "control_plane_gateway",
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    made = World(backend, bus, clock, ids)
    with made.uow() as uow:
        uow.repo(ScopeRegistry).create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        principal = new_principal(
            principal_id=PrincipalId(ids.new_id()),
            kind=PrincipalKind.HUMAN,
            display_name="owner",
            created_by=None,
            now=NOW,
        )
        uow.repo(PrincipalRepository).add(principal)
        uow.repo(MembershipRepository).upsert(Membership(INSTANCE, principal.id, Role.OWNER, None, NOW))
        uow.commit()
    made.owner = Actor(principal_id=principal.id, kind=PrincipalKind.HUMAN, display_name="owner")
    return made


@dataclass
class Setup:
    world: World
    project: ProjectId = field(init=False)
    plan: UUID = field(init=False)

    def __post_init__(self) -> None:
        self.project = self.world.project(self.world.workspace())
        self.plan = self.world.run(CreatePlan(project_id=self.project, title="Webhooks")).plan_id

    def open(self, base: Any = "current") -> UUID:
        return self.world.run(OpenDraft(plan_id=self.plan, base=base)).draft_id

    def save(self, draft_id: UUID, version: int = 1, **form: Any) -> Any:
        return self.world.run(
            SaveDraft(plan_id=self.plan, draft_id=draft_id, expected_edit_version=version, **form)
        )

    def saved_with_ids(self, doc: dict[str, Any] | None = None) -> tuple[UUID, dict[str, Any]]:
        """An open draft at edit version 2 whose entities have ids, and that document."""
        draft_id = self.open()
        self.save(draft_id, document=doc if doc is not None else document())
        return draft_id, copy.deepcopy(self.world.draft_row(draft_id).document)


@pytest.fixture
def world() -> World:
    return build_world()


@pytest.fixture
def setup(world: World) -> Setup:
    return Setup(world)


def _changes(*operations: dict[str, Any]) -> dict[str, Any]:
    return {
        "changes": SaveDraft.from_json(
            {
                "plan_id": str(uuid4()),
                "draft_id": str(uuid4()),
                "expected_edit_version": 1,
                "changes": list(operations),
            }
        ).changes
    }


def _archive_project(setup: Setup) -> None:
    setup.world.run(ArchiveProject(project_id=setup.project, expected_row_version=1, reason="done"))


# ------------------------------------------------------------------ create_plan


def test_create_plan_allocates_alias_and_scope_atomically(setup: Setup) -> None:
    world = setup.world
    second = world.run(CreatePlan(project_id=setup.project, title="  Second  "))
    assert second.alias == "PLAN2"
    assert second.title == "Second"
    assert second.lifecycle_state == "active"
    assert second.draft_id is None
    with world.uow(readonly=True) as uow:
        scope = uow.repo(ScopeRegistry).get(ScopeId(second.plan_id))
        found = uow.repo(PlanRepository).find_by_alias(setup.project, "PLAN2")
    assert scope.kind is ScopeKind.PLAN
    assert scope.parent_id == ScopeId(setup.project)
    assert found is not None
    assert found.id == second.plan_id
    created = world.events("plan-created")
    assert [event.payload["alias"] for event in created] == ["PLAN1", "PLAN2"]


def test_each_project_counts_its_own_aliases(world: World) -> None:
    workspace_id = world.workspace()
    first = world.project(workspace_id, "one")
    second = world.project(workspace_id, "two")
    assert world.run(CreatePlan(project_id=first, title="A")).alias == "PLAN1"
    assert world.run(CreatePlan(project_id=second, title="B")).alias == "PLAN1"
    assert world.run(CreatePlan(project_id=first, title="C")).alias == "PLAN2"


def test_a_refused_create_consumes_neither_number_nor_scope(setup: Setup) -> None:
    world = setup.world
    with pytest.raises(ValidationFailed) as refused:
        world.run(CreatePlan(project_id=setup.project, title="x" * 301))
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert world.run(CreatePlan(project_id=setup.project, title="Next")).alias == "PLAN2"
    assert len(world.events("plan-created")) == 2


def test_create_plan_refuses_an_archived_project(setup: Setup) -> None:
    _archive_project(setup)
    with pytest.raises(PreconditionFailed) as refused:
        setup.world.run(CreatePlan(project_id=setup.project, title="Late"))
    assert refused.value.code is ErrorCode.PROJECT_ARCHIVED


def test_create_plan_does_not_drop_a_template_it_cannot_render(setup: Setup) -> None:
    class EmptyResources:
        def versions_of(self, *args: Any, **kwargs: Any) -> tuple[()]:
            return ()

    class EmptyPacks:
        def list_versions(self) -> tuple[()]:
            return ()

    class EmptyQuarantine:
        def quarantined_ids(self, *args: Any) -> frozenset[Any]:
            return frozenset()

    world = setup.world
    world.backend.factories = {
        **world.backend.factories,
        ResourceRepository: lambda _state: EmptyResources(),
        PackRepository: lambda _state: EmptyPacks(),
        QuarantineRepository: lambda _state: EmptyQuarantine(),
    }
    before = world.event_count()
    plans = dict(planning_state(world.backend.committed).plans)
    drafts = dict(planning_state(world.backend.committed).drafts)
    with pytest.raises(SkmError) as refused:
        world.run(CreatePlan(project_id=setup.project, title="T", template_key="feature"))
    assert refused.value.code is ErrorCode.NOT_FOUND
    assert world.event_count() == before
    assert planning_state(world.backend.committed).plans == plans
    assert planning_state(world.backend.committed).drafts == drafts


# ------------------------------------------------------------------ open_draft


def test_open_draft_without_a_revision_is_the_skeleton(setup: Setup) -> None:
    result = setup.world.run(OpenDraft(plan_id=setup.plan))
    draft = setup.world.draft_row(result.draft_id)
    assert result.edit_version == 1
    assert result.base_revision_id is None
    assert result.document_digest == specification_digest(draft.document)
    assert draft.state is DraftState.OPEN
    assert draft.document == {
        "schema": URN,
        "title": "Webhooks",
        "goal": "Webhooks",
        "phases": [],
        "items": [],
    }
    assert setup.world.events("draft-opened")[-1].payload["source"] == "current"


def test_open_draft_takes_the_current_revision_or_an_empty_skeleton_on_it(setup: Setup) -> None:
    world = setup.world
    _, doc = setup.saved_with_ids()
    revision_id = world.publish_revision_row(setup.plan, doc)

    current = world.run(OpenDraft(plan_id=setup.plan))
    assert current.base_revision_id == revision_id
    assert world.draft_row(current.draft_id).document == doc

    empty = world.run(OpenDraft(plan_id=setup.plan, base="empty"))
    assert empty.base_revision_id == revision_id
    assert world.draft_row(empty.draft_id).document["items"] == []
    assert world.events("draft-opened")[-1].payload["source"] == "empty"


def test_open_draft_over_the_limit_is_already_exists(setup: Setup) -> None:
    world = setup.world
    world.set_instance("planning.drafts.max_open", MAX_OPEN)
    for _ in range(MAX_OPEN):
        setup.open()
    with pytest.raises(Conflict) as refused:
        setup.open()
    assert refused.value.code is ErrorCode.ALREADY_EXISTS
    assert refused.value.details == {"open_drafts": MAX_OPEN, "limit": MAX_OPEN}
    assert len(world.events("draft-opened")) == MAX_OPEN


def test_closed_drafts_do_not_count_against_the_limit(setup: Setup) -> None:
    setup.world.set_instance("planning.drafts.max_open", 1)
    first = setup.open()
    setup.world.run(AbandonDraft(plan_id=setup.plan, draft_id=first, expected_edit_version=1))
    assert setup.open() != first


def test_open_draft_limit_race_does_not_exceed_max_open(setup: Setup) -> None:
    """Memory variant of ``test_open_draft_limit_race`` in ``integration/planning/test_concurrency.py``."""
    world = setup.world
    world.set_instance("planning.drafts.max_open", MAX_OPEN)
    for _ in range(MAX_OPEN - 1):
        setup.open()
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def racer() -> None:
        barrier.wait()
        try:
            outcomes.append(setup.open())
        except SkmError as error:
            outcomes.append(error)

    threads = [threading.Thread(target=racer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    refused = [outcome for outcome in outcomes if isinstance(outcome, Conflict)]
    assert len(outcomes) == 2
    assert len(refused) == 1
    assert refused[0].code is ErrorCode.ALREADY_EXISTS
    with world.uow(readonly=True) as uow:
        assert uow.repo(DraftRepository).count_open(PlanId(setup.plan)) == MAX_OPEN


def test_open_draft_with_the_same_key_replays_the_same_draft(setup: Setup) -> None:
    first = setup.world.run(OpenDraft(plan_id=setup.plan), key="open-once")
    second = setup.world.run(OpenDraft(plan_id=setup.plan), key="open-once")
    assert second.draft_id == first.draft_id
    assert len(setup.world.events("draft-opened")) == 1


def test_open_draft_guards_plan_and_project(setup: Setup) -> None:
    other = setup.world.run(CreatePlan(project_id=setup.project, title="Other")).plan_id
    setup.world.run(ArchivePlan(plan_id=other))
    with pytest.raises(PreconditionFailed) as archived:
        setup.world.run(OpenDraft(plan_id=other))
    assert archived.value.code is ErrorCode.PLAN_ARCHIVED

    _archive_project(setup)
    with pytest.raises(PreconditionFailed) as project:
        setup.open()
    assert project.value.code is ErrorCode.PROJECT_ARCHIVED


def _system_plan(setup: Setup) -> UUID:
    with setup.world.uow() as uow:
        project = uow.repo(PlanRepository).get(PlanId(setup.plan))
        plan_id = PlanId(setup.world.ids.new_id())
        plan = new_plan(
            plan_id,
            cast("Any", _ProjectRef(project.workspace_id, project.project_id)),
            "review-requests",
            "Review requests",
            project.created_by,
            NOW,
            purpose=PlanPurpose.REVIEW_REQUESTS,
        )
        uow.repo(ScopeRegistry).create(
            ScopeId(plan_id),
            ScopeKind.PLAN,
            parent=ScopeId(project.project_id),
            workspace_id=project.workspace_id,
        )
        uow.repo(PlanRepository).add(plan)
        uow.commit()
    return plan_id


@dataclass(frozen=True)
class _ProjectRef:
    workspace_id: UUID
    project_id: UUID


def test_the_system_plan_takes_neither_a_draft_nor_an_archive(setup: Setup) -> None:
    system = _system_plan(setup)
    for command in (OpenDraft(plan_id=system), ArchivePlan(plan_id=system)):
        with pytest.raises(PreconditionFailed) as refused:
            setup.world.run(command)
        assert refused.value.code is ErrorCode.INVALID_TRANSITION
        assert refused.value.details["reason"] == "system_plan"


# ------------------------------------------------------------------ save_draft


def test_two_stale_saves_are_a_version_conflict(setup: Setup) -> None:
    draft_id = setup.open()
    first = setup.save(draft_id, merge_patch={"goal": "First"})
    assert first.edit_version == 2
    for goal in ("Second", "Third"):
        with pytest.raises(Conflict) as stale:
            setup.save(draft_id, merge_patch={"goal": goal})
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        assert stale.value.details == {"expected": 1, "actual": 2}
    draft = setup.world.draft_row(draft_id)
    assert draft.document["goal"] == "First"
    assert draft.edit_version == 2
    assert len(setup.world.events("draft-saved")) == 1


def test_parallel_saves_of_one_version_let_one_through(setup: Setup) -> None:
    draft_id = setup.open()
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def racer(goal: str) -> None:
        barrier.wait()
        try:
            outcomes.append(setup.save(draft_id, merge_patch={"goal": goal}))
        except SkmError as error:
            outcomes.append(error)

    threads = [threading.Thread(target=racer, args=(goal,)) for goal in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    refused = [outcome for outcome in outcomes if isinstance(outcome, Conflict)]
    assert len(refused) == 1
    assert refused[0].code is ErrorCode.VERSION_CONFLICT
    assert setup.world.draft_row(draft_id).edit_version == 2


def test_the_repository_enforces_the_edit_version_itself(setup: Setup) -> None:
    draft_id = setup.open()
    setup.save(draft_id, merge_patch={"goal": "Moved on"})
    with setup.world.uow() as uow:
        drafts = uow.repo(DraftRepository)
        draft = drafts.get(DraftId(draft_id))
        with pytest.raises(Conflict) as stale:
            drafts.save(replace(draft, edit_version=3), expected_edit_version=1)
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    assert stale.value.details == {"expected": 1, "actual": 2}


@pytest.mark.parametrize(
    ("name", "changed"),
    [
        ("plan_id", {"plan_id": PlanId(UUID("01900000-0000-7000-8000-00000000abcd"))}),
        ("workspace_id", {"workspace_id": WorkspaceId(UUID("01900000-0000-7000-8000-00000000abcd"))}),
        ("created_at", {"created_at": NOW + timedelta(days=1)}),
    ],
)
def test_the_draft_repository_refuses_owned_columns(setup: Setup, name: str, changed: dict[str, Any]) -> None:
    draft_id = setup.open()
    with setup.world.uow() as uow:
        drafts = uow.repo(DraftRepository)
        draft = drafts.get(DraftId(draft_id))
        with pytest.raises(ValidationFailed) as refused:
            drafts.save(replace(draft, **changed), expected_edit_version=1)
    assert refused.value.code is ErrorCode.FIELD_OWNED
    assert refused.value.details == {"target": "draft", "field": name}


def test_the_draft_repository_refuses_another_schema_and_a_closed_draft(setup: Setup) -> None:
    draft_id = setup.open()
    with setup.world.uow() as uow:
        drafts = uow.repo(DraftRepository)
        draft = drafts.get(DraftId(draft_id))
        other = {**draft.document, "schema": "other"}
        with pytest.raises(ValidationFailed) as refused:
            drafts.save(replace(draft, document=other), expected_edit_version=1)
    assert refused.value.code is ErrorCode.FIELD_OWNED

    setup.world.run(AbandonDraft(plan_id=setup.plan, draft_id=draft_id, expected_edit_version=1))
    with setup.world.uow() as uow:
        drafts = uow.repo(DraftRepository)
        closed = drafts.get(DraftId(draft_id))
        with pytest.raises(PreconditionFailed) as not_open:
            drafts.save(closed, expected_edit_version=1)
    assert not_open.value.code is ErrorCode.DRAFT_NOT_OPEN


def test_the_plan_repository_enforces_row_version_and_owned_columns(setup: Setup) -> None:
    with setup.world.uow() as uow:
        plans = uow.repo(PlanRepository)
        plan = plans.get(PlanId(setup.plan))
        with pytest.raises(Conflict) as stale:
            plans.save(plan, expected_version=plan.row_version + 1)
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        with pytest.raises(ValidationFailed) as owned:
            plans.save(replace(plan, alias="PLAN9"), expected_version=plan.row_version)
    assert owned.value.code is ErrorCode.FIELD_OWNED
    assert owned.value.details == {"target": "plan", "field": "alias"}


def test_a_schema_invalid_result_leaves_the_draft_unchanged(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    events = setup.world.event_count()
    for form in (
        {"merge_patch": {"goal": None}},
        {"merge_patch": {"surprise": 1}},
        _changes({"op": "patch", "target": "P1.1", "merge_patch": {"title": None}}),
    ):
        with pytest.raises(ValidationFailed) as refused:
            setup.save(draft_id, 2, **form)
        assert refused.value.code is ErrorCode.SCHEMA_INVALID
        assert refused.value.details["issues"]
        assert refused.value.details["applied"] is False
        assert "change_index" not in refused.value.details
    draft = setup.world.draft_row(draft_id)
    assert draft.document == doc
    assert draft.edit_version == 2
    assert setup.world.event_count() == events


def test_a_schema_invalid_full_document_leaves_the_draft_unchanged(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    invalid = copy.deepcopy(doc)
    del invalid["goal"]
    with pytest.raises(ValidationFailed) as refused:
        setup.save(draft_id, 2, document=invalid)
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert setup.world.draft_row(draft_id).document == doc
    assert setup.world.draft_row(draft_id).edit_version == 2


@pytest.mark.parametrize(
    ("form", "pointer"),
    [
        (
            {"merge_patch": {"extensions": {"acme/tool": {"schema_version": 1, "value": 1.5}}}},
            "/extensions/acme~1tool/value",
        ),
        (
            {"merge_patch": {"extensions": {"acme/tool": {"schema_version": 1, "value": {"a": [0, 2.0]}}}}},
            "/extensions/acme~1tool/value/a/1",
        ),
        (
            _changes(
                {
                    "op": "patch",
                    "target": "plan",
                    "merge_patch": {"extensions": {"acme/tool": {"schema_version": 1, "value": 1.5}}},
                }
            ),
            "/extensions/acme~1tool/value",
        ),
        (  # the schema takes 2.0 as an integer; canonical JSON has no form for it either
            _changes({"op": "patch", "target": "P1.1", "merge_patch": {"review": {"max_rounds": 2.0}}}),
            "/items/0/review/max_rounds",
        ),
    ],
)
def test_a_float_in_the_document_is_schema_invalid_and_changes_nothing(
    setup: Setup, form: dict[str, Any], pointer: str
) -> None:
    draft_id, doc = setup.saved_with_ids()
    events = setup.world.event_count()
    with pytest.raises(ValidationFailed) as refused:
        setup.save(draft_id, 2, **form)
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert refused.value.details["applied"] is False
    assert cast("Any", refused.value.details)["issues"] == [
        {"pointer": pointer, "message": "a float has no canonical JSON form", "schema_pointer": ""}
    ]
    draft = setup.world.draft_row(draft_id)
    assert draft.document == doc
    assert draft.edit_version == 2
    assert setup.world.event_count() == events


def test_a_float_in_a_full_document_is_schema_invalid_and_changes_nothing(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    events = setup.world.event_count()
    invalid = copy.deepcopy(doc)
    invalid["extensions"] = {"acme/tool": {"schema_version": 1, "value": 1.5}}
    with pytest.raises(ValidationFailed) as refused:
        setup.save(draft_id, 2, document=invalid)
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert [issue["pointer"] for issue in cast("Any", refused.value.details)["issues"]] == [
        "/extensions/acme~1tool/value"
    ]
    assert setup.world.draft_row(draft_id).document == doc
    assert setup.world.draft_row(draft_id).edit_version == 2
    assert setup.world.event_count() == events


def test_a_number_that_is_not_finite_is_schema_invalid_and_changes_nothing(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    events = setup.world.event_count()
    with pytest.raises(ValidationFailed) as refused:
        setup.save(
            draft_id,
            2,
            merge_patch={"extensions": {"acme/tool": {"schema_version": 1, "value": float("nan")}}},
        )
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert setup.world.draft_row(draft_id).document == doc
    assert setup.world.draft_row(draft_id).edit_version == 2
    assert setup.world.event_count() == events


def test_an_integer_extension_value_is_still_saved(setup: Setup) -> None:
    draft_id = setup.open()
    extensions = {"acme/tool": {"schema_version": 1, "value": {"a": [0, 2], "c": True}}}
    assert setup.save(draft_id, merge_patch={"extensions": extensions}).edit_version == 2
    assert setup.world.draft_row(draft_id).document["extensions"] == extensions


def test_a_semantically_invalid_document_is_saved_with_its_findings(setup: Setup) -> None:
    draft_id = setup.open()
    broken = document()
    broken["items"][0]["depends_on"] = ["P9.9"]
    result = setup.save(draft_id, document=broken)
    assert result.edit_version == 2
    assert "ref_unknown" in {found.code for found in result.findings}
    assert result.counts.error >= 1
    payload = setup.world.events("draft-saved")[-1].payload
    assert payload["counts"]["error"] == result.counts.error
    assert payload["document_digest"] == result.document_digest
    assert "document" not in payload
    assert setup.world.draft_row(draft_id).document["items"][0]["depends_on"] == ["P9.9"]


def test_a_cycle_is_a_finding_of_a_saved_draft(setup: Setup) -> None:
    draft_id = setup.open()
    other = {**copy.deepcopy(ITEM), "key": "P1.2", "depends_on": ["P1.1"]}
    first = {**copy.deepcopy(ITEM), "depends_on": ["P1.2"]}
    result = setup.save(draft_id, document=document(items=[first, other]))
    assert "dependency_cycle" in {found.code for found in result.findings}
    assert not result.rule_failures


def test_a_missing_file_version_is_a_finding_not_a_refusal(setup: Setup) -> None:
    draft_id = setup.open()
    material = {
        "key": "spec",
        "title": "Spec",
        "kind": "file_version",
        "file_version_id": "0192f5c3-9999-7000-8000-000000000001",
        "role": "input",
        "why": "Reference",
    }
    result = setup.save(draft_id, document=document(materials=[material]))
    assert "material_unavailable" in {found.code for found in result.findings}


def test_merge_patch_may_not_change_the_schema_but_may_repeat_it(setup: Setup) -> None:
    draft_id = setup.open()
    for value in ("urn:skm:planning:specification:v2", None):
        with pytest.raises(ValidationFailed) as refused:
            setup.save(draft_id, merge_patch={"schema": value})
        assert refused.value.code is ErrorCode.FIELD_OWNED
        assert refused.value.details == {"target": "plan", "field": "schema"}
    assert setup.save(draft_id, merge_patch={"schema": URN, "goal": "Same schema"}).edit_version == 2


def test_the_root_patch_of_the_api_example_issues_ids(setup: Setup) -> None:
    """``examples/api/03-save-draft-merge-patch.http`` without ``position``: the schema has no such member."""
    draft_id = setup.open()
    result = setup.save(
        draft_id,
        merge_patch={
            "goal": "Webhook deliveries are retried with backoff and never lost",
            "phases": [PHASE],
            "items": [ITEM],
        },
    )
    assert [(item.entity_kind, item.display_key) for item in result.assigned_ids] == [
        ("phase", "P1"),
        ("item", "P1.1"),
    ]
    saved = setup.world.draft_row(draft_id).document
    assert saved["phases"][0]["id"] == str(result.assigned_ids[0].entity_id)
    assert saved["items"][0]["id"] == str(result.assigned_ids[1].entity_id)


def test_a_batch_fails_as_a_whole_and_names_its_operation(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    with pytest.raises(NotFound) as refused:
        setup.save(
            draft_id,
            2,
            **_changes(
                {"op": "patch", "target": "P1.1", "merge_patch": {"title": "Applied?"}},
                {"op": "remove", "target": "P9.9"},
            ),
        )
    assert refused.value.details["change_index"] == 1
    assert refused.value.details["applied"] is False
    assert setup.world.draft_row(draft_id).document == doc


def test_a_batch_refuses_an_owned_field(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    entity_id = doc["items"][0]["id"]
    with pytest.raises(ValidationFailed) as refused:
        setup.save(
            draft_id, 2, **_changes({"op": "patch", "target": "P1.1", "merge_patch": {"id": str(uuid4())}})
        )
    assert refused.value.code is ErrorCode.FIELD_OWNED
    assert refused.value.details["field"] == "id"
    assert setup.world.draft_row(draft_id).document["items"][0]["id"] == entity_id


def test_a_batch_fills_item_defaults_and_keeps_ids_through_a_rekey(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    entity_id = doc["items"][0]["id"]
    added = {key: value for key, value in ITEM.items() if key != "review"} | {"key": "P1.2"}
    result = setup.save(
        draft_id,
        2,
        **_changes(
            {"op": "add", "kind": "item", "entity": added},
            {"op": "rekey", "target": f"entity:{entity_id}", "new_key": "P1.3"},
            {"op": "patch", "target": f"entity:{entity_id}", "merge_patch": {"title": "Renamed"}},
        ),
    )
    assert [item.display_key for item in result.assigned_ids] == ["P1.2"]
    items = {item["key"]: item for item in setup.world.draft_row(draft_id).document["items"]}
    assert items["P1.3"]["id"] == entity_id
    assert items["P1.3"]["title"] == "Renamed"
    assert items["P1.2"]["route"] == {"class": "implementation", "effort": "high"}
    assert items["P1.2"]["review"]["mode"] == "required"


def test_an_oversized_document_is_refused_and_changes_nothing(setup: Setup) -> None:
    world = setup.world
    world.set_instance("planning.drafts.max_document_bytes", 65536)
    draft_id = setup.open()
    with pytest.raises(ValidationFailed) as refused:
        setup.save(draft_id, merge_patch={"non_goals": ["x" * 1000] * 70})
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert "65536 bytes" in cast("Any", refused.value.details)["issues"][0]["message"]
    assert world.draft_row(draft_id).edit_version == 1


def test_save_guards_the_owner_the_state_and_the_order_of_checks(setup: Setup) -> None:
    world = setup.world
    other = world.run(CreatePlan(project_id=setup.project, title="Other")).plan_id
    draft_id = setup.open()
    with pytest.raises(NotFound) as foreign:
        world.run(SaveDraft(plan_id=other, draft_id=draft_id, expected_edit_version=1, merge_patch={}))
    assert foreign.value.details["kind"] == "draft"

    world.run(AbandonDraft(plan_id=setup.plan, draft_id=draft_id, expected_edit_version=1))
    with pytest.raises(PreconditionFailed) as closed:
        setup.save(draft_id, 99, merge_patch={"goal": "Late"})  # the state wins over the stale version
    assert closed.value.code is ErrorCode.DRAFT_NOT_OPEN


def test_save_refuses_an_archived_project(setup: Setup) -> None:
    draft_id = setup.open()
    _archive_project(setup)
    with pytest.raises(PreconditionFailed) as refused:
        setup.save(draft_id, merge_patch={"goal": "Late"})
    assert refused.value.code is ErrorCode.PROJECT_ARCHIVED
    assert setup.world.draft_row(draft_id).edit_version == 1


# ------------------------------------------------------------------ identity


def _no_ids_issued(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object) -> None:
        pytest.fail("ids were issued before the identity guard")

    monkeypatch.setattr(save_draft, "assign_missing_ids", refuse)


def _with_check() -> dict[str, Any]:
    return document(checks=[copy.deepcopy(CHECK)])


def test_a_stripped_document_is_refused_before_ids_are_issued(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_id, doc = setup.saved_with_ids(_with_check())
    stripped = copy.deepcopy(doc)
    del stripped["items"][0]["id"]
    del stripped["checks"][0]["id"]
    _no_ids_issued(monkeypatch)
    with pytest.raises(ValidationFailed) as refused:
        setup.save(draft_id, 2, document=stripped)
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert refused.value.details["issues"] == [
        {"pointer": "/items/0/id", "message": "existing entity id required", "schema_pointer": ""},
        {"pointer": "/checks/0/id", "message": "existing entity id required", "schema_pointer": ""},
    ]
    assert setup.world.draft_row(draft_id).document == doc


def test_a_stripped_root_patch_is_refused_before_ids_are_issued(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft_id, doc = setup.saved_with_ids()
    _no_ids_issued(monkeypatch)
    with pytest.raises(ValidationFailed) as refused:
        setup.save(draft_id, 2, merge_patch={"phases": [PHASE], "goal": "New goal"})
    assert refused.value.code is ErrorCode.SCHEMA_INVALID
    assert [issue["pointer"] for issue in cast("Any", refused.value.details)["issues"]] == ["/phases/0/id"]
    assert setup.world.draft_row(draft_id).document == doc


def test_a_full_replacement_with_its_ids_keeps_every_identity(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids(_with_check())
    ids = {str(entity["id"]) for _, _, entity in iter_entities(doc)}
    replacement = copy.deepcopy(doc)
    replacement["title"] = "Rebuilt"
    replacement["items"][0]["title"] = "Rebuilt item"
    result = setup.save(draft_id, 2, document=replacement)
    assert result.assigned_ids == ()
    saved = setup.world.draft_row(draft_id).document
    assert {str(entity["id"]) for _, _, entity in iter_entities(saved)} == ids
    assert saved["items"][0]["title"] == "Rebuilt item"


def test_a_new_key_in_a_replacement_gets_an_id_next_to_kept_ones(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    replacement = copy.deepcopy(doc)
    replacement["items"].append({**copy.deepcopy(ITEM), "key": "P1.2"})
    result = setup.save(draft_id, 2, document=replacement)
    assert [item.display_key for item in result.assigned_ids] == ["P1.2"]
    assert setup.world.draft_row(draft_id).document["items"][0]["id"] == doc["items"][0]["id"]


def test_an_explicit_other_id_is_a_deliberate_rebuild(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    replacement = copy.deepcopy(doc)
    other = "0192f5c6-1005-7a05-8000-5e6f708192a8"
    replacement["items"][0]["id"] = other
    result = setup.save(draft_id, 2, document=replacement)
    assert result.assigned_ids == ()
    assert setup.world.draft_row(draft_id).document["items"][0]["id"] == other


def test_an_explicit_remove_and_add_gets_a_new_identity(setup: Setup) -> None:
    draft_id, doc = setup.saved_with_ids()
    old_id = doc["items"][0]["id"]
    result = setup.save(
        draft_id,
        2,
        **_changes(
            {"op": "remove", "target": "P1.1"},
            {"op": "add", "kind": "item", "entity": ITEM},
        ),
    )
    assert [item.display_key for item in result.assigned_ids] == ["P1.1"]
    new_id = setup.world.draft_row(draft_id).document["items"][0]["id"]
    assert new_id == str(result.assigned_ids[0].entity_id)
    assert new_id != old_id


# ------------------------------------------------------------------ abandon_draft


def test_abandon_closes_the_draft_and_records_the_reason(setup: Setup) -> None:
    world = setup.world
    draft_id = setup.open()
    result = world.run(AbandonDraft(plan_id=setup.plan, draft_id=draft_id, expected_edit_version=1))
    assert result.state == "abandoned"
    assert result.closed_at == NOW
    draft = world.draft_row(draft_id)
    assert draft.state is DraftState.ABANDONED
    assert draft.closed_at == NOW
    assert draft.edit_version == 1
    assert world.events("draft-abandoned")[-1].payload["reason"] == "user"
    with pytest.raises(PreconditionFailed) as again:
        world.run(AbandonDraft(plan_id=setup.plan, draft_id=draft_id, expected_edit_version=1))
    assert again.value.code is ErrorCode.DRAFT_NOT_OPEN


def test_abandon_is_checked_against_the_edit_version_and_the_plan(setup: Setup) -> None:
    world = setup.world
    draft_id = setup.open()
    setup.save(draft_id, merge_patch={"goal": "Edited"})
    with pytest.raises(Conflict) as stale:
        world.run(AbandonDraft(plan_id=setup.plan, draft_id=draft_id, expected_edit_version=1))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    other = world.run(CreatePlan(project_id=setup.project, title="Other")).plan_id
    with pytest.raises(NotFound):
        world.run(AbandonDraft(plan_id=other, draft_id=draft_id, expected_edit_version=2))
    assert world.draft_row(draft_id).state is DraftState.OPEN


def test_abandon_refuses_an_archived_project(setup: Setup) -> None:
    draft_id = setup.open()
    _archive_project(setup)
    with pytest.raises(PreconditionFailed) as refused:
        setup.world.run(AbandonDraft(plan_id=setup.plan, draft_id=draft_id, expected_edit_version=1))
    assert refused.value.code is ErrorCode.PROJECT_ARCHIVED


# ------------------------------------------------------------------ archive_plan


def test_archive_abandons_open_drafts_and_leaves_the_history(setup: Setup) -> None:
    world = setup.world
    _, doc = setup.saved_with_ids()
    revision_id = world.publish_revision_row(setup.plan, doc)
    first, second = setup.open(), setup.open("empty")
    closed = setup.open()
    world.run(AbandonDraft(plan_id=setup.plan, draft_id=closed, expected_edit_version=1))
    version = world.plan_row(setup.plan).row_version

    result = world.run(ArchivePlan(plan_id=setup.plan, expected_row_version=version))

    assert result.changed is True
    assert result.lifecycle_state == "archived"
    assert result.row_version == version + 1
    assert len(result.abandoned_draft_ids) == 3  # the one saved above and the two opened after the revision
    assert {first, second} <= set(result.abandoned_draft_ids)
    assert closed not in result.abandoned_draft_ids
    plan = world.plan_row(setup.plan)
    assert plan.lifecycle is PlanLifecycle.ARCHIVED
    assert plan.current_revision_id == revision_id
    with world.uow(readonly=True) as uow:
        assert uow.repo(RevisionRepository).get_document(revision_id) == doc
        assert uow.repo(DraftRepository).count_open(PlanId(setup.plan)) == 0
    reasons = [event.payload["reason"] for event in world.events("draft-abandoned")]
    assert reasons == ["user", "plan_archived", "plan_archived", "plan_archived"]
    assert world.events("plan-archived")[-1].payload["abandoned_draft_ids"] == [
        str(item) for item in result.abandoned_draft_ids
    ]


def test_archive_of_an_archived_plan_is_a_no_op_without_events(setup: Setup) -> None:
    world = setup.world
    first = world.run(ArchivePlan(plan_id=setup.plan))
    row = world.plan_row(setup.plan)
    events = world.event_count()
    second = world.run(ArchivePlan(plan_id=setup.plan))
    assert second.changed is False
    assert second.abandoned_draft_ids == ()
    assert second.row_version == first.row_version
    assert world.plan_row(setup.plan) == row
    assert world.event_count() == events


def test_an_archived_plan_stays_a_no_op_after_its_project_is_archived(setup: Setup) -> None:
    setup.world.run(ArchivePlan(plan_id=setup.plan))
    _archive_project(setup)
    assert setup.world.run(ArchivePlan(plan_id=setup.plan)).changed is False


def test_archive_checks_the_expected_row_version(setup: Setup) -> None:
    version = setup.world.plan_row(setup.plan).row_version
    with pytest.raises(Conflict) as stale:
        setup.world.run(ArchivePlan(plan_id=setup.plan, expected_row_version=version + 5))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    assert stale.value.details == {"expected": version + 5, "actual": version}
    assert setup.world.plan_row(setup.plan).lifecycle is PlanLifecycle.ACTIVE


def test_archive_refuses_an_active_plan_of_an_archived_project(setup: Setup) -> None:
    _archive_project(setup)
    with pytest.raises(PreconditionFailed) as refused:
        setup.world.run(ArchivePlan(plan_id=setup.plan))
    assert refused.value.code is ErrorCode.PROJECT_ARCHIVED


def test_a_draft_after_the_archive_is_refused_and_an_old_one_is_closed(setup: Setup) -> None:
    world = setup.world
    draft_id = setup.open()
    world.run(ArchivePlan(plan_id=setup.plan))
    with pytest.raises(PreconditionFailed) as refused:
        setup.open()
    assert refused.value.code is ErrorCode.PLAN_ARCHIVED
    with pytest.raises(PreconditionFailed) as closed:
        setup.save(draft_id, merge_patch={"goal": "Late"})
    assert closed.value.code is ErrorCode.DRAFT_NOT_OPEN


def test_archive_racing_a_new_draft_leaves_no_open_draft(setup: Setup) -> None:
    world = setup.world
    barrier = threading.Barrier(2)
    opened: list[object] = []

    def opener() -> None:
        barrier.wait()
        try:
            opened.append(setup.open())
        except SkmError as error:
            opened.append(error)

    def archiver() -> None:
        barrier.wait()
        world.run(ArchivePlan(plan_id=setup.plan))

    threads = [threading.Thread(target=opener), threading.Thread(target=archiver)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(opened) == 1
    outcome = opened[0]
    if isinstance(outcome, SkmError):
        assert outcome.code is ErrorCode.PLAN_ARCHIVED
    else:
        assert world.draft_row(cast("UUID", outcome)).state is DraftState.ABANDONED
    with world.uow(readonly=True) as uow:
        assert uow.repo(DraftRepository).count_open(PlanId(setup.plan)) == 0


# ------------------------------------------------------------------ reading and the memory repositories


def test_reading_needs_no_checkout(setup: Setup) -> None:
    """The project has no mounted repository and no host binding: everything comes from the control plane."""
    world = setup.world
    draft_id, doc = setup.saved_with_ids()
    revision_id = world.publish_revision_row(setup.plan, doc)
    with world.uow(readonly=True) as uow:
        plans = uow.repo(PlanRepository)
        assert plans.find_by_alias(setup.project, "PLAN1") == plans.get(PlanId(setup.plan))
        assert plans.project_plan_refs(setup.project)["PLAN1"] == setup.plan
        assert plans.project_plan_refs(setup.project)[f"plan:{setup.plan}"] == setup.plan
        assert [row.id for row in plans.find_by_id_prefix(setup.project, str(setup.plan)[:13], limit=5)] == [
            setup.plan
        ]
        assert uow.repo(DraftRepository).get(DraftId(draft_id)).document == doc
        revisions = uow.repo(RevisionRepository)
        assert revisions.get_document(revision_id) == doc
        assert revisions.load_typed_document(revision_id) == doc
        assert [
            meta.id for meta in revisions.list_for_plan(PlanId(setup.plan), before_revision_no=None, limit=5)
        ] == [revision_id]
        assert set(revisions.identities(PlanId(setup.plan)).values()) == {EntityKind.PHASE, EntityKind.ITEM}


def test_a_readonly_unit_of_work_refuses_every_write(setup: Setup) -> None:
    draft_id = setup.open()
    with setup.world.uow(readonly=True) as uow:
        drafts = uow.repo(DraftRepository)
        draft = drafts.get(DraftId(draft_id))
        plan = uow.repo(PlanRepository).get(PlanId(setup.plan))
        for write in (
            lambda: drafts.save(draft, expected_edit_version=1),
            lambda: uow.repo(PlanRepository).save(plan, expected_version=plan.row_version),
            lambda: uow.repo(PlanCounters).allocate_plan_no(plan.workspace_id, plan.project_id),
        ):
            with pytest.raises(RuntimeError):
                write()


def test_a_returned_document_is_not_the_stored_row(setup: Setup) -> None:
    draft_id = setup.open()
    with setup.world.uow() as uow:
        drafts = uow.repo(DraftRepository)
        drafts.get(DraftId(draft_id)).document["goal"] = "Leaked"
        assert drafts.get(DraftId(draft_id)).document["goal"] == "Webhooks"


def test_a_committed_pin_selector_is_an_immutable_snapshot(setup: Setup) -> None:
    """No port reads pins yet: the stored row is the only reader, and it answers with copies."""
    world = setup.world
    _, doc = setup.saved_with_ids()
    selector: dict[str, Any] = {"kind": "heading", "value": {"path": ["intro"]}}
    pin = MaterialPin(EntityId(uuid4()), uuid4(), "input", selector)
    empty = MaterialPin(EntityId(uuid4()), uuid4(), "reference", None)
    snapshot = copy.deepcopy(selector)
    revision_id = world.publish_revision_row(setup.plan, doc, (pin, empty))

    def stored() -> tuple[MaterialPin, ...]:
        return planning_state(world.backend.committed).revisions[revision_id].pins

    selector["value"]["path"].append("leaked by the original")
    selector["kind"] = "leaked"
    assert stored() == (replace(pin, selector=snapshot), empty)

    returned = cast("Any", stored()[0].selector)
    returned["value"]["path"].append("leaked by the returned value")
    returned["kind"] = "leaked"
    assert stored()[0].selector == snapshot

    setup.open()  # the next commit takes over a deep copy of the row
    assert stored()[0].selector == snapshot


def test_revisions_are_append_only_and_an_id_stays_with_its_plan(setup: Setup) -> None:
    world = setup.world
    _, doc = setup.saved_with_ids()
    world.publish_revision_row(setup.plan, doc)
    other = world.run(CreatePlan(project_id=setup.project, title="Other")).plan_id
    with pytest.raises(Conflict) as taken:
        world.publish_revision_row(other, doc)
    assert taken.value.code is ErrorCode.ID_CONFLICT
    assert sorted(cast("Any", taken.value.details)["entity_ids"]) == sorted(
        str(entity["id"]) for _, _, entity in iter_entities(doc)
    )
    assert world.plan_row(other).current_revision_id is None
    assert not hasattr(RevisionRepository, "save")
    assert not hasattr(RevisionRepository, "delete")


def test_aliases_are_unique_in_a_project_and_only_legacy_ones_are_added(setup: Setup) -> None:
    with setup.world.uow() as uow:
        plans = uow.repo(PlanRepository)
        plans.add_alias(PlanId(setup.plan), "old-plan", AliasKind.LEGACY)
        assert plans.find_by_alias(setup.project, "old-plan") == plans.get(PlanId(setup.plan))
        with pytest.raises(Conflict) as taken:
            plans.add_alias(PlanId(setup.plan), "PLAN1", AliasKind.EXTERNAL)
        assert taken.value.code is ErrorCode.ALREADY_EXISTS
        assert taken.value.details["alias"] == "PLAN1"
        with pytest.raises(SkmError) as kind:
            plans.add_alias(PlanId(setup.plan), "PLAN2", AliasKind.SHORT)
        assert kind.value.code is ErrorCode.INTERNAL_ERROR


def test_a_superseding_plan_is_found_through_its_current_revision(setup: Setup) -> None:
    world = setup.world
    newer = world.run(CreatePlan(project_id=setup.project, title="Newer")).plan_id
    doc = document(plan_relations=[{"kind": "supersedes", "target": "PLAN1"}], phases=[], items=[])
    with world.uow() as uow:
        plans = uow.repo(PlanRepository)
        plan = plans.get(PlanId(newer))
        revision_id = RevisionId(world.ids.new_id())
        meta = new_revision_meta(
            revision_id,
            plan,
            content_digest=specification_digest(doc),
            origin=RevisionOrigin.DRAFT,
            restored_from=None,
            change_reason="seed",
            actor=plan.created_by,
            now=NOW,
        )
        spec, _ = from_document(doc)
        uow.repo(RevisionRepository).add(RevisionRecord(meta, spec, doc, (), (), (PlanId(setup.plan),)))
        plans.save(record_publication(plan, revision_id, "Newer", NOW), expected_version=plan.row_version)
        assert plans.superseded_by(PlanId(setup.plan)) == (newer,)
        assert plans.superseded_by(PlanId(newer)) == ()


def test_one_review_requests_plan_per_project(setup: Setup) -> None:
    _system_plan(setup)
    with setup.world.uow(readonly=True) as uow:
        found = uow.repo(PlanRepository).find_review_requests_plan(setup.project)
    assert found is not None
    assert found.alias == "review-requests"
    with pytest.raises(Conflict) as second:
        _system_plan(setup)
    assert second.value.code is ErrorCode.ALREADY_EXISTS
