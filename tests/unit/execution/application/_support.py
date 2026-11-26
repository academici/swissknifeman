"""Real memory UoW/bus with deterministic execution facts and pinned test resources."""

from __future__ import annotations

import contextlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from contracts.context.harness import MutableBuiltinPacks, _profile_toml, core_pack
from contracts.execution.harness import isolate_synthetic_prepare_routing, make_exec_side
from contracts.execution.seed_helpers import (
    seed_attempt,
    seed_bundle,
)
from contracts.execution.seed_helpers import (
    seed_output as seed_output,
)
from contracts.execution.seed_helpers import (
    seed_stage as seed_stage,
)
from contracts.execution.seed_helpers import (
    seed_step as seed_step,
)
from contracts.execution.seed_helpers import (
    seed_task as seed_task,
)
from contracts.extensions.harness import pack_payload
from skm.application_bus.context import CommandContext
from skm.kernel.ids import ResourceVersionId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.execution.application._control import current_binding_digest
from skm.modules.execution.application._start_inputs import prospective_config
from skm.modules.execution.domain.attempt import AttemptState, ContinuationCause, SelectedStage, select_stage
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.task import TaskStatus
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.ports import (
    AttemptRepository,
    RunRepository,
    TaskRepository,
)
from skm.modules.extensions import public as extensions
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.extensions.ports import BuiltinPacks
from skm.platform.config.store import ConfigStore, ScopeTree

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="session")
def _shared_side(tmp_path_factory: Any):
    from contracts.execution._worker_protocol_support import _fixture_catalog

    tmp_path = tmp_path_factory.mktemp("p0705b")
    generator = make_exec_side("memory", tmp_path)
    current = next(generator)
    payload = core_pack("1.1.0")
    files = {f.path: f.content.decode() for f in payload.files}
    files["runtimes/models.toml"] = _fixture_catalog()
    workflow = (ROOT / "tests/fixtures/corpus/examples/execution/workflows/quick-fix.toml").read_text()
    files["workflows/reviewed-development.toml"] = workflow.replace(
        'id = "quick-fix"', 'id = "reviewed-development"'
    )
    files["workflows/default.toml"] = workflow
    files["agent-profiles/plan-auditor.toml"] = _profile_toml("advisor", "1.1.0").replace(
        'key = "advisor"', 'key = "plan-auditor"'
    )
    for role in ("reviewer", "triager", "registrar"):
        files[f"agent-profiles/{role}.toml"] = _profile_toml(role, "1.1.0")
    files["workflows/plan-audit.toml"] = """schema = "urn:skm:execution:workflow:v1"
id = "plan-audit"
version = "1.0.0"
applies_to = ["code"]
requires_roles = ["advisor"]
[[stage]]
id = "prepare"
type = "prepare_environment"
for_kinds = ["plan_audit"]
[[stage]]
id = "audit"
type = "advisor_consult"
for_kinds = ["plan_audit"]
[stage.params]
profile = "plan-auditor"
"""
    builtin = current.app.gateways.get(BuiltinPacks)
    assert isinstance(builtin, MutableBuiltinPacks)
    builtin.current = (pack_payload("core", "1.1.0", files=files),)
    current.client.dispatch(SyncBuiltinPacks())
    from contracts.execution.harness import _publish_revision
    from skm.modules.planning import public as planning

    with current.uow(readonly=True) as uow:
        spec = planning.get_revision_specification(uow, current.rev2)
        from skm.modules.planning.domain.specification import to_document

        doc = to_document(spec)
        phases = cast("list[JsonObject]", doc["phases"])
        items = cast("list[JsonObject]", doc["items"])
    for phase in phases:
        phase["design_state"] = "detailed"
    for item in items:
        item["scope"] = {"include": ["repo:src/**"], "exclude": []}
        item["deliverables"] = ["A reproducible context manifest"]
        item["reads"] = [
            {"kind": "material", "ref": "material/guide-doc", "why": "Input contract", "required": True}
        ]
    current.rev2 = _publish_revision(
        current.app,
        current.client,
        current.owner,
        current.clock,
        current.plan1,
        {"phases": doc["phases"], "items": doc["items"]},
        "current",
    )
    try:
        yield current
    finally:
        with contextlib.suppress(StopIteration):
            next(generator)


@pytest.fixture
def side(_shared_side: Any, monkeypatch: pytest.MonkeyPatch):
    from copy import deepcopy

    current = _shared_side
    backend = current.app.uow_factory._backend
    saved = deepcopy(backend.committed)
    original_time = current.clock.now()
    builtin = current.app.gateways.get(BuiltinPacks)
    original_packs = builtin.current
    # Readiness checks existence/capability routing without invoking a provider. This
    # boundary fake models an admitted catalog route; lifecycle/SQL/bus remain real.
    from skm.modules.execution.application import _start_inputs

    isolate_synthetic_prepare_routing(monkeypatch)

    def route(_uow, _gateways, req, *, config, pins):
        assert pins
        assert req.host_id is None
        return SimpleNamespace(runtime_id="fake", model="fake", catalog_digest="sha256:" + "1" * 64)

    monkeypatch.setattr(_start_inputs, "route_role", route)
    try:
        yield current
    finally:
        backend.committed = saved
        builtin.current = original_packs
        current.app.config.clear_cache()
        current.clock.advance(original_time - current.clock.now())


