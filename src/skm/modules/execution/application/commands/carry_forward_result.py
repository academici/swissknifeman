"""Conservative exact-input reuse after a prepare-only target attempt."""

from typing import Any, cast
from uuid import UUID

from skm.application_bus.registry import CommandSpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, error_for
from skm.kernel.ids import FileVersionId, TaskId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeId, ScopeKind, ScopeRef
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._action_effects import finish_run
from skm.modules.execution.application._control import close_attempt, live_guard, require_permission
from skm.modules.execution.application._events import cause, emit, save_task
from skm.modules.execution.application._json_reads import obj
from skm.modules.execution.application._plain import plain
from skm.modules.execution.application._start_inputs import value
from skm.modules.execution.application.apply_action import release_dependents
from skm.modules.execution.domain.attempt import AttemptEndReason
from skm.modules.execution.domain.carry_forward import (
    COMPATIBILITY_SCHEMA_VERSION,
    CarryForward,
    CompatibilityInputs,
    compare_compatibility,
    compatibility_inputs_to_json,
)
from skm.modules.execution.domain.environment import EnvironmentState
from skm.modules.execution.domain.readiness import PROGRESSIVE_MODE, canonical_digest
from skm.modules.execution.domain.run import TERMINAL_RUN_STATUSES
from skm.modules.execution.domain.task import TaskStatus, accept_carried_forward
from skm.modules.execution.domain.task_graph import prerequisites
from skm.modules.execution.generated.commands import CarryForwardResult
from skm.modules.execution.generated.results import CarryForwardResultResult
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    BundleRepository,
    EnvironmentRepository,
    ExecutionQueries,
    OutputRepository,
    ReadinessRepository,
    RunRepository,
    StageRepository,
    TaskRepository,
)
from skm.modules.planning import public as planning


