"""Record an owned terminal result, settle once and apply its continuation."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import FileVersionId, RepositoryId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.context.public import (
    require_final,
)
from skm.modules.execution.application._integration_inputs import check_integration_result
from skm.modules.execution.application._live_control import require_not_stopping
from skm.modules.execution.application._primitives import save_attempt, schemas
from skm.modules.execution.application._worker_budget import close_budgets, pause_budget, priced_usage
from skm.modules.execution.application._worker_dtos import RecordStageResult, RecordStageResultResult, digest
from skm.modules.execution.application._worker_events import (
    close_steps,
    precheck_observations,
    stage_completed,
)
from skm.modules.execution.application._worker_evidence import register
from skm.modules.execution.application._worker_host_stages import record_checks, record_review
from skm.modules.execution.application._worker_integration import record_integration
from skm.modules.execution.application._worker_protocol import (
    fenced_scope,
    lock_fenced_context,
    locked_stage,
    next_instruction,
    parse_worker_claim,
    revoke_authority,
    verify_fenced_replay,
    verify_worker,
)
from skm.modules.execution.application._worker_result import (
    advance_terminal,
    record_minimal_triage,
    terminal_stage,
    validate_agent_result,
)
from skm.modules.execution.application.commands.reconcile_external_effect import (
    admin_context,
    record_admin,
    verify_admin_result_replay,
)
from skm.modules.execution.application.commands.record_external_effect import (
    complete_external,
    propose_effects,
)
from skm.modules.execution.application.commands.report_attempt_failure import close_effects
from skm.modules.execution.domain.assignment import AssignmentState
from skm.modules.execution.domain.attempt import AttemptState, transition_attempt
from skm.modules.execution.domain.environment import (
    BaselineEntry,
    EnvironmentKind,
    EnvironmentState,
    ExecutionEnvironment,
    attempt_branch,
)
from skm.modules.execution.domain.ids import CheckExecutionId, EnvironmentId, OutputId
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES, AGENT_STAGE_TYPES, StageOutcomeKind
from skm.modules.execution.ports import (
    AssignmentRepository,
    CheckRepository,
    EnvironmentRepository,
    EvidenceBindingRepository,
    OutputRepository,
    ReviewRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)


def _locator(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or "\0" in value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value[1:].split("/"))
    ):
        raise error_for(ErrorCode.SCHEMA_INVALID, "environment locator must be canonical and absolute")
    return value


def prepare_environment_result(
    uow: UnitOfWork, fenced: Any, outcome: Any, previous_evidence: set[Any]
) -> None:
    metadata = outcome.get("mounts", ())
    entries = outcome.get("baseline", ())
    names = [b["mount"] for b in entries]
    if (
        not names
        or len(set(names)) != len(names)
        or len(metadata) != len(names)
        or {m.get("mount") for m in metadata} != set(names)
    ):
        raise error_for(ErrorCode.SCHEMA_INVALID, "prepare mounts and baseline must match exactly")
    locators = {_locator(m.get("environment_locator")) for m in metadata}
    if len(locators) != 1:
        raise error_for(ErrorCode.SCHEMA_INVALID, "mounts must share one owned environment locator")
    locator = locators.pop()
    if locator.rsplit("/", 1)[-1] != str(fenced.attempt.id):
        raise error_for(ErrorCode.INVALID_REFERENCE, "environment locator belongs to another attempt")
    kind = EnvironmentKind(outcome["kind"])
    if outcome.get("branch") != attempt_branch(fenced.attempt.id):
        raise error_for(ErrorCode.INVALID_REFERENCE, "environment branch belongs to another attempt")
    by_mount = {m["mount"]: m for m in metadata}
    versions = uow.repo(artifacts.FileVersionRepository)
    patches: dict[str, Any] = {}
    for version_id, role in uow.repo(EvidenceBindingRepository).for_owner("attempt", fenced.attempt.id):
        if version_id in previous_evidence or role.value != "patch":
            continue
        version = versions.get(version_id)
        if version.original_filename in patches:
            raise error_for(ErrorCode.INVALID_REFERENCE, "dirty patch filename is ambiguous")
        patches[version.original_filename] = version
    baseline = _prepare_baseline(entries, by_mount, patches, kind, locator)
    env = ExecutionEnvironment(
        EnvironmentId(UUID(outcome["environment_id"])),
        fenced.attempt.id,
        fenced.worker.host_id,
        kind,
        tuple(baseline),
        attempt_branch(fenced.attempt.id),
        locator,
        EnvironmentState.READY,
        fenced.now,
        None,
        None,
    )
    repo = uow.repo(EnvironmentRepository)
    previous = repo.for_attempt(fenced.attempt.id)
    if previous is not None:
        env = _reopened_environment(versions, previous, env)
    repo.upsert(env)
    attempt = replace(fenced.attempt, environment_id=env.id)
    if attempt.state is AttemptState.PREPARING:
        attempt = transition_attempt(attempt, AttemptState.RUNNING)
    save_attempt(uow, attempt)
    fenced.attempt = attempt


def _prepare_baseline(
    entries: Any, by_mount: Any, patches: Any, kind: EnvironmentKind, locator: str
) -> tuple[BaselineEntry, ...]:
    baseline: list[BaselineEntry] = []
    used: set[Any] = set()
    for entry in entries:
        mount = entry["mount"]
        if not mount or "/" in mount or "\\" in mount or mount in {".", ".."}:
            raise error_for(ErrorCode.SCHEMA_INVALID, "invalid environment mount")
        local = _locator(by_mount[mount].get("local_locator"))
        if kind is not EnvironmentKind.EXISTING_CHECKOUT and local != f"{locator}/{mount}":
            raise error_for(ErrorCode.INVALID_REFERENCE, "mount locator differs from owned environment")
        source = entry.get("source_head_sha", entry["commit_sha"])
        dirty = source != entry["commit_sha"]
        filename = by_mount[mount].get("dirty_patch_filename")
        patch = patches.get(filename)
        if entry.get("dirty_patch_file_version_id") is not None:
            raise error_for(ErrorCode.INVALID_REFERENCE, "dirty patches must be freshly staged evidence")
        if dirty and (kind is not EnvironmentKind.EXISTING_CHECKOUT or patch is None or patch.id in used):
            raise error_for(ErrorCode.INVALID_REFERENCE, "dirty baseline requires its own attempt patch")
        if not dirty and filename is not None:
            raise error_for(ErrorCode.INVALID_REFERENCE, "clean baseline cannot claim a dirty patch")
        patch_id = None
        if dirty:
            patch_id = FileVersionId(patch.id)
        if patch_id is not None:
            used.add(patch_id)
        baseline.append(
            BaselineEntry(
                mount, RepositoryId(UUID(entry["repository_id"])), entry["commit_sha"], source, patch_id
            )
        )
    return tuple(baseline)


def _reopened_environment(
    versions: Any, previous: ExecutionEnvironment, env: ExecutionEnvironment
) -> ExecutionEnvironment:
    # Reopening preserves B and all ownership facts; equivalent re-upload keeps the original version.
    old = {b.mount: b for b in previous.baseline}
    rebound: list[BaselineEntry] = []
    for entry in env.baseline:
        prior = old.get(entry.mount)
        if prior is None:
            raise error_for(ErrorCode.CHECKOUT_MISMATCH, "reopened baseline mount changed")
        bound_entry = entry
        if prior.dirty_patch_file_version_id is not None and entry.dirty_patch_file_version_id is not None:
            if (
                versions.get(prior.dirty_patch_file_version_id).blob_id
                != versions.get(entry.dirty_patch_file_version_id).blob_id
            ):
                raise error_for(ErrorCode.CHECKOUT_MISMATCH, "reopened dirty patch changed")
            bound_entry = replace(entry, dirty_patch_file_version_id=prior.dirty_patch_file_version_id)
        rebound.append(bound_entry)
    env = replace(env, baseline=tuple(rebound), created_at=previous.created_at)
    if env != previous:
        raise error_for(ErrorCode.CHECKOUT_MISMATCH, "reopened environment binding changed")
    return env


def consume_stage_evidence(
    uow: UnitOfWork, ctx: Any, fenced: Any, steps: Any, evidence: Any
) -> dict[Any, Any]:
    """Validate the whole batch, then lock typed digests by their canonical value (K8).

    ContentDigest is an opaque value object without ordering. Multiple mount patches/logs therefore
    need an explicit string key, while all staged/digest locks still precede any file registration.
    """
    step_ids = {step.id for step in steps}
    for item in evidence:
        owner, owner_id = item["owner"], UUID(item["owner_id"])
        valid = (owner == "attempt" and owner_id == fenced.attempt.id) or (
            owner == "step" and owner_id in step_ids
        )
        if owner == "output":
            valid = uow.repo(OutputRepository).get(OutputId(owner_id)).attempt_id == fenced.attempt.id
        elif owner == "check_execution":
            valid = uow.repo(CheckRepository).get(CheckExecutionId(owner_id)).attempt_id == fenced.attempt.id
        elif owner == "review":
            valid = any(
                r.id == owner_id and r.attempt_id == fenced.attempt.id
                for r in uow.repo(ReviewRepository).for_task(fenced.task.id)
            )
        if not valid:
            raise error_for(
                ErrorCode.INVALID_REFERENCE, "evidence owner is outside the current stage/attempt"
            )
        if item["role"] not in set(artifacts.BindingRole):
            raise error_for(
                ErrorCode.SCHEMA_INVALID,
                f"role {item['role']!r} is not valid for {owner} bindings",
                details={"field": "role"},
            )
    locks = uow.repo(artifacts.BlobDigestLock)
    ordered = sorted(evidence, key=lambda item: item["staged_blob"]["staged_blob_id"])
    for item in ordered:
        locks.lock_staged(
            fenced.run.workspace_id, artifacts.StagedBlobId(UUID(item["staged_blob"]["staged_blob_id"]))
        )
    consumed = [
        (
            item,
            artifacts.consume_staged_blob(
                uow,
                ref=item["staged_blob"],
                workspace_id=fenced.run.workspace_id,
                request_id=ctx.meta.request_id,
                now=fenced.now,
            ),
        )
        for item in ordered
    ]
    consumed.sort(key=lambda pair: (pair[1].backend_id, pair[1].digest.value))
    for _, blob in consumed:
        locks.lock_digest(fenced.run.workspace_id, blob.digest, blob.backend_id)
    bindings: dict[Any, Any] = {}
    for item, blob in consumed:
        version_id = register(uow, ctx, fenced, item, consumed=blob)
        owner, owner_id = item["owner"], UUID(item["owner_id"])
        uow.repo(EvidenceBindingRepository).bind(
            "attempt" if owner == "step" else owner,
            fenced.attempt.id if owner == "step" else owner_id,
            (version_id,),
            artifacts.BindingRole(item["role"]),
        )
        bindings[(owner_id, item["role"])] = version_id
    return bindings


def handle(  # noqa: PLR0912, PLR0915 -- one atomic worker protocol transition
    cmd: RecordStageResult, ctx: Any, uow: UnitOfWork
) -> RecordStageResultResult:
    admin = admin_context(uow, ctx, cmd["claim"], allow_closed=True)
    if admin is not None:
        return record_admin(cmd, ctx, uow, admin)
    if "reconciled_effect" in cmd["outcome"]:
        raise error_for(ErrorCode.FORBIDDEN, "only a server-bound assignment can reconcile an effect")
    fenced = lock_fenced_context(uow, ctx, cmd["claim"], allow_terminal=True)
    stage = locked_stage(uow, fenced, cmd["stage_record_id"])
    outcome, kind = dict(cmd["outcome"]), StageOutcomeKind(cmd["outcome_kind"])
    metadata: dict[str, Any] = stage.outcome or {}
    prepared_inputs = metadata.get("integration_inputs") if stage.stage_type == "integrate" else None
    if stage.state not in ACTIVE_STAGE_STATES:
        recorded = dict(stage.outcome or {})
        recorded.pop("integration_inputs", None)
        recorded.pop("external_effect_id", None)
        if digest(recorded) != digest(outcome) or stage.outcome_kind is not kind:
            raise error_for(
                ErrorCode.INVALID_TRANSITION, "terminal stage result differs from its recorded outcome"
            )
        if cmd.get("observations"):
            raise error_for(ErrorCode.INVALID_TRANSITION, "terminal steps accept no late observation")
        return RecordStageResultResult(
            task_status=uow.repo(TaskRepository).get(fenced.task.id).status.value,
            next=next_instruction(uow, fenced),
        )
    require_not_stopping(stage)
    steps = uow.repo(StepRepository).for_stage(stage.id)
    observations = precheck_observations(steps, cmd.get("observations", ()))
    if stage.stage_type in AGENT_STAGE_TYPES:
        for step in steps:
            manifest = require_final(uow, step.context_manifest_id)
            if manifest.owner_ref != f"step:{step.id}":
                raise error_for(ErrorCode.FORBIDDEN, "result manifest belongs to another step")
    schemas().require_valid(
        f"urn:skm:execution:stage-outcome-{stage.stage_type.replace('_', '-')}:v1", outcome
    )
    previous_evidence = {
        version_id
        for version_id, _ in uow.repo(EvidenceBindingRepository).for_owner("attempt", fenced.attempt.id)
    }
    bindings = consume_stage_evidence(uow, ctx, fenced, steps, cmd.get("evidence", ()))
    result, schema_errors = None, ()
    if steps and kind not in {StageOutcomeKind.RESULT_INVALID, StageOutcomeKind.RUNTIME_ERROR}:
        if outcome.get("step_id") != str(steps[0].id):
            raise error_for(ErrorCode.INVALID_REFERENCE, "role result names a foreign step")
        try:
            result = validate_agent_result(uow, fenced, steps[0], outcome, bindings)
        except SkmError as exc:
            if exc.code is ErrorCode.REPAIR_SEMANTIC_DRIFT:
                raise
            kind = StageOutcomeKind.RESULT_INVALID
            schema_errors = ({"code": "RESULT_INVALID", "message": exc.message},)
            outcome = {**outcome, "error_code": "RESULT_INVALID"}
    if result is not None:
        if outcome.get("output_id") is not None and outcome["output_id"] != str(
            fenced.attempt.current_output_id
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "result output was not sealed by this attempt")
        if steps[0].role.value == "executor":
            if result.get("questions"):
                kind = StageOutcomeKind.QUESTION
                outcome["questions"] = result["questions"]
            elif result.get("status") == "blocked":
                kind = StageOutcomeKind.BLOCKED
        elif steps[0].role.value == "reviewer":
            if (
                outcome.get("output_id") is not None
                and steps[0].admission.get("reviewer_with_fix") is not True
            ):
                raise error_for(ErrorCode.INVALID_REFERENCE, "read-only review cannot report a fix")
            kind = {
                "green": StageOutcomeKind.VERDICT_GREEN,
                "attention": StageOutcomeKind.VERDICT_ATTENTION,
                "red": StageOutcomeKind.VERDICT_RED,
            }[result["verdict"]]
    successful = kind not in {StageOutcomeKind.RESULT_INVALID, StageOutcomeKind.RUNTIME_ERROR}
    if successful and result is not None and steps[0].role.value == "triager":
        record_minimal_triage(uow, fenced, result)
    if stage.stage_type == "prepare_environment" and kind is StageOutcomeKind.SUCCESS:
        prepare_environment_result(uow, fenced, outcome, previous_evidence)
    if stage.stage_type == "run_checks" and successful:
        record_checks(uow, fenced, stage, outcome)
    if stage.stage_type == "agent_review" and successful:
        record_review(uow, ctx, fenced, outcome, result)
    if stage.stage_type == "integrate" and kind is StageOutcomeKind.OUTCOME_UNKNOWN:
        close_effects(uow, ctx, fenced)
    if stage.stage_type == "integrate" and kind is StageOutcomeKind.APPROVAL_REQUIRED:
        propose_effects(uow, ctx, fenced, outcome)
    if stage.stage_type == "integrate" and kind is StageOutcomeKind.SUCCESS:
        if metadata.get("external_effect_id"):
            complete_external(uow, fenced, stage, outcome)
        else:
            check_integration_result(uow, fenced, stage, outcome)
            record_integration(uow, ctx, fenced, stage, outcome)
    notes = [
        note
        for step in steps
        for note in uow.repo(StepRepository).notes_for_step(step.id)
        if note.kind.value == "question"
    ]
    if successful and notes:
        kind = StageOutcomeKind.QUESTION
        outcome["questions"] = [
            {
                "id": str(n.id),
                "kind": "decision",
                "text": n.text,
                "options": list(n.options),
                "why_blocked": n.why_blocked,
                "urgency": n.urgency.value,
            }
            for n in notes
        ]
    updates = {
        step.id: {
            "schema_errors": schema_errors,
            "repairs": tuple(outcome.get("repairs", ())),
            "session_ref": outcome.get("session_ref", step.session_ref),
            "raw_result_file_version_id": bindings.get((step.id, "raw_result")),
            "transcript_file_version_id": bindings.get((step.id, "transcript")),
        }
        for step in steps
    }
    closed = close_steps(
        uow,
        fenced,
        stage,
        steps,
        successful=successful,
        observations=observations,
        result=result,
        code=None if successful else kind.value.upper(),
        usage=priced_usage(uow, ctx, fenced, steps[0] if steps else None, cmd.get("usage")),
        activity=cmd.get("activity"),
        updates=updates,
    )
    budget_refusal = close_budgets(uow, fenced, stage, closed)
    if metadata.get("external_effect_id"):
        outcome["external_effect_id"] = metadata["external_effect_id"]
    if prepared_inputs is not None:
        outcome["integration_inputs"] = prepared_inputs
    stage = terminal_stage(stage, kind, outcome, fenced.now)
    uow.repo(StageRepository).save(stage)
    for step in steps:
        revoke_authority(uow, ctx, fenced, step_id=step.id)
    stage_completed(uow, fenced, stage, closed, diagnostics=cmd.get("diagnostics", ()))
    if budget_refusal is not None:
        pause_budget(uow, ctx, fenced, budget_refusal)
    advance_terminal(uow, ctx, fenced, stage)
    return RecordStageResultResult(
        task_status=uow.repo(TaskRepository).get(fenced.task.id).status.value,
        next=next_instruction(uow, fenced),
    )


def replay_guard(cmd: RecordStageResult, ctx: Any, uow: UnitOfWork) -> None:
    claim = parse_worker_claim(cmd["claim"])
    assignment = uow.repo(AssignmentRepository).get(claim.assignment_id)
    if assignment.reconcile_effect_id is not None and assignment.state is AssignmentState.COMPLETED:
        worker = verify_worker(uow, ctx.actor, claim.worker_id, workspace_id=assignment.workspace_id)
        verify_admin_result_replay(cmd, ctx, uow, claim, assignment, worker)
        return
    verify_fenced_replay(cmd, ctx, uow)


SPEC = CommandSpec(
    name="execution.record_stage_result",
    dto=RecordStageResult,
    result=RecordStageResultResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
    replay_guard=replay_guard,
)