def context(side: Any, uow: Any, run: Any = None, *, overrides: Any = None, actor: Any = None) -> Any:
    scope = ScopeRef(
        ScopeKind.PLAN if run is None else ScopeKind.RUN, ScopeId(side.plan1 if run is None else run.id)
    )
    config = side.app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope)
    if overrides:
        config = prospective_config(config, overrides, parent_id=side.plan1)
    return CommandContext(
        actor or side.owner,
        RequestMeta("req_" + "e" * 26, Surface.TEST, None, side.clock.now()),
        scope,
        uow.repo(ScopeRegistry).ancestors(scope.id),
        side.clock,
        side.ids,
        cast("Any", object()),
        config,
        cast("Any", SimpleNamespace(info=lambda *a, **kw: None)),
        side.app.gateways,
    )


def seeded(
    side: Any,
    *,
    run_status: Any = None,
    task_status: Any = TaskStatus.EXECUTING,
    attempt_state: Any = AttemptState.RUNNING,
    cursor: bool = False,
    attempt_no: int = 1,
) -> tuple[Any, Any, Any]:
    from skm.modules.execution.domain.run import RunStatus

    with side.uow() as uow:
        from skm.modules.execution.domain.review_grouping import ReviewGrouping
        from skm.modules.execution.domain.run import Run, RunKind

        cfg = context(side, uow).config
        wf = extensions.resolve_resource(
            uow, extensions.ResourceKind.WORKFLOW, "reviewed-development", config=cfg
        )
        rid = side.new_id()
        uow.repo(ScopeRegistry).create(
            ScopeId(rid), ScopeKind.RUN, parent=ScopeId(side.plan1), workspace_id=side.ws
        )
        status = run_status or RunStatus.RUNNING
        run = Run(
            rid,
            side.ws,
            side.proj,
            RunKind.PLAN,
            side.plan1,
            side.rev1,
            1,
            status,
            side.owner.principal_id,
            None,
            None,
            None,
            1,
            ResourceVersionId(wf.resource_version_id),
            ReviewGrouping("none", (), "medium", "off"),
            False,
            False,
            "owner" if status is RunStatus.PAUSED else None,
            "owner" if status is RunStatus.PAUSED else None,
            None,
            None,
            1,
            side.clock.now(),
            side.clock.now(),
            None,
        )
        uow.repo(RunRepository).add(run)
        run_cfg = context(side, uow, run).config
        seed_bundle(side, uow, run.id, config_snapshot=run_cfg.freeze(run_cfg.registry).to_document())
        task = seed_task(side, uow, run.id, status=task_status)
        attempt = seed_attempt(side, uow, run.id, task.id, state=attempt_state, attempt_no=attempt_no)
        task = replace(
            task, current_attempt_id=attempt.id, attempt_count=attempt_no, row_version=task.row_version + 1
        )
        uow.repo(TaskRepository).save(task, expected_version=1)
        if cursor:
            stage = SelectedStage(
                "execute", "agent_step", StageMode.NORMAL, 1, {}, None, None, FeedbackRefs(), None, None
            )
            attempt = select_stage(
                attempt,
                cause=ContinuationCause("run_start", "A1"),
                stage=stage,
                continuation_id=side.new_id(),
            )
            uow.repo(AttemptRepository).save(attempt, expected_version=1)
        uow.commit()
    return run, task, attempt


def manual_case(side: Any, *, status: Any = TaskStatus.MANUAL_PENDING):
    from skm.modules.execution.domain.check_execution import CheckExecution, CheckKind, CheckState
    from skm.modules.execution.domain.run import RunStatus
    from skm.modules.execution.ports import CheckRepository
    from skm.modules.planning import public as planning

    run, task, attempt = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        output = seed_output(side, uow, attempt)
        attempt = replace(attempt, current_output_id=output.id)
        uow.repo(AttemptRepository).save(
            attempt, expected_version=uow.repo(AttemptRepository).version(attempt.id)
        )
        spec = planning.get_revision_specification(uow, run.revision_id)
        cid = side.new_id()
        check = CheckExecution(
            cid,
            side.ws,
            run.id,
            task.id,
            attempt.id,
            output.id,
            spec.checks[0].id,
            "P1.1:V1",
            CheckKind.MANUAL,
            True,
            CheckState.MANUAL_PENDING,
            None,
            "",
            None,
            None,
            "sha256:" + "1" * 64,
            None,
            None,
            1,
        )
        uow.repo(CheckRepository).add_many((check,))
        reason = blocking_reason(
            BlockingCode.WAITING_MANUAL_CHECK,
            task_id=task.id,
            refs={"check_execution_id": str(cid), "check_key": check.check_key},
            now=side.clock.now(),
            message="manual wait",
        )
        new = replace(
            task,
            status=status,
            blocking_reason=reason if status is TaskStatus.MANUAL_PENDING else None,
            row_version=task.row_version + 1,
        )
        uow.repo(TaskRepository).save(new, expected_version=task.row_version)
        uow.commit()
    return run, new, attempt, check


