"""Dual-backend harness (memory + PostgreSQL) for execution contract tests."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import pytest

from contracts.context.harness import (
    NOW,
    UNIT_ID,
    MutableBuiltinPacks,
    _spec_doc,
    core_pack,
    default_work_policy,
)
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    add_file_dto,
    dispatch_new,
    seed_principals,
)
from security.api.harness import History
from skm.application_bus.client import SkmClient
from skm.application_bus.context import CommandContext
from skm.application_bus.platform.migrations import SchemaVersionReader
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import (
    ContextManifestId,
    FileVersionId,
    HostId,
    PlanId,
    PrincipalId,
    ProjectId,
    RepositoryId,
    ResourceVersionId,
    RevisionId,
    ScopeId,
    WorkerId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.membership import Membership
from skm.modules.access.ports import MembershipRepository
from skm.modules.access.public import (
    CreateToken,
    RbacAuthorizer,
    Role,
    TokenPepperSource,
    authenticate_token,
)
from skm.modules.context import public as context
from skm.modules.context.domain.finalize import host_facts_to_meta, sha256_text, verify_finalization
from skm.modules.context.domain.host_inputs import (
    HostBlock,
    HostBlockMeta,
    HostFacts,
    HostInputKind,
    HostReadStatus,
)
from skm.modules.context.domain.render import format_host_block, render_block_text
from skm.modules.context.domain.request import (
    ContextRequest,
    ExecutionBlocks,
    PermissionsSummary,
    RunParams,
    RuntimeTarget,
    StepPurpose,
)
from skm.modules.context.ports import ContextRepository
from skm.modules.extensions import public as extensions
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.planning.application.publication_candidate import prepare
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.generated.commands import CreatePlan, OpenDraft, PublishRevision, SaveDraft
from skm.modules.planning.ports import DraftRepository, PlanRepository
from skm.modules.workspace.generated import documents as ws_docs
from skm.modules.workspace.generated.commands import HostArch, HostOs, RegisterHostDefsHostPlatform
from skm.modules.workspace.public import (
    AttachRepository,
    CreateProject,
    CreateWorkspace,
    RegisterHost,
    RegisterRepository,
    RegisterWorker,
)
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.system_clock import SystemClock
from skm.platform.tokens.heuristic import HeuristicTokenEstimator
from support.pg import TestDatabase
from support.seed import SEED

from .seed_helpers import COMMIT_1

VIEWER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d2"))
PEPPER = b"execution-contracts-pepper-32byt"


def _other_plan_spec(file_id: FileVersionId, plan_id: PlanId) -> JsonObject:
    """Entity IDs belong to one plan, including across workspaces."""
    import json

    text = json.dumps(_spec_doc(file_id))
    for number in range(0x901, 0x90A):
        entity_id = f"01900000-0000-7000-8000-{number:012x}"
        text = text.replace(entity_id, str(uuid5(plan_id, entity_id)))
    return cast("JsonObject", json.loads(text))


def ask(client: SkmClient, query: object) -> Any:
    """Read through the real query bus."""
    return client.ask(query)


class _FixedPepper:
    def pepper(self) -> bytes:
        return PEPPER


def _publish_revision(
    app: App,
    client: SkmClient,
    owner: Actor,
    clock: FrozenClock,
    plan_id: PlanId,
    patch: JsonObject,
    base: str,
) -> RevisionId:
    draft_res = dispatch_new(client, OpenDraft(plan_id=plan_id, base=cast("Any", base)))
    draft_id = DraftId(draft_res.draft_id)
    save_res = dispatch_new(
        client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=draft_res.edit_version,
            merge_patch=patch,
        ),
    )
    with app.uow_factory(RequestMeta("req_" + "9" * 26, Surface.CLI, None, NOW), readonly=True) as uow:
        p_draft = uow.repo(DraftRepository).get(draft_id)
        plan = uow.repo(PlanRepository).get(plan_id)
        p_scope = ScopeRef(ScopeKind.PLAN, ScopeId(plan_id))
        p_ctx = CommandContext(
            actor=owner,
            meta=RequestMeta("req_" + "8" * 26, Surface.CLI, None, NOW),
            scope=p_scope,
            scope_chain=uow.repo(ScopeRegistry).ancestors(p_scope.id),
            clock=clock,
            ids=SequentialIds(),
            entropy=DeterministicEntropy(),
            config=app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), p_scope),
            log=cast("Any", object()),
            gateways=GatewayTable({}, "control_plane_gateway"),
        )
        cand = prepare(uow, p_ctx, plan, p_draft)
        assert not cand.has_errors, (cand.report.findings, cand.report.rule_failures)
        digest = cand.content_digest
        uow.rollback()
    pub = dispatch_new(
        client, PublishRevision(plan_id, draft_id, int(save_res.edit_version), digest, reason="pub")
    )
    return RevisionId(pub.revision_id)


@dataclass
class ExecSide:
    kind: str
    app: App
    clock: FrozenClock
    owner: Actor
    viewer: Actor
    client: SkmClient
    viewer_client: SkmClient
    worker1_client: SkmClient
    ws: WorkspaceId
    proj: ProjectId
    repo_id: RepositoryId
    ws2: WorkspaceId
    proj2: ProjectId
    plan2_ws2: PlanId
    rev_ws2: RevisionId
    host1: HostId
    host2: HostId
    worker1: WorkerId
    worker2: WorkerId
    plan1: PlanId
    rev1: RevisionId
    rev2: RevisionId
    plan2: PlanId
    rev_p2: RevisionId
    fv1: FileVersionId
    fv2: FileVersionId
    workflow_rv_id: ResourceVersionId
    estimator: HeuristicTokenEstimator
    dsn: str | None
    ids: SequentialIds

    def new_id(self) -> UUID:
        return self.ids.new_id()

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        rid = f"req_{self.new_id().hex[:26]}"
        return self.app.uow_factory(RequestMeta(rid, Surface.CLI, None, self.clock.now()), readonly=readonly)

    def restricted_client(
        self, permissions: Sequence[str], *, scope_id: UUID | None = None, owner_token: bool = False
    ) -> SkmClient:
        tok = cast(
            "Any",
            self.client.dispatch(
                CreateToken(
                    name=f"tok-{self.new_id().hex[:8]}",
                    principal_id=None if owner_token else UUID(str(self.viewer.principal_id)),
                    scope_id=scope_id,
                    permissions=tuple(permissions),
                ),
            ),
        )
        with self.uow() as uow:
            act = authenticate_token(uow, tok.secret, pepper=PEPPER, now=self.clock.now())
            uow.commit()
        return self.app.client(actor=act, surface=Surface.CLI)

    def make_final_manifest(self, *, step_ref: str | None = None) -> ContextManifestId:
        sref = step_ref or f"step:{self.new_id()}"
        rt = RuntimeTarget(
            "codex_cli",
            "gpt-5",
            128000,
            frozenset(),
            frozenset(),
            (),
            "plan",
            "execute",
            "isolated",
            (),
            frozenset(),
            ("AGENTS.md",),
        )
        with self.uow() as uow:
            cfg = self.app.config.effective(
                uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PLAN, ScopeId(self.plan1))
            )
            req = ContextRequest(
                workspace_id=self.ws,
                project_id=self.proj,
                plan_id=self.plan1,
                revision_id=self.rev1,
                entity_id=UNIT_ID,
                project_slug="skm",
                purpose=StepPurpose("executor", "execute", sref.removeprefix("step:"), 1, 1),
                agent_profile_version_id=self.workflow_rv_id,
                runtime=rt,
                permissions=PermissionsSummary(
                    ("repo:src/**",), ("repo:**",), ("pytest",), (), "none", (), ()
                ),
                run=RunParams("run_1", "default", 1, 1, None, "none", "json", "en", ()),
                execution_blocks=ExecutionBlocks(
                    default_work_policy(), (), None, None, None, (), None, (), ()
                ),
                resume=None,
                task_risk="medium",
                research_queries=(),
                pack_pins=None,
            )
            draft = context.assemble_draft(uow, self.app.gateways, req, config=cfg, owner_ref=sref)
            uow.commit()
        blocks: list[HostBlock] = []
        metas: list[HostBlockMeta] = []
        for hi in draft.host_inputs:
            if hi.kind is HostInputKind.REPO_INSTRUCTIONS and hi.path == "AGENTS.md":
                hb = HostBlock(hi.request_id, HostReadStatus.SELF_LOADED, "AGENTS.md", None, None, None, None)
            elif hi.kind is HostInputKind.REPOSITORY_PATH:
                txt = "x = 1\n"
                pr = HostBlock(hi.request_id, HostReadStatus.OK, hi.path, txt, None, None, None)
                bt, tt, bd, sr = format_host_block(hi, pr)
                wr = render_block_text(
                    block_type=bt,
                    title=tt,
                    content=bd,
                    source_ref=sr,
                    templates=draft.templates,
                    prompt_plan=draft.prompt_plan,
                    variables=draft.variables,
                )
                hb = HostBlock(
                    hi.request_id,
                    HostReadStatus.OK,
                    hi.path,
                    txt,
                    sha256_text(txt),
                    len(txt),
                    self.estimator.estimate(wr),
                )
            else:
                hb = HostBlock(hi.request_id, HostReadStatus.MISSING, None, None, None, None, None)
            blocks.append(hb)
            metas.append(
                HostBlockMeta(
                    hi.request_id,
                    hb.status,
                    hb.resolved_path,
                    hb.text_digest,
                    hb.size_bytes,
                    hb.tokens_estimate,
                    (),
                )
            )
        facts = HostFacts(frozenset(), (), False, {"repo": COMMIT_1})
        fin = context.finalize(draft, blocks, facts, self.estimator)
        with self.uow() as uow:
            repo = uow.repo(ContextRepository)
            st_draft = repo.get(draft.manifest_id, for_update=True)
            vf, hrows = verify_finalization(
                st_draft,
                draft_digest=draft.draft_digest,
                estimator_id=self.estimator.estimator_id,
                host_meta=metas,
                facts_meta=host_facts_to_meta(facts),
                claimed_selection=fin.selection,
                rendered_prompt_digest=fin.prompt_digest,
                artifact_prompt_digest=fin.prompt_digest,
                prompt_file_version_id=self.fv1,
                finalized_at=self.clock.now(),
            )
            repo.finalize(vf, host_rows=hrows)
            uow.commit()
        return draft.manifest_id


def isolate_synthetic_prepare_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The hand-seeded preparation cases have no provisioned provider installation."""
    from skm.modules.execution.application import _stage_agent_helpers

    monkeypatch.setattr(_stage_agent_helpers, "first_agent_after_prepare", lambda *args: None)


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def exec_side(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ExecSide]:
    isolate_synthetic_prepare_routing(monkeypatch)
    backend = str(request.param)
    db = (
        cast("TestDatabase", request.getfixturevalue("clean_test_database"))
        if backend == "postgres"
        else None
    )
    dsn = db.dsn if db is not None else None
    yield from make_exec_side(backend, tmp_path, dsn=dsn)


