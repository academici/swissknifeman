"""Freeze accepted integration inputs once; host paths and writer containment stay on the host."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast
from uuid import UUID, uuid5

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.context.public import get_manifest
from skm.modules.execution.application._json_reads import objects, text
from skm.modules.execution.application._state import effective_values
from skm.modules.execution.application._worker_dtos import digest, document
from skm.modules.execution.application._worker_events import executed_by
from skm.modules.execution.domain.contracts import EvidenceOwnerKind
from skm.modules.execution.domain.ids import FixBriefId, OutputId, StepId
from skm.modules.execution.domain.integration import (
    SESSION_REF,
    CommitMode,
    IntegrationStrategy,
    validate_mode,
)
from skm.modules.execution.domain.review import ReviewState
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.execution.ports import (
    AcceptanceRepository,
    EnvironmentRepository,
    EvidenceBindingRepository,
    ExecutionQueries,
    OutputRepository,
    ReviewRepository,
    StageRepository,
    StepRepository,
)
from skm.modules.planning import public as planning


def task_spec_trailers(uow: UnitOfWork, run: Any, task: Any) -> dict[str, str]:
    if run.revision_id is not None and task.spec_entity_id is not None:
        spec = planning.get_revision_specification(uow, run.revision_id)
        return {
            "task_spec_ref": f"skm:revision:{run.revision_id}#entity:{task.spec_entity_id}",
            "task_spec_digest": digest(spec.entity(task.spec_entity_id)),
        }
    if run.inline_spec_file_version_id is not None:
        version = artifacts.get_file_version(uow, run.inline_spec_file_version_id)
        return {
            "task_spec_ref": f"skm:file-version:{run.inline_spec_file_version_id}",
            "task_spec_digest": version.digest,
        }
    if task.origin is not None:
        return {
            "task_spec_ref": f"skm:task:{task.id}",
            "task_spec_digest": digest(
                {"kind": task.kind, "origin": task.origin, "write_scope": task.declared_write_scope}
            ),
        }
    return {}


def step_attribution(step: Any) -> dict[str, str]:
    attribution = {"plan_role": step.role.value}
    snapshot = cast("Mapping[str, JsonValue] | None", step.route_snapshot)
    assigned = snapshot.get("requested_route") if snapshot is not None else None
    if isinstance(assigned, Mapping):
        route = cast("Mapping[str, JsonValue]", assigned)
        parts = tuple(
            value
            for key in ("runtime_id", "model", "effort")
            if isinstance(value := route.get(key), str) and value
        )
        if parts:
            attribution["plan_actor"] = "/".join(parts)
    actual = executed_by(step.route_snapshot, step.runtime_observation)
    if actual is not None:
        attribution["executed_by"] = actual
        session = step.session_ref
        if isinstance(session, str) and SESSION_REF.fullmatch(session):
            attribution["executor_session"] = session
    return attribution


def output_attribution(uow: UnitOfWork, fenced: Any, chain: list[Any], decision: Any) -> list[dict[str, Any]]:
    repo = uow.repo(ReviewRepository)
    reviews = {
        review.id: review
        for review in repo.for_task(fenced.task.id)
        if review.attempt_id == fenced.attempt.id and review.state is ReviewState.COMPLETED
    }
    findings: dict[Any, set[str]] = {}
    for finding in repo.findings_for_task(fenced.task.id):
        if finding.review_id in reviews:
            findings.setdefault(finding.review_id, set()).add(finding.finding_key)
    steps = uow.repo(StepRepository)
    metadata: list[dict[str, Any]] = []
    for output in chain:
        row: dict[str, Any] = {}
        source_review = None
        keys: set[str] = set()
        if output.produced_by_step_id is not None:
            step = steps.get(output.produced_by_step_id)
            row["producers"] = [step_attribution(step)]
            brief_id = step.admission.get("fix_brief_id")
            if isinstance(brief_id, str):
                brief = repo.get_fix_brief(FixBriefId(UUID(brief_id)))
                if brief.source_review_id is not None:
                    source_review = reviews.get(brief.source_review_id)
                keys.update(item.finding_key for item in brief.items)
            if step.role.value == "reviewer":
                source_review = next(
                    (r for r in reviews.values() if r.reviewer_ref.get("step_id") == str(step.id)), None
                )
                if source_review is not None:
                    keys.update(findings.get(source_review.id, ()))
        review = (
            reviews.get(decision.basis.review_id)
            if decision.output_id == output.id and decision.basis.review_id is not None
            else max(
                (r for r in reviews.values() if r.output_id == output.id),
                key=lambda r: r.round_no,
                default=source_review,
            )
        )
        if review is not None:
            row.update(review_id=str(review.id), review_round=review.round_no)
            keys.update(findings.get(review.id, ()))
            reviewer_id = review.reviewer_ref.get("step_id")
            if isinstance(reviewer_id, str):
                reviewer = step_attribution(steps.get(StepId(UUID(reviewer_id))))
                row["reviewed_by"] = reviewer.get("executed_by")
                row["reviewer_session"] = reviewer.get("executor_session")
        if keys:
            row["findings"] = sorted(keys)
        metadata.append(row)
    return metadata


def accepted_inputs(uow: UnitOfWork, fenced: Any) -> tuple[Any, Any, Any]:
    output = uow.repo(OutputRepository).latest(fenced.attempt.id)
    environment = uow.repo(EnvironmentRepository).for_attempt(fenced.attempt.id)
    decisions = uow.repo(AcceptanceRepository).decisions_for_task(fenced.task.id)
    decision = next(
        (
            d
            for d in reversed(decisions)
            if d.decision == "accepted"
            and d.attempt_id == fenced.attempt.id
            and output is not None
            and d.output_id == output.id
        ),
        None,
    )
    if output is None or decision is None or environment is None:
        raise error_for(
            ErrorCode.INVALID_TRANSITION, "integration requires the accepted current output and environment"
        )
    if fenced.attempt.current_output_id != output.id or fenced.task.current_attempt_id != fenced.attempt.id:
        raise error_for(ErrorCode.INVALID_TRANSITION, "accepted output is no longer current")
    if environment.host_id != fenced.worker.host_id:
        raise error_for(ErrorCode.INTEGRATION_HOST_MISMATCH, "environment belongs to another host")
    return output, environment, decision


def artifact_digests(uow: UnitOfWork, fenced: Any, output: Any) -> list[str]:
    owners: tuple[tuple[EvidenceOwnerKind, UUID], ...] = (
        ("attempt", fenced.attempt.id),
        ("output", output.id),
    )
    versions = {
        version
        for kind, identity in owners
        for version, _ in uow.repo(EvidenceBindingRepository).for_owner(kind, identity)
    }
    view = uow.repo(ExecutionQueries).attempt_view(fenced.attempt.id)
    collections: tuple[tuple[str, EvidenceOwnerKind, str], ...] = (
        ("outputs", "output", "output_id"),
        ("checks", "check_execution", "check_execution_id"),
        ("reviews", "review", "review_id"),
    )
    for collection, kind, key in collections:
        for row in objects(view.get(collection), collection):
            identity = UUID(text(row[key], f"{collection}.{key}"))
            versions.update(
                version for version, _ in uow.repo(EvidenceBindingRepository).for_owner(kind, identity)
            )
    for entry in uow.repo(StageRepository).history(fenced.attempt.id).entries:
        for step in uow.repo(StepRepository).for_stage(entry.record.id):
            for version in (
                step.raw_result_file_version_id,
                step.transcript_file_version_id,
                get_manifest(uow, step.context_manifest_id).prompt_file_version_id,
            ):
                if version is not None:
                    versions.add(version)
    return sorted({artifacts.get_file_version(uow, version).digest for version in versions})


def prepare_integration(uow: UnitOfWork, fenced: Any, stage: Any) -> Any:
    metadata: dict[str, Any] = stage.outcome or {}
    saved = metadata.get("integration_inputs")
    if saved is not None:
        return document(saved)
    output, environment, decision = accepted_inputs(uow, fenced)
    # An uncertain multi-target publication keeps its original requests/effect IDs. A later stage
    # must not turn A-success/B-unknown into a second publication of A under a new identity.
    for entry in reversed(uow.repo(StageRepository).history(fenced.attempt.id).entries):
        prior = entry.record
        packet = (prior.outcome or {}).get("integration_inputs")
        if (
            prior.id != stage.id
            and prior.stage_type == "integrate"
            and isinstance(packet, Mapping)
            and packet.get("accepted_output_id") == str(output.id)
            and packet.get("acceptance_decision_id") == str(decision.id)
        ):
            uow.repo(StageRepository).save(replace(stage, outcome={"integration_inputs": document(packet)}))
            return document(packet)
    if stage.mode is StageMode.RECONCILE:
        raise error_for(ErrorCode.INVALID_TRANSITION, "reconciliation requires original integration inputs")
    _, values = effective_values(uow, fenced.run.id)
    strategy = IntegrationStrategy(values.get("execution.integration.strategy", "squash"))
    mode = CommitMode(values.get("execution.integration.commit_mode", "final_only"))
    validate_mode(strategy, mode)
    branch = str(values.get("execution.integration.branch", "skm/integration/{run}")).replace(
        "{run}", str(fenced.run.id)
    )
    rows = objects(uow.repo(ExecutionQueries).attempt_view(fenced.attempt.id).get("outputs"), "outputs")
    chain_outputs = sorted(
        (
            uow.repo(OutputRepository).get(OutputId(UUID(text(row["output_id"], "outputs.output_id"))))
            for row in rows
        ),
        key=lambda o: o.seq,
    )
    if not chain_outputs or chain_outputs[-1].id != output.id:
        raise error_for(ErrorCode.INVALID_TRANSITION, "accepted output chain changed")
    attribution = output_attribution(uow, fenced, chain_outputs, decision)
    if mode is CommitMode.FINAL_ONLY:
        # Each contributor remains visible after collapsing the accepted output chain.
        final = attribution[-1]
        final["producers"] = [producer for row in attribution for producer in row.get("producers", ())]
        final["findings"] = sorted({key for row in attribution for key in row.get("findings", ())})
        chain_outputs, attribution = chain_outputs[-1:], attribution[-1:]
    baseline = {b.mount: b for b in environment.baseline}
    task_spec = task_spec_trailers(uow, fenced.run, fenced.task)
    plan_id = fenced.run.plan_id
    plan = planning.get_plan_ref(uow, plan_id).alias if plan_id is not None else "adhoc"
    targets: list[dict[str, Any]] = []
    for mount in output.manifest.mounts:
        base = baseline.get(mount.mount)
        if base is None or base.repository_id != mount.repository_id or base.commit_sha != mount.base_commit:
            raise error_for(ErrorCode.INVALID_REFERENCE, "output differs from the environment baseline")
        chain: list[dict[str, Any]] = []
        for item, evidence in zip(chain_outputs, attribution, strict=True):
            projected = next((m for m in item.manifest.mounts if m.mount == mount.mount), None)
            if (
                projected is None
                or projected.repository_id != mount.repository_id
                or projected.base_commit != base.commit_sha
            ):
                raise error_for(ErrorCode.INVALID_REFERENCE, "output chain changed repository or baseline")
            chain.append(
                {
                    "output_id": str(item.id),
                    "output_digest": item.manifest_digest,
                    "head_sha": projected.head_commit,
                    "output_no": item.seq,
                    **evidence,
                }
            )
        effect = uuid5(stage.id, str(mount.repository_id) + ":refs/heads/" + branch)
        targets.append(
            {
                "repository_id": str(mount.repository_id),
                "target_branch": branch,
                "effect_id": str(effect),
                "mount": mount.mount,
                "baseline_sha": base.commit_sha,
                "run_id": str(fenced.run.id),
                "plan_id": str(plan_id) if plan_id is not None else "adhoc",
                "revision_no": fenced.run.revision_no or 0,
                "task_key": fenced.task.display_key,
                "plan": plan,
                "plan_ref": fenced.task.display_key,
                **task_spec,
                "attempt_id": str(fenced.attempt.id),
                "assignment_fencing_token": fenced.claim.fencing_token,
                "outputs": chain,
                "strategy": strategy.value,
                "commit_mode": mode.value,
                "exclude_paths": values.get("execution.integration.exclude_paths", [".skm/**"]),
            }
        )
    targets.sort(key=lambda t: (t["repository_id"].encode(), t["target_branch"].encode()))
    if len({(t["repository_id"], t["target_branch"]) for t in targets}) != len(targets):
        raise error_for(ErrorCode.INVALID_REFERENCE, "duplicate integration targets")
    payload = {
        "accepted_output_id": str(output.id),
        "acceptance_decision_id": str(decision.id),
        "integration_targets": targets,
        "artifact_digests": artifact_digests(uow, fenced, output),
        "slot_limits": {
            "wait_max_seconds": values.get("execution.integration.slot_wait_max_seconds", 1800),
            "poll_seconds": values.get("execution.integration.slot_poll_seconds", 5),
        },
    }
    uow.repo(StageRepository).save(replace(stage, outcome={"integration_inputs": document(payload)}))
    return document(payload)


def check_integration_result(uow: UnitOfWork, fenced: Any, stage: Any, outcome: Any) -> None:
    metadata: dict[str, Any] = stage.outcome or {}
    inputs: dict[str, Any] | None = metadata.get("integration_inputs")
    if inputs is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "integration stage has no prepared inputs")
    output, _, decision = accepted_inputs(uow, fenced)
    if inputs["accepted_output_id"] != str(output.id) or inputs["acceptance_decision_id"] != str(decision.id):
        raise error_for(ErrorCode.INVALID_REFERENCE, "integration acceptance changed")
    targets = {(t["repository_id"], t["target_branch"]): t for t in inputs["integration_targets"]}
    for receipt in outcome.get("integration_receipts", []):
        if str(output.id) not in receipt["output_ids"] or receipt["target_branch"] not in {
            t[1] for t in targets
        }:
            raise error_for(ErrorCode.INVALID_REFERENCE, "integration receipt is outside prepared targets")
