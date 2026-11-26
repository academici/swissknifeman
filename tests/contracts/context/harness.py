"""Dual-backend harness (memory + PostgreSQL) for context contract tests (P09.04.a)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.extensions.harness import CATALOG_TOML, pack_payload
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    add_file_dto,
    dispatch_new,
    seed_principals,
)
from skm.application_bus.client import SkmClient
from skm.application_bus.context import CommandContext
from skm.bootstrap.composition import App, CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import (
    EntityId,
    FileVersionId,
    PlanId,
    ProjectId,
    ResourceVersionId,
    RevisionId,
    ScopeId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.context.domain.request import (
    ContextRequest,
    ExecutionBlocks,
    PermissionsSummary,
    RunParams,
    RuntimeTarget,
    StepPurpose,
)
from skm.modules.extensions import public as extensions
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.pack import PackPins
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.planning.application.publication_candidate import prepare
from skm.modules.planning.domain.draft import DraftId
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.commands import CreatePlan, OpenDraft, PublishRevision, SaveDraft
from skm.modules.planning.ports import DraftRepository, PlanRepository
from skm.modules.workspace.public import (
    AttachRepository,
    CreateProject,
    CreateWorkspace,
    RegisterRepository,
)
from skm.platform.config import EffectiveConfig
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.tokens.heuristic import HeuristicTokenEstimator
from support.pg import TestDatabase
from support.seed import SEED

__all__ = [
    "NOW",
    "UNIT_ID",
    "ContextSide",
    "MutableBuiltinPacks",
    "core_pack",
    "ctx_side",
    "default_work_policy",
]

NOW = datetime(2026, 11, 15, 7, 0, tzinfo=UTC)
PHASE_ID = "01900000-0000-7000-8000-000000000901"
ITEM_ID = "01900000-0000-7000-8000-000000000902"
UNIT_UUID = UUID("01900000-0000-7000-8000-000000000903")
UNIT_ID = EntityId(UNIT_UUID)
REQ_ID = "01900000-0000-7000-8000-000000000904"
CRIT_ID = "01900000-0000-7000-8000-000000000905"
CHK_ID = "01900000-0000-7000-8000-000000000906"
DEC_ID = "01900000-0000-7000-8000-000000000907"
MAT_FV_ENTITY_ID = "01900000-0000-7000-8000-000000000908"
MAT_REPO_ENTITY_ID = "01900000-0000-7000-8000-000000000909"


class MutableBuiltinPacks:
    def __init__(self, *payloads: PackPayload) -> None:
        self.current = tuple(payloads)

    def payloads(self) -> tuple[PackPayload, ...]:
        return self.current


def _profile_toml(role: str, version: str = "1.0.0") -> str:
    return f"""
schema = "urn:skm:extensions:agent-profile:v1"
key = "{role}"
version = "{version}"
role = "{role}"
title = "{role.title()}"
description = "Implements or audits one unit."
result_schema = "urn:skm:execution:role-result:{role}:v1"
llm = true

[routing]
model_class = "implementation"
effort = "high"
required_capabilities = []
optional_capabilities = []

[isolation]
profile = "worktree"

[permissions]
policy_profile = "workspace-contained"

[prompt]
system_constraints = ["shared/system"]
role_contract = ["executor/role"]
result_contract = ["executor/result"]

[context]
include = []
inherit_user_global = false
repo_instructions = "full"
repo_instruction_sections = []
skills_mode = "auto"
skills_include = []
skills_exclude = []
history_max_steps = 3
memory_top_k = 0
include_optional_materials = true