def make_exec_side(backend: str, tmp_path: Path, *, dsn: str | None = None) -> Iterator[ExecSide]:
    clock = FrozenClock(SystemClock().now() if dsn else NOW)
    builtin = MutableBuiltinPacks(core_pack("1.0.0"))
    estimator = HeuristicTokenEstimator()
    env = {"SKM_DATABASE_URL": dsn} if dsn else {}
    bs = replace(
        load_bootstrap(None, {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}, tmp_path),
        instance_id=SEED.instance_id,
        database_application_name="skm-execution-contracts",
        database_pool_min_size=0,
        database_pool_max_size=4,
        database_pool_timeout_seconds=2,
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        instance_id=SEED.instance_id,
        repositories={SchemaVersionReader: lambda _: History()} if backend == "memory" else {},
        gateways=GatewayTable(
            {TokenEstimator: estimator, BuiltinPacks: builtin, TokenPepperSource: _FixedPepper()},
            "control_plane_gateway",
        ),
    )
    app = build_app(
        bs,
        surface=Surface.CLI,
        environ=env,
        invocation={},
        backend="postgres" if backend == "postgres" else None,
        overrides=ov,
    )
    try:
        owner = seed_principals(
            app,
            backend,
            people=((OWNER_ID, PrincipalKind.HUMAN, "owner"), (VIEWER_ID, PrincipalKind.HUMAN, "viewer")),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        viewer = Actor(VIEWER_ID, PrincipalKind.HUMAN, "viewer")
        client = app.client(actor=owner, surface=Surface.CLI)
        dispatch_new(client, SyncBuiltinPacks())
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        with app.uow_factory(RequestMeta("req_" + "7" * 26, Surface.CLI, None, NOW)) as uow:
            uow.repo(MembershipRepository).upsert(Membership(ScopeId(ws), VIEWER_ID, Role.VIEWER, None, NOW))
            uow.commit()
        viewer_client = app.client(actor=viewer, surface=Surface.CLI)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        r_dto = RegisterRepository(ws, "SKM", "https://example.invalid/skm.git", None)
        repo_id = RepositoryId(dispatch_new(client, r_dto).repository_id)
        dispatch_new(client, AttachRepository(proj, repo_id, mount_name="repo", role="primary"))

        ws2 = WorkspaceId(
            dispatch_new(client, CreateWorkspace(slug="secret-ws", title="Secret WS")).workspace_id
        )
        proj2 = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws2, slug="sec", title="Sec")).project_id
        )
        repo2 = RepositoryId(
            dispatch_new(
                client, RegisterRepository(ws2, "Sec", "https://example.invalid/sec.git", None)
            ).repository_id
        )
        dispatch_new(client, AttachRepository(proj2, repo2, mount_name="repo", role="primary"))
        fv_ws2_st = client.upload_blob(ws2, [b"sec\n"], size=4, media_type="text/markdown")
        fv_ws2 = FileVersionId(
            UUID(str(dispatch_new(client, add_file_dto(ws2, proj2, fv_ws2_st)).file_version_id))
        )
        plan2_ws2 = PlanId(dispatch_new(client, CreatePlan(project_id=proj2, title="Secret Plan")).plan_id)
        rev_ws2 = _publish_revision(
            app, client, owner, clock, plan2_ws2, _other_plan_spec(fv_ws2, plan2_ws2), "empty"
        )

        plat = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        host1 = HostId(dispatch_new(client, RegisterHost(name="host-1", platform=plat)).host_id)
        host2 = HostId(dispatch_new(client, RegisterHost(name="host-2", platform=plat)).host_id)
        wcaps = ws_docs.WorkerCapabilities(
            runtimes=("codex_cli",),
            isolation_profiles=("landlock",),
            max_concurrency=4,
            labels=("linux",),
            platform=ws_docs.WorkerCapabilitiesDefsHostPlatform(
                os=ws_docs.HostOs.LINUX, arch=ws_docs.HostArch.X86_64
            ),
            skm_version="2.0.0",
        )
        w1_res = cast("Any", client.dispatch(RegisterWorker(ws, host1, "w1", wcaps)))
        w2_res = cast("Any", client.dispatch(RegisterWorker(ws, host2, "w2", wcaps)))
        with app.uow_factory(RequestMeta("req_" + "6" * 26, Surface.CLI, None, NOW)) as uow:
            w1_actor = authenticate_token(uow, w1_res.token_secret, pepper=PEPPER, now=NOW)
            cfg = app.config.effective(
                uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.WORKSPACE, ScopeId(ws))
            )
            wf_rv = ResourceVersionId(
                extensions.resolve_resource(
                    uow, ResourceKind.AGENT_PROFILE, "executor", config=cfg
                ).resource_version_id
            )
            uow.commit()
        worker1_client = app.client(actor=w1_actor, surface=Surface.WORKER)

        st1 = client.upload_blob(ws, [b"Artifact 1\n"], size=11, media_type="text/markdown")
        st2 = client.upload_blob(ws, [b"Artifact 2\n"], size=11, media_type="text/markdown")
        fv1 = FileVersionId(UUID(str(dispatch_new(client, add_file_dto(ws, proj, st1)).file_version_id)))
        fv2 = FileVersionId(UUID(str(dispatch_new(client, add_file_dto(ws, proj, st2)).file_version_id)))

        plan1 = PlanId(dispatch_new(client, CreatePlan(project_id=proj, title="Exec Plan 1")).plan_id)
        rev1 = _publish_revision(app, client, owner, clock, plan1, _spec_doc(fv1), "empty")
        clock.advance(timedelta(seconds=5))
        rev2 = _publish_revision(
            app, client, owner, clock, plan1, {"goal": "Verify Exec Plan 1 v2"}, "current"
        )
        plan2 = PlanId(dispatch_new(client, CreatePlan(project_id=proj, title="Exec Plan 2")).plan_id)
        rev_p2 = _publish_revision(app, client, owner, clock, plan2, _other_plan_spec(fv1, plan2), "empty")

        if dsn:
            # Revision timestamps advance the fixture clock. SQL claim admission samples its own clock.
            clock.set(SystemClock().now())

        yield ExecSide(
            kind=backend,
            app=app,
            clock=clock,
            owner=owner,
            viewer=viewer,
            client=client,
            viewer_client=viewer_client,
            worker1_client=worker1_client,
            ws=ws,
            proj=proj,
            repo_id=repo_id,
            ws2=ws2,
            proj2=proj2,
            plan2_ws2=plan2_ws2,
            rev_ws2=rev_ws2,
            host1=host1,
            host2=host2,
            worker1=WorkerId(w1_res.worker_id),
            worker2=WorkerId(w2_res.worker_id),
            plan1=plan1,
            rev1=rev1,
            rev2=rev2,
            plan2=plan2,
            rev_p2=rev_p2,
            fv1=fv1,
            fv2=fv2,
            workflow_rv_id=wf_rv,
            estimator=estimator,
            dsn=dsn,
            ids=SequentialIds(start=5000),
        )
    finally:
        app.close()