def decision_case(side: Any, *, status: Any = TaskStatus.AWAITING_DECISION, code: str | None = None):
    from skm.modules.execution.domain.decision_record import QuestionCategory
    from skm.modules.execution.domain.decision_request import (
        Audience,
        DecisionKind,
        DecisionRequest,
        DecisionState,
        question_digest,
        question_key,
    )
    from skm.modules.execution.domain.run import RunStatus
    from skm.modules.execution.ports import DecisionRepository

    run, task, attempt = seeded(side, run_status=RunStatus.PAUSED)
    with side.uow() as uow:
        rid = side.new_id()
        payload = {"kind": "decision", "text": "Continue?", "options": [{"id": "continue"}]}
        if code is not None:
            payload = {"code": code, "options": ["resume_run", "fail"]}
        request = DecisionRequest(
            rid,
            side.ws,
            run.id,
            task.id,
            DecisionKind.QUESTION if code is None else DecisionKind.ESCALATION,
            Audience.OWNER,
            QuestionCategory.ARCHITECTURAL if code is None else None,
            frozenset(),
            question_key(task.display_key, payload) if code is None else None,
            question_digest(task.display_key, payload) if code is None else None,
            1,
            payload,
            None,
            {"attempt_id": str(attempt.id), "input_part_digest": current_binding_digest(uow, attempt)},
            DecisionState.OPEN,
            None,
            None,
            side.clock.now(),
        )
        uow.repo(DecisionRepository).add(request)
        reason = blocking_reason(
            BlockingCode.WAITING_OWNER,
            task_id=task.id,
            refs={"decision_request_id": str(rid), "stop_code": code or "QUESTION_ASKED"},
            now=side.clock.now(),
            message="owner wait",
        )
        updated = replace(
            task,
            status=status,
            blocking_reason=reason if status is TaskStatus.AWAITING_DECISION else None,
            row_version=task.row_version + 1,
        )
        uow.repo(TaskRepository).save(updated, expected_version=task.row_version)
        uow.commit()
    return run, updated, attempt, request


def set_setting(side: Any, key: str, value: Any) -> Any:
    from skm.modules.settings.public import SetValue

    return side.client.dispatch(
        SetValue.from_json(
            {
                "scope": {"level": "instance"},
                "key": key,
                "value": value,
                "reason": "execution test",
                "confirmed": True,
            }
        )
    )


def carry_case(side: Any, *, baseline: str | None = "1" * 40, extra_work: bool = False):
    from skm.modules.execution.domain.attempt import AttemptEndReason, record_output, transition_attempt
    from skm.modules.execution.domain.environment import (
        BaselineEntry,
        EnvironmentKind,
        EnvironmentState,
        ExecutionEnvironment,
        attempt_branch,
    )
    from skm.modules.execution.domain.stage_record import StageState
    from skm.modules.execution.domain.task import accept
    from skm.modules.execution.ports import EnvironmentRepository

    source_run, source, source_attempt = seeded(side, task_status=TaskStatus.INTEGRATING)
    target_run, target, target_attempt = seeded(side, task_status=TaskStatus.ASSIGNED)
    with side.uow() as uow:
        for attempt, commit in ((source_attempt, "1" * 40), (target_attempt, baseline)):
            if commit is not None:
                env = ExecutionEnvironment(
                    side.new_id(),
                    attempt.id,
                    side.host1,
                    EnvironmentKind.GIT_WORKTREE,
                    (BaselineEntry("repo", side.repo_id, commit, commit, None),),
                    attempt_branch(attempt.id),
                    f"/test/{attempt.id}",
                    EnvironmentState.READY,
                    side.clock.now(),
                    None,
                    None,
                )
                uow.repo(EnvironmentRepository).upsert(env)
        output = seed_output(side, uow, source_attempt)
        current = record_output(source_attempt, output, previous=None)
        repo = uow.repo(AttemptRepository)
        repo.save(current, expected_version=repo.version(current.id))
        accepted = accept(source, rule="T19", attempt=current, output=output)
        uow.repo(TaskRepository).save(accepted, expected_version=source.row_version)
        repo.save(
            transition_attempt(
                current, AttemptState.COMPLETED, now=side.clock.now(), end_reason=AttemptEndReason.ACCEPTED
            ),
            expected_version=repo.version(current.id),
        )
        seed_stage(
            side,
            uow,
            target_attempt,
            stage_id="prepare",
            stage_type="prepare_environment",
            state=StageState.COMPLETED,
        )
        if extra_work:
            seed_stage(side, uow, target_attempt, seq=2, stage_id="execute", state=StageState.RUNNING)
        uow.commit()
    return source_run, accepted, target_run, target, target_attempt
