"""Unit tests for ``IntentExpiryTask`` and module-gated ``build_janitor_tasks`` (kernel-platform §6)."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from skm.background.janitor import (
    ExpireStagedBlobsTask,
    IntentExpiryTask,
    JanitorService,
    JanitorTask,
    build_janitor_tasks,
)
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.bootstrap.modules import MODULE_CATALOG
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import PrincipalId, ScopeId, ToolIntentId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.artifacts.generated.commands import ExpireStagedBlobs
from skm.modules.policy.domain.tool_intent import (
    EffectKind,
    IntentState,
    RiskClass,
    ToolIntent,
    args_digest,
    normalize_args,
)
from skm.modules.policy.generated.commands import ExpireIntents
from skm.modules.policy.ports import ToolIntentRepository
from skm.modules.workspace.public import CreateWorkspace, CreateWorkspaceResult
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging.logger import get_logger
from skm.platform.system_ids import Uuid7Generator
from support.seed import SEED

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
OWNER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000e1"))


class _StaticTask:
    def __init__(self, name: str, count: int = 0, *, fail: Exception | None = None) -> None:
        self.name = name
        self._count = count
        self._fail = fail
        self.calls = 0

    def run(self) -> int:
        self.calls += 1
        if self._fail is not None:
            raise self._fail
        return self._count


def _open_mem_app(tmp_path: Path) -> tuple[App, FrozenClock, IdGenerator, WorkspaceId]:
    clock = FrozenClock(NOW)
    ids = Uuid7Generator(clock)
    bs = replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://127.0.0.1:5432/mem"}, tmp_path),
        instance_id=SEED.instance_id,
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        ids=ids,
        instance_id=SEED.instance_id,
    )
    app = build_app(bs, surface=Surface.CLI, environ={}, invocation={}, backend=None, overrides=ov)
    with app.uow_factory(RequestMeta("req_" + "1" * 26, Surface.CLI, None, NOW)) as uow:
        uow.repo(ScopeRegistry).create(SEED.instance_id, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        for pid, kind, name in (
            (SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system"),
            (OWNER_ID, PrincipalKind.HUMAN, "owner"),
        ):
            uow.repo(PrincipalRepository).add(
                new_principal(principal_id=pid, kind=kind, display_name=name, created_by=None, now=NOW)
            )
            uow.repo(MembershipRepository).upsert(Membership(SEED.instance_id, pid, Role.OWNER, None, NOW))
        uow.commit()
    owner_client = app.client(actor=Actor(OWNER_ID, PrincipalKind.HUMAN, "owner"), surface=Surface.CLI)
    created = cast(
        "CreateWorkspaceResult",
        owner_client.dispatch(
            CreateWorkspace(slug="main", title="Main"),
            idempotency_key=owner_client.new_idempotency_key(),
        ),
    )
    return app, clock, ids, WorkspaceId(created.workspace_id)


def _make_intent(intent_id: UUID, ws: WorkspaceId, *, expires_at: datetime) -> ToolIntent:
    norm = normalize_args(
        EffectKind.PUBLISH,
        {"target": "registry", "artifact_digest": "sha256:" + "a" * 64, "version": str(intent_id)},
    )
    return ToolIntent(
        id=ToolIntentId(intent_id),
        workspace_id=ws,
        scope_id=ScopeId(ws),
        subject_ref="step:1",
        actor_id=OWNER_ID,
        kind=EffectKind.PUBLISH,
        normalized_args=norm,
        args_digest=args_digest(EffectKind.PUBLISH, norm),
        risk=RiskClass.MEDIUM,
        reason="notify channel",
        state=IntentState.PROPOSED,
        denied_reason=None,
        created_at=NOW,
        expires_at=expires_at,
        row_version=1,
    )


def test_janitor_intent_expiry_tick(tmp_path: Path) -> None:
    app, clock, ids, ws = _open_mem_app(tmp_path)
    try:
        due_1 = UUID("01900000-0000-7000-8000-000000000101")
        due_2 = UUID("01900000-0000-7000-8000-000000000102")
        fresh = UUID("01900000-0000-7000-8000-000000000103")
        with app.uow_factory(RequestMeta("req_" + "2" * 26, Surface.CLI, None, NOW)) as uow:
            repo = uow.repo(ToolIntentRepository)
            repo.add(_make_intent(due_1, ws, expires_at=NOW + timedelta(minutes=5)))
            repo.add(_make_intent(due_2, ws, expires_at=NOW + timedelta(minutes=10)))
            repo.add(_make_intent(fresh, ws, expires_at=NOW + timedelta(hours=2)))
            uow.commit()

        clock.advance(timedelta(minutes=15))
        intent_task = IntentExpiryTask(
            app.bus,
            lambda limit: ExpireIntents(limit=limit),
            ids,
            clock,
            batch_size=1,
        )
        staging_task = ExpireStagedBlobsTask(
            app.bus,
            lambda limit: ExpireStagedBlobs(limit=limit),
            ids,
            clock,
        )
        enabled = tuple(entry.id for entry in MODULE_CATALOG)
        tasks = build_janitor_tasks(
            enabled_modules=enabled,
            staging_gc=staging_task,
            intent_expiry=intent_task,
        )
        assert [t.name for t in tasks] == ["staging_gc", "intent_expiry"]

        janitor = JanitorService(tasks, log=get_logger("test.janitor"))
        tick_1 = janitor.tick()
        assert tick_1.processed == 2

        with app.uow_factory(
            RequestMeta("req_" + "3" * 26, Surface.CLI, None, clock.now()), readonly=True
        ) as uow:
            repo = uow.repo(ToolIntentRepository)
            assert repo.get(ToolIntentId(due_1)).state is IntentState.EXPIRED
            assert repo.get(ToolIntentId(due_2)).state is IntentState.EXPIRED
            assert repo.get(ToolIntentId(fresh)).state is IntentState.PROPOSED
            uow.rollback()

        owner_client = app.client(actor=Actor(OWNER_ID, PrincipalKind.HUMAN, "owner"), surface=Surface.CLI)
        resolved = [
            env
            for env in owner_client.events(workspace_id=ws, after=0)
            if env.type.endswith("intent-resolved:v1")
        ]
        assert len(resolved) == 2
        assert {str(env.payload["outcome"]) for env in resolved} == {"expired"}

        assert janitor.tick().processed == 0
    finally:
        app.close()


def test_janitor_omits_intent_expiry_when_policy_disabled_and_isolates_failures() -> None:
    idem = _StaticTask("idempotency_gc", 1)
    staging = _StaticTask("staging_gc", 2)
    intents = _StaticTask("intent_expiry", 5)
    outbox = _StaticTask("outbox_gc", 3)

    without_policy: tuple[JanitorTask, ...] = build_janitor_tasks(
        enabled_modules=("access", "workspace", "artifacts"),
        idempotency_gc=idem,
        staging_gc=staging,
        intent_expiry=intents,
        outbox_gc=outbox,
    )
    assert [t.name for t in without_policy] == ["idempotency_gc", "staging_gc", "outbox_gc"]
    assert JanitorService(without_policy, log=get_logger("test.janitor")).tick().processed == 6
    assert intents.calls == 0

    boom = _StaticTask("staging_gc", fail=RuntimeError("transient store error"))
    tail = _StaticTask("outbox_gc", 4)
    svc = JanitorService((boom, tail), log=get_logger("test.janitor"))
    with pytest.raises(RuntimeError, match="transient store error"):
        svc.tick()
    assert tail.calls == 1
