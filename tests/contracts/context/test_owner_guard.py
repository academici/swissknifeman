"""Atomic context admission, exact prompt bytes and live replay across both real backends."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, create_autospec
from uuid import UUID

import pytest

from contracts.context.harness import UNIT_ID, default_work_policy
from contracts.execution._worker_protocol_support import claim, make_case
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.seed_helpers import seed_stage, seed_step
from integration.artifacts.test_upload_flow import add_file_dto, dispatch_new
from skm.adapters.execution.context_owner import ExecutionContextOwnerGuard
from skm.bootstrap.composition import _control_plane_gateways
from skm.bootstrap.doctor import DoctorCheckCollector
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import FileVersionId, PrincipalId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.context import public as context
from skm.modules.context.application.commands.finalize_manifest import SPEC, FinalizeManifest
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.host_inputs import HostBlock, HostFacts, HostInputKind, HostReadStatus
from skm.modules.context.domain.manifest import ManifestState
from skm.modules.context.domain.render import format_host_block, render_block_text
from skm.modules.context.domain.request import (
    ContextRequest,
    ExecutionBlocks,
    PermissionsSummary,
    RunParams,
    RuntimeTarget,
    StepPurpose,
)
from skm.modules.context.generated.commands import finalize_manifest_from_json
from skm.modules.context.generated.results import finalize_manifest_result_to_json
from skm.modules.context.generated.settings import ContextSettings
from skm.modules.context.ports import ContextOwnerClaim, ContextOwnerGuard, ContextRepository, TextStore
from skm.modules.execution.domain.attempt import consume_stage
from skm.modules.execution.domain.stage_record import StageState
from skm.modules.execution.ports import AttemptRepository
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, ScopeTree


def upload_prompt(side: Any, text: str, *, workspace: Any = None, project: Any = None) -> str:
    raw = text.encode("utf-8")
    ws, proj = workspace or side.ws, project or side.proj
    staged = side.client.upload_blob(ws, [raw], size=len(raw), media_type="text/markdown")
    result = dispatch_new(side.client, replace(add_file_dto(ws, proj, staged), original_filename="prompt.md"))
    return str(result.file_version_id)


def admitted_config(config: EffectiveConfig, store_content: bool) -> EffectiveConfig:
    """Override only context storage at admission; all other settings use the real loader."""

    def section[T](view: type[T]) -> T:
        value = config.section(view)
        if isinstance(value, ContextSettings):
            return replace(value, store_host_block_content=store_content)
        return value

    admitted = Mock(spec=EffectiveConfig, wraps=config)
    admitted.section.side_effect = section
    return admitted


def owned_draft(side: Any, *, store_content: bool = True, runtime_id: str = "codex_cli") -> Any:
    run, task, attempt, assignment = make_case(side, stage_id="execute", stage_type="agent_step", env=True)
    claimed = claim(side)
    assert claimed.get("outcome") is None, claimed
    sid = side.new_id()
    with side.uow() as uow:
        cfg = side.app.config.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PLAN, ScopeId(side.plan1))
        )
        req = ContextRequest(
            workspace_id=side.ws,
            project_id=side.proj,
            plan_id=side.plan1,
            revision_id=side.rev1,
            entity_id=UNIT_ID,
            project_slug="skm",
            purpose=StepPurpose("executor", "execute", str(sid), 1, 1),
            agent_profile_version_id=side.workflow_rv_id,
            runtime=RuntimeTarget(
                runtime_id,
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
            ),
            permissions=PermissionsSummary(("repo:src/**",), ("repo:**",), ("pytest",), (), "none", (), ()),
            run=RunParams("run_1", "default", 1, 1, None, "none", "json", "en", ()),
            execution_blocks=ExecutionBlocks(default_work_policy(), (), None, None, None, (), None, (), ()),
            resume=None,
            task_risk="medium",
            research_queries=(),
            pack_pins=None,
        )
        draft = context.assemble_draft(
            uow, side.app.gateways, req, config=admitted_config(cfg, store_content), owner_ref=f"step:{sid}"
        )
        attempt, _ = consume_stage(attempt, continuation_id=attempt.continuation.continuation_id)
        uow.repo(AttemptRepository).save(
            attempt, expected_version=uow.repo(AttemptRepository).version(attempt.id)
        )
        stage = seed_stage(
            side, uow, attempt, state=StageState.CONTEXT_DRAFT, fencing_token=claimed["fencing_token"]
        )
        step = seed_step(
            side,
            uow,
            attempt,
            stage,
            manifest_id=draft.manifest_id,
            step_id=sid,
            admission={"min_class": "implementation"},
        )
        uow.commit()
    blocks = []
    for hi in draft.host_inputs:
        if hi.kind is HostInputKind.REPOSITORY_PATH:
            text = "x = 'Привет 🐍'\r\n"
            provisional = HostBlock(hi.request_id, HostReadStatus.OK, hi.path, text, None, None, None)
            bt, title, body, source = format_host_block(hi, provisional)
            wrapped = render_block_text(
                block_type=bt,
                title=title,
                content=body,
                source_ref=source,
                templates=draft.templates,
                prompt_plan=draft.prompt_plan,
                variables=draft.variables,
            )
            blocks.append(
                replace(
                    provisional,
                    text_digest=sha256_text(text),
                    size_bytes=len(text.encode()),
                    tokens_estimate=side.estimator.estimate(wrapped),
                )
            )
        else:
            status = HostReadStatus.SELF_LOADED if hi.path == "AGENTS.md" else HostReadStatus.MISSING
            blocks.append(
                HostBlock(
                    hi.request_id,
                    status,
                    hi.path if status is HostReadStatus.SELF_LOADED else None,
                    None,
                    None,
                    None,
                    None,
                )
            )
    facts = HostFacts(frozenset(), (), False, {})
    final = context.finalize(draft, blocks, facts, side.estimator)
    version = FileVersionId(UUID(upload_prompt(side, final.rendered_prompt)))
    wire = context.finalize_command(
        draft,
        final,
        blocks,
        facts,
        version,
        claim=ContextOwnerClaim(
            UUID(claimed["assignment_id"]), attempt.id, side.worker1, claimed["fencing_token"]
        ),
        store_content=store_content,
        runtime_self_loaded=(),
    )
    return SimpleNamespace(
        side=side,
        run=run,
        task=task,
        attempt=attempt,
        assignment=assignment,
        claimed=claimed,
        stage=stage,
        step=step,
        draft=draft,
        final=final,
        command=finalize_manifest_from_json(wire),
    )


def dispatch(case: Any, cmd: Any = None, *, client: Any = None, key: str | None = None) -> Any:
    return (client or case.side.worker1_client).dispatch(
        FinalizeManifest(**(cmd or case.command)),
        idempotency_key=key,
    )


def test_finalize_intrinsic_replay_and_durable_utf8_prompt(exec_side: Any) -> None:
    case = owned_draft(exec_side)
    observed = [{"kind": "instructions", "locator": "repo", "files": ["AGENTS.md"], "when": "startup"}]
    case.command["runtime_self_loaded"] = observed
    first = dispatch(case)
    assert dispatch(case) == first
    assert finalize_manifest_result_to_json(first) == first
    with exec_side.uow(readonly=True) as uow:
        saved = uow.repo(ContextRepository).get(case.draft.manifest_id)
        assert saved.state is ManifestState.FINAL
        assert saved.prompt_digest == sha256_text(case.final.rendered_prompt)
        assert saved.prompt_file_version_id == UUID(case.command["prompt_file_version_id"])
        assert saved.route["self_loads_observed"] == observed
        assert any(
            item["code"] == "RUNTIME_SELF_LOADS_MISMATCH" and item["message"] for item in saved.diagnostics
        )
        assert "render_snapshot" in saved.route
        assert "render_snapshot" not in case.draft.manifest.route
        for item in case.command["host_blocks"]:
            if "text" in item:
                assert (
                    uow.repo(TextStore).get_many((item["text_digest"],))[item["text_digest"]] == item["text"]
                )
    changed = deepcopy(case.command)
    changed["runtime_self_loaded"] = [
        {"kind": "instructions", "locator": "repo", "files": [], "when": "startup"}
    ]
    with pytest.raises(SkmError) as caught:
        dispatch(case, changed)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_external_idempotency_key_is_forbidden(exec_side: Any) -> None:
    case = owned_draft(exec_side)
    from skm.application_bus.registry import IdempotencyMode

    assert SPEC.idempotency is IdempotencyMode.FORBIDDEN
    with pytest.raises(SkmError) as caught:
        dispatch(case, key="must-not-create-receipt")
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["reason"] == "not_idempotent"


def test_bus_allows_run_control_alternative_but_keeps_additional_permissions_required(
    exec_side: Any,
    monkeypatch: Any,
) -> None:
    case = owned_draft(exec_side)
    operator = exec_side.restricted_client(("run.control",), scope_id=exec_side.proj, owner_token=True)
    reader = exec_side.viewer_client
    first = dispatch(case, client=operator)
    assert dispatch(case) == first  # The same body may replay under the worker's independent authority.
    with pytest.raises(SkmError) as caught:
        dispatch(case, client=reader)
    assert caught.value.code is ErrorCode.FORBIDDEN

    registry = exec_side.app.bus._registry
    stricter = replace(SPEC, permissions_of=lambda _cmd: ("run.read",))
    monkeypatch.setattr(exec_side.app.bus, "_registry", SimpleNamespace(command=lambda _dto: stricter))
    with pytest.raises(SkmError) as caught:
        dispatch(case, client=operator)
    assert caught.value.code is ErrorCode.FORBIDDEN
    monkeypatch.setattr(exec_side.app.bus, "_registry", registry)


def test_bus_rejects_unknown_permission_alternatives_at_bootstrap(exec_side: Any) -> None:
    from skm.application_bus.registry import BusRegistry, BusRegistryError
    from skm.modules.context.module import MODULE

    for alternatives in (("unregistered.permission",), ["run.control"], None):
        invalid = replace(SPEC, permission_alternatives=alternatives)
        with pytest.raises(BusRegistryError, match="permission_alternatives"):
            BusRegistry.build(
                (replace(MODULE, commands=(invalid,)),),
                schemas=exec_side.app.schemas,
                permission_catalog=frozenset({"worker.claim", "run.control"}),
                disabled_modules=frozenset(),
            )


def test_r16_live_settings_cannot_rewrite_admitted_draft_and_new_route_has_new_step(
    exec_side: Any,
    monkeypatch: Any,
) -> None:
    from skm.platform.config.effective import EffectiveConfig

    case = owned_draft(exec_side)
    original = EffectiveConfig.section

    def changed(self: Any, view: Any) -> Any:
        settings = original(self, view)
        if view is ContextSettings:
            return replace(settings, max_total_tokens=1000, output_language="de")
        return settings

    monkeypatch.setattr(EffectiveConfig, "section", changed)
    assert dispatch(case)["prompt_digest"] == case.final.prompt_digest
    with exec_side.uow(readonly=True) as uow:
        saved = uow.repo(ContextRepository).get(case.draft.manifest_id)
        assert saved.total_limit == case.draft.manifest.total_limit
        assert saved.draft_digest == case.draft.draft_digest
    new = owned_draft(exec_side, runtime_id="claude_code")
    assert new.step.id != case.step.id
    assert new.draft.manifest_id != case.draft.manifest_id
    assert new.draft.manifest.runtime_id == "claude_code"
    assert new.draft.manifest.total_limit == 1000


def test_manifest_binding_is_rechecked_after_execution_locks(exec_side: Any, monkeypatch: Any) -> None:
    case = owned_draft(exec_side)
    with exec_side.uow(readonly=True) as uow:
        cls = type(uow.repo(ContextRepository))
    original = cls.get
    for change in (
        {"owner_ref": f"step:{exec_side.new_id()}"},
        {"workspace_id": exec_side.ws2},
        {"project_id": exec_side.proj2},
    ):

        def changed(self: Any, identity: Any, *, for_update: bool = False, change: Any = change) -> Any:
            row = original(self, identity, for_update=for_update)
            return replace(row, **change) if for_update else row

        monkeypatch.setattr(cls, "get", changed)
        with pytest.raises(SkmError) as caught:
            dispatch(case)
        assert caught.value.code is ErrorCode.NOT_FOUND


def test_tampering_rolls_back_without_finalizing(exec_side: Any) -> None:
    case = owned_draft(exec_side)
    for field in (
        "draft_digest",
        "estimator_id",
        "selection",
        "unknown_host",
        "missing_host",
        "duplicate_host",
        "unavailable_host",
        "host_digest",
        "prompt_digest",
    ):
        cmd = deepcopy(case.command)
        expected = ErrorCode.CONTEXT_MANIFEST_TAMPERED
        if field == "selection":
            cmd["selection"]["total_tokens"] += 1
        elif field == "unknown_host":
            cmd["host_blocks"][0]["request_id"] = "hi:foreign"
        elif field == "missing_host":
            cmd["host_blocks"].pop()
        elif field == "duplicate_host":
            cmd["host_blocks"].append(cmd["host_blocks"][0])
        elif field == "unavailable_host":
            item = next(b for b in cmd["host_blocks"] if b["status"] == "ok")
            item.update(status="missing", text_digest=None, size_bytes=None, tokens_estimate=None)
            item.pop("text")
        elif field == "host_digest":
            next(b for b in cmd["host_blocks"] if b["status"] == "ok")["text"] += "!"
            expected = ErrorCode.BLOB_DIGEST_MISMATCH
        elif field == "prompt_digest":
            cmd["rendered_prompt_digest"] = "sha256:" + "0" * 64
            expected = ErrorCode.BLOB_DIGEST_MISMATCH
        else:
            cmd[field] = "sha256:" + "0" * 64 if field == "draft_digest" else "forged-estimator"
        with pytest.raises(SkmError) as caught:
            dispatch(case, cmd)
        assert caught.value.code is expected
        with exec_side.uow(readonly=True) as uow:
            assert uow.repo(ContextRepository).get(case.draft.manifest_id).state is ManifestState.DRAFT


def test_required_host_input_refuses_missing_status_before_selection() -> None:
    from skm.modules.context.application.commands.finalize_manifest import _host_inputs
    from unit.context.domain.test_explain_diff import manifest
    from unit.context.host.test_collect_host_blocks import request

    value = replace(manifest(), host_inputs=(request(request_id="hi:required", required=True),))
    cmd = FinalizeManifest(host_blocks=[{"request_id": "hi:required", "status": "missing"}])
    with pytest.raises(SkmError) as caught:
        _host_inputs(cmd, value)
    assert caught.value.code is ErrorCode.CONTEXT_INPUT_MISSING


def test_execution_locks_precede_manifest_lock_in_same_uow(exec_side: Any, monkeypatch: Any) -> None:
    case = owned_draft(exec_side)
    from skm.modules.execution.ports import AssignmentRepository, RunRepository, TaskRepository

    with exec_side.uow(readonly=True) as uow:
        ports = (RunRepository, TaskRepository, AttemptRepository, AssignmentRepository, ContextRepository)
        types = {port: type(uow.repo(port)) for port in ports}
    calls = []
    for port, cls in types.items():
        original = cls.get

        def observed(
            self: Any, identity: Any, *, for_update: bool = False, original: Any = original, port: Any = port
        ) -> Any:
            if for_update:
                calls.append(port)
            return original(self, identity, for_update=for_update)

        monkeypatch.setattr(cls, "get", observed)
    dispatch(case)
    assert calls.index(RunRepository) < calls.index(TaskRepository) < calls.index(AttemptRepository)
    assert calls.index(AttemptRepository) < calls.index(AssignmentRepository) < calls.index(ContextRepository)


def test_adapter_maps_every_primitive_without_opening_or_committing_uow(monkeypatch: Any) -> None:
    from datetime import UTC, datetime

    from skm.modules.execution import public as execution

    calls = []
    monkeypatch.setattr(execution, "require_current_context_owner", lambda *a, **kw: calls.append((a, kw)))
    claim = ContextOwnerClaim(UUID(int=1), UUID(int=2), UUID(int=3), 4)
    uow = create_autospec(UnitOfWork, instance=True)
    actor = Actor(PrincipalId(UUID(int=5)), PrincipalKind.HUMAN, "test owner")
    now = datetime(2026, 11, 16, tzinfo=UTC)
    ExecutionContextOwnerGuard().require_current(uow, actor, "step:owner", claim, now)
    assert not uow.mock_calls
    assert calls == [
        (
            (uow, actor, "step:owner"),
            {
                "assignment_id": claim.assignment_id,
                "attempt_id": claim.attempt_id,
                "worker_id": claim.worker_id,
                "fencing_token": 4,
                "now": now,
            },
        )
    ]


def test_bootstrap_requires_context_owner_guard() -> None:
    supplied = GatewayTable({ContextOwnerGuard: None}, "control_plane_gateway")
    config = create_autospec(ConfigLoader, instance=True)
    doctor = create_autospec(DoctorCheckCollector, instance=True)
    with pytest.raises(SkmError) as caught:
        _control_plane_gateways(config, doctor, supplied, pepper=b"production-pepper")
    assert caught.value.code is ErrorCode.CONFIG_INVALID
    assert "ContextOwnerGuard" in str(caught.value)


@pytest.mark.parametrize("token", [0, -1, True])
def test_context_claim_requires_positive_integer_token(token: int) -> None:
    with pytest.raises(SkmError) as caught:
        ContextOwnerClaim(UUID(int=1), UUID(int=2), UUID(int=3), token)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