[limits]
timeout_seconds = 3600
idle_timeout_seconds = 600
max_result_retries = 2
"""


def _pblock(block_type: str, variables: tuple[str, ...], body: str) -> str:
    vars_toml = ", ".join(f'"{v}"' for v in variables)
    return (
        f'+++\nschema = "urn:skm:extensions:prompt-block:v1"\n'
        f'block_type = "{block_type}"\nvariables = [{vars_toml}]\n+++\n{body}'
    )


def core_pack(version: str = "1.0.0", *, system_body: str = "Obey core v1 invariants.") -> PackPayload:
    files = {
        "prompts/shared/system.md": system_body,
        "prompts/shared/block_wrapper.md": _pblock(
            "system_constraints",
            ("block.title", "block.content"),
            "## {{ block.title }}\n\n{{ block.content }}",
        ),
        "prompts/shared/work_policy.md": _pblock(
            "task_contract",
            (
                "role.intensity",
                "run.verification_intensity",
                "role.warn_seconds",
                "role.emergency_wall_seconds",
            ),
            "Intensity: {{ role.intensity }} / verification: {{ run.verification_intensity }}. "
            "Soft overrun at {{ role.warn_seconds }}s is an advisory soft warning, not a hard cutoff — "
            "continue authorized work until {{ role.emergency_wall_seconds }}s.",
        ),
        "prompts/executor/role.md": _pblock(
            "role_contract", ("task.key",), "Act as executor for {{ task.key }}."
        ),
        "prompts/executor/result.md": "Emit JSON conforming to executor schema.",
        "agent-profiles/executor.toml": _profile_toml("executor", version),
        "agent-profiles/advisor.toml": _profile_toml("advisor", version),
        "runtimes/models.toml": CATALOG_TOML.format(version=version),
    }
    return pack_payload("core", version, files=files)


def default_work_policy(
    *,
    intensity: str = "medium",
    verification_intensity: str = "medium",
    warn_seconds: int = 900,
    emergency_wall_seconds: int = 3600,
) -> JsonObject:
    return {
        "intensity": intensity,
        "verification_intensity": verification_intensity,
        "warn_seconds": warn_seconds,
        "emergency_wall_seconds": emergency_wall_seconds,
    }


def _spec_doc(mat_fv_id: FileVersionId) -> JsonObject:
    return {
        "schema": SPECIFICATION_URN,
        "title": "Context Protocol Plan",
        "goal": "Verify Phase-A/B/C context assembly and persistence.",
        "rules": ["Keep domain pure."],
        "materials": [
            {
                "id": MAT_FV_ENTITY_ID,
                "key": "guide-doc",
                "title": "Implementation Guide",
                "kind": "file_version",
                "file_version_id": str(mat_fv_id),
                "role": "input",
                "required_for": ["execution"],
                "freshness": {"policy": "pinned"},
                "applies_to": ["P1.1/U1"],
            },
            {
                "id": MAT_REPO_ENTITY_ID,
                "key": "target-mod",
                "title": "Target Module",
                "kind": "repository_path",
                "mount": "repo",
                "path": "src/target.py",
                "role": "reference",
                "freshness": {"policy": "pinned"},
                "applies_to": ["P1.1/U1"],
            },
        ],
        "requirements": [
            {
                "id": REQ_ID,
                "key": "R1",
                "statement": "Context manifests are immutable after finalization.",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": ["P1.1"],
            }
        ],
        "decisions": [
            {
                "id": DEC_ID,
                "key": "D1",
                "title": "Two-phase manifest lifecycle",
                "state": "accepted",
                "question": "How to persist context?",
                "decision": "Draft row then single final transition.",
                "rationale": "Auditability without host IO in domain.",
                "applies_to": ["P1.1"],
            }
        ],
        "phases": [
            {
                "id": PHASE_ID,
                "key": "P1",
                "title": "Phase 1",
                "goal": "Context protocol",
                "design_state": "skeleton",
            }
        ],
        "items": [
            {
                "id": ITEM_ID,
                "key": "P1.1",
                "phase": "P1",
                "title": "Context protocol item",
                "summary": "Build draft/final context protocol.",
                "why": "Deterministic prompt provenance.",
                "implements": ["R1"],
                "decisions": ["D1"],
                "review": {"mode": "self", "reason": "contract harness"},
            }
        ],
        "units": [
            {
                "id": str(UNIT_UUID),
                "key": "P1.1/U1",
                "title": "Assemble and finalize context",
                "goal": "Execute Phase-A/B/C protocol.",
                "unit_kind": "implementation",
                "work_kind": "code",
                "mode": "either",
                "write_scope": [{"mount": "repo", "pattern": "src/**"}],
                "checks": ["V1"],
                "implements": ["R1"],
            }
        ],
        "checks": [
            {
                "id": CHK_ID,
                "key": "V1",
                "owner": "P1.1",
                "title": "Unit check",
                "kind": "manual",
                "category": "acceptance",
                "required": True,
                "definition": {
                    "instructions_md": "Verify manifest parity.",
                    "actor_role": "owner",
                    "allowed_verdicts": ["pass", "fail"],
                },
            }
        ],
        "criteria": [
            {
                "id": CRIT_ID,
                "key": "AC1",
                "owner": "P1.1",
                "statement": "Draft finalizes once and reproduces identically under pack pins.",
                "verification_mode": "manual",
                "checks": ["P1.1:V1"],
                "requirements": ["R1"],
            }
        ],
        "execution_constraints": {"strategy": "dag"},
    }


@dataclass
class ContextSide:
    kind: str
    app: App
    clock: FrozenClock
    owner: Actor
    client: SkmClient
    ws: WorkspaceId
    proj: ProjectId
    plan_id: PlanId
    rev_id: RevisionId
    run_scope_id: ScopeId
    mat_fv_id: FileVersionId
    prompt_fv_id: FileVersionId
    builtin: MutableBuiltinPacks
    estimator: HeuristicTokenEstimator
    dsn: str | None
    seq: int = 100

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        self.seq += 1
        meta = RequestMeta(f"req_{self.seq:026d}", Surface.CLI, None, self.clock.now())
        return self.app.uow_factory(meta, readonly=readonly)

    def effective_config(self, uow: UnitOfWork) -> EffectiveConfig:
        return self.app.config.effective(
            uow.repo(ConfigStore),
            uow.repo(ScopeTree),
            ScopeRef(ScopeKind.RUN, self.run_scope_id),
        )

    def upload_text(self, text: str, *, filename: str = "prompt.md") -> FileVersionId:
        raw = text.encode("utf-8")
        staged = self.client.upload_blob(self.ws, [raw], size=len(raw), media_type="text/markdown")
        res = dispatch_new(
            self.client,
            replace(add_file_dto(self.ws, self.proj, staged), title=filename, original_filename=filename),
        )
        return FileVersionId(UUID(str(res.file_version_id)))

    def make_request(
        self,
        uow: UnitOfWork,
        *,
        config: EffectiveConfig,
        step_ref: str = "run:1/step:1",
        work_policy: JsonObject | None = None,
        pack_pins: PackPins | None = None,
        entity_id: EntityId | None = UNIT_ID,
        role: str = "executor",
        stage_id: str = "execute",
    ) -> ContextRequest:
        resolved = extensions.resolve_resource(
            uow, ResourceKind.AGENT_PROFILE, role, config=config, pins=pack_pins
        )
        raw_pins = (
            {str(slug): UUID(str(vid)) for slug, vid in pack_pins.items()} if pack_pins is not None else None
        )
        return ContextRequest(
            workspace_id=self.ws,
            project_id=self.proj,
            plan_id=self.plan_id,
            revision_id=self.rev_id,
            entity_id=entity_id,
            project_slug="skm",
            purpose=StepPurpose(role=role, stage_id=stage_id, step_ref=step_ref, attempt_no=1, round_no=1),
            agent_profile_version_id=ResourceVersionId(resolved.resource_version_id),
            runtime=RuntimeTarget(
                runtime_id="codex_cli",
                model="gpt-5",
                context_window_tokens=128000,
                capabilities=frozenset(),
                tools=frozenset(),
                notes=(),
                route_source="plan",
                operation="execute",
                config_mode="isolated",
                self_loads=(),
                degraded=frozenset(),
                self_loaded_instruction_files=("AGENTS.md",),
            ),
            permissions=PermissionsSummary(
                write_scope=("repo:src/**",),
                read_scope=("repo:**",),
                commands_allowed=("pytest",),
                commands_denied=(),
                network="none",
                network_allow=(),
                external_effects=(),
            ),
            run=RunParams(
                run_id="run_1",
                workflow_key="default",
                attempt_no=1,
                round_no=1,
                integration_branch=None,
                commit_policy="none",
                progress_format="json",
                output_language="en",
                rules_extra=(),
            ),
            execution_blocks=ExecutionBlocks(
                work_policy=default_work_policy() if work_policy is None else work_policy,
                decision_answers=(),
                review_feedback=None,
                previous_attempt=None,
                candidate=None,
                findings_under_review=(),
                context_map=None,
                research=(),
                history=(),
            ),
            resume=None,
            task_risk="medium",
            research_queries=(),
            pack_pins=raw_pins,
        )


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def ctx_side(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[ContextSide]:
    backend = str(request.param)
    db = (
        cast("TestDatabase", request.getfixturevalue("clean_test_database"))
        if backend == "postgres"
        else None
    )
    dsn = db.dsn if db is not None else None
    clock = FrozenClock(NOW)
    builtin = MutableBuiltinPacks(core_pack("1.0.0"))
    estimator = HeuristicTokenEstimator()
    env = {"SKM_DATABASE_URL": dsn} if dsn else {}
    bs_env = {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}
    bs = replace(
        load_bootstrap(None, bs_env, tmp_path),
        instance_id=SEED.instance_id,
        database_application_name="skm-context-contracts",
        database_pool_min_size=0,
        database_pool_max_size=4,
        database_pool_timeout_seconds=2,
    )
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        instance_id=SEED.instance_id,
        gateways=GatewayTable(
            {TokenEstimator: estimator, BuiltinPacks: builtin},
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
            people=((OWNER_ID, PrincipalKind.HUMAN, "owner"),),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=owner, surface=Surface.CLI)
        dispatch_new(client, SyncBuiltinPacks())
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        repo_id = dispatch_new(
            client,
            RegisterRepository(
                workspace_id=ws,
                title="SKM Repo",
                remote_url="https://example.invalid/skm.git",
                external_id=None,
            ),
        ).repository_id
        dispatch_new(
            client,
            AttachRepository(project_id=proj, repository_id=repo_id, mount_name="repo", role="primary"),
        )

        mat_raw = b"Guide line 1: keep domain pure.\nGuide line 2: verify finalization.\n"
        mat_staged = client.upload_blob(ws, [mat_raw], size=len(mat_raw), media_type="text/markdown")
        mat_res = dispatch_new(
            client,
            replace(add_file_dto(ws, proj, mat_staged), title="guide.md", original_filename="guide.md"),
        )
        mat_fv_id = FileVersionId(UUID(str(mat_res.file_version_id)))

        p_raw = b"initial prompt placeholder\n"
        p_staged = client.upload_blob(ws, [p_raw], size=len(p_raw), media_type="text/markdown")
        p_res = dispatch_new(
            client,
            replace(add_file_dto(ws, proj, p_staged), title="prompt0.md", original_filename="prompt0.md"),
        )
        prompt_fv_id = FileVersionId(UUID(str(p_res.file_version_id)))

        plan_id = PlanId(dispatch_new(client, CreatePlan(project_id=proj, title="Context Plan")).plan_id)
        draft_res = dispatch_new(client, OpenDraft(plan_id=plan_id, base="empty"))
        draft_id = DraftId(draft_res.draft_id)
        save_res = dispatch_new(
            client,
            SaveDraft(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=draft_res.edit_version,
                merge_patch=_spec_doc(mat_fv_id),
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
            candidate = prepare(uow, p_ctx, plan, p_draft)
            assert not candidate.has_errors, (candidate.report.findings, candidate.report.rule_failures)
            expected_digest = candidate.content_digest
            uow.rollback()
        pub_res = dispatch_new(
            client,
            PublishRevision(plan_id, draft_id, int(save_res.edit_version), expected_digest, reason="v1"),
        )
        rev_id = RevisionId(pub_res.revision_id)

        run_scope_id = ScopeId(UUID("01900000-0000-7000-8000-0000000009aa"))
        with app.uow_factory(RequestMeta("req_" + "7" * 26, Surface.CLI, None, NOW)) as uow:
            uow.repo(ScopeRegistry).create(
                run_scope_id, ScopeKind.RUN, parent=ScopeId(plan_id), workspace_id=ws
            )
            uow.commit()

        yield ContextSide(
            kind=backend,
            app=app,
            clock=clock,
            owner=owner,
            client=client,
            ws=ws,
            proj=proj,
            plan_id=plan_id,
            rev_id=rev_id,
            run_scope_id=run_scope_id,
            mat_fv_id=mat_fv_id,
            prompt_fv_id=prompt_fv_id,
            builtin=builtin,
            estimator=estimator,
            dsn=dsn,
        )
    finally:
        app.close()