def scope(cmd: CarryForwardResult, uow: UnitOfWork) -> ScopeRef | None:
    try:
        target = uow.repo(TaskRepository).get(TaskId(cmd.target_task_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(target.run_id))


def _predecessor_outputs(uow: UnitOfWork, run: Any, task: Any) -> dict[str, str] | None:
    tasks = uow.repo(TaskRepository)
    predecessors = prerequisites(task.id, tasks.edges_for_run(run.id))
    carried = (
        {
            row.target_task_id: row.source_output_id
            for row in uow.repo(AcceptanceRepository).carry_forwards_for_run(run.id)
            if row.decision == "accepted"
        }
        if predecessors
        else {}
    )
    parents: dict[str, str] = {}
    for parent_id in predecessors:
        parent = tasks.get(parent_id)
        output_id = parent.accepted_output_id or carried.get(parent_id)
        if parent.status is not TaskStatus.ACCEPTED or output_id is None:
            return None
        parents[parent.display_key] = uow.repo(OutputRepository).get(output_id).manifest.tree_digest
    return parents


def compatibility_inputs(
    uow: UnitOfWork,
    run: Any,
    task: Any,
    attempt: Any,
    *,
    scoped_materials: bool = False,
    historical: bool = False,
) -> CompatibilityInputs:
    bundle = uow.repo(BundleRepository).get(run.id)
    spec = planning.get_revision_specification(uow, run.revision_id)
    entity = next((e for e in (*spec.items, *spec.units, *spec.phases) if e.id == task.spec_entity_id), None)
    graph = planning.compile_execution_graph(spec, run.revision_id)
    node = next((n for n in graph.tasks if n.task_key == task.display_key), None)
    parent = next((item for item in spec.items if node is not None and item.key == node.item_key), None)
    env = None if attempt is None else uow.repo(EnvironmentRepository).for_attempt(attempt.id)
    # Cleanup keeps the accepted source's baseline. The target still needs its prepared environment.
    usable_states = {EnvironmentState.READY}
    if historical:
        usable_states.update(
            {EnvironmentState.RETAINED, EnvironmentState.DISCARDED, EnvironmentState.REMOVED}
        )
    baseline = (
        None
        if env is None or env.state not in usable_states or not env.baseline
        else {b.mount: b.commit_sha for b in env.baseline}
    )
    materials: dict[str, str] = {}
    material_ids: set[str] = set() if node is None else {str(found) for found in node.materials}
    for material in planning.revision_materials(uow, run.revision_id):
        raw = plain(material)
        if scoped_materials and raw["material_id"] not in material_ids:
            continue
        if "execution" in raw.get("required_for", []):
            vid = raw.get("file_version_id")
            if not vid:
                return CompatibilityInputs(None, None, None, None, None, None, None, baseline)
            ready = artifacts.require_ready_versions(uow, run.workspace_id, (FileVersionId(UUID(vid)),))[0]
            materials[raw.get("key", vid)] = canonical_digest({"version": vid, "digest": plain(ready)})
    pins = {
        f"{p.kind}:{p.key}": f"{p.resource_version_id}:{p.digest}" for p in bundle.resource_pins.resources
    }
    pins.update({"pack:" + str(k): str(v) for k, v in bundle.resource_pins.packs.items()})
    check_ids: set[Any] = set() if node is None else {b.check_id for b in node.checks}
    checks = {f"{c.owner}:{c.key}": canonical_digest(plain(c)) for c in spec.checks if c.id in check_ids}
    snapshot = bundle.config_snapshot
    config = dict(obj(snapshot["values"], "config_snapshot.values") if "values" in snapshot else snapshot)
    wp = None if bundle.work_policies is None else bundle.work_policies.get(task.display_key)
    return CompatibilityInputs(
        None
        if entity is None or node is None or wp is None
        else canonical_digest(
            {
                "entity": plain(entity),
                "parent_item": plain(parent),
                "node": plain(node),
                "work_policy": wp.digest,
            }
        ),
        pins,
        checks,
        canonical_digest({"registry": bundle.config_snapshot.get("registry_digest"), "values": config}),
        canonical_digest(
            {
                "policy": bundle.policy_digest,
                "acceptance": {
                    k: v
                    for k, v in config.items()
                    if k.startswith(("checks.", "execution.review.", "execution.acceptance."))
                },
            }
        ),
        materials,
        _predecessor_outputs(uow, run, task),
        baseline,
    )


def handle(cmd: CarryForwardResult, ctx: Any, uow: UnitOfWork) -> CarryForwardResultResult:
    tasks, runs = uow.repo(TaskRepository), uow.repo(RunRepository)
    source, target = tasks.get(TaskId(cmd.source_task_id)), tasks.get(TaskId(cmd.target_task_id))
    locked_runs = {
        rid: runs.get(rid, for_update=True) for rid in sorted({source.run_id, target.run_id}, key=str)
    }
    locked_tasks = {tid: tasks.get(tid, for_update=True) for tid in sorted({source.id, target.id}, key=str)}
    source, target = locked_tasks[source.id], locked_tasks[target.id]
    old_run, run = locked_runs[source.run_id], locked_runs[target.run_id]
    require_permission(uow, ctx, run, "deviation.accept", human=True)
    if not value(ctx.config, "execution.carry_forward.allowed", True):
        raise error_for(ErrorCode.FORBIDDEN, "carry-forward is disabled")
    live_guard(uow, ctx, run)
    if (
        run.status in TERMINAL_RUN_STATUSES
        or source.run_id == target.run_id
        or run.plan_id is None
        or run.plan_id != old_run.plan_id
        or source.status is not TaskStatus.ACCEPTED
        or target.status not in {TaskStatus.ASSIGNED, TaskStatus.EXECUTING}
        or target.current_attempt_id is None
        or source.accepted_attempt_id is None
        or source.accepted_output_id is None
    ):
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "source acceptance and a prepare-only target are required")
    report = (
        None
        if run.readiness_report_id is None
        else uow.repo(ReadinessRepository).get(run.readiness_report_id)
    )
    progressive = report is not None and (report.start_request or {}).get("mode") == PROGRESSIVE_MODE
    if progressive and (
        run.revision_no is None or old_run.revision_no is None or run.revision_no <= old_run.revision_no
    ):
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "progressive carry-forward requires a newer revision")
    target_attempt = uow.repo(AttemptRepository).get(target.current_attempt_id, for_update=True)
    history = uow.repo(StageRepository).history(target_attempt.id)
    entries = history.entries
    if (
        not entries
        or any(
            e.record.stage_type != "prepare_environment"
            or e.record.state.value != "completed"
            or e.record.runtime_started_at is not None
            or e.steps
            for e in entries
        )
        or target_attempt.current_output_id is not None
        or uow.repo(ExecutionQueries).attempt_view(target_attempt.id).get("effects")
    ):
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "target has already started work beyond preparation")
    old_attempt = uow.repo(AttemptRepository).get(source.accepted_attempt_id)
    source_inputs = compatibility_inputs(
        uow, old_run, source, old_attempt, scoped_materials=progressive, historical=True
    )
    target_inputs = compatibility_inputs(uow, run, target, target_attempt, scoped_materials=progressive)
    compared = compare_compatibility(source_inputs, target_inputs)
    if not compared.compatible:
        raise error_for(
            ErrorCode.NOT_ACCEPTABLE,
            "compatibility evidence differs or is incomplete",
            details=plain(compared),
        )
    row = CarryForward(
        ctx.ids.new_id(),
        source.run_id,
        source.id,
        source.accepted_attempt_id,
        source.accepted_output_id,
        target.run_id,
        target.id,
        cast("str", compared.source_digest),
        {
            "schema_version": COMPATIBILITY_SCHEMA_VERSION,
            "source": compatibility_inputs_to_json(source_inputs),
            "target": compatibility_inputs_to_json(target_inputs),
        },
        "accepted",
        ctx.actor.principal_id,
        cmd.reason,
        ctx.clock.now(),
    )
    uow.repo(AcceptanceRepository).add_carry_forward(row)
    close_attempt(
        uow, ctx, run, target_attempt, code="OWNER_DECISION", reason=AttemptEndReason.OWNER_DECISION
    )
    updated = accept_carried_forward(target, row)
    why = cause("carry_forward")
    save_task(uow, run, target, updated, why, ctx.clock.now())
    emit(
        uow,
        run,
        "task-accepted",
        {
            "task_id": str(target.id),
            "attempt_id": None,
            "output_id": None,
            "carried_forward": True,
            "clearance": "deviation",
            "carry_forward_id": str(row.id),
        },
        why,
    )
    release_dependents(uow, ctx, run, why)

    finish_run(uow, ctx, run, why)
    return CarryForwardResultResult(row.id, updated.status.value)


SPEC = CommandSpec(
    name="execution.carry_forward_result",
    dto=CarryForwardResult,
    result=CarryForwardResultResult,
    permission="deviation.accept",
    scope_of=None,
    scope_resolver=scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.HUMAN}),
)
