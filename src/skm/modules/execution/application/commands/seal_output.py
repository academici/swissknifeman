"""Fence and seal a server-validated immutable output manifest."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import RepositoryId
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._events import cause, emit
from skm.modules.execution.application._incident_gate import bind_repair_output
from skm.modules.execution.application._live_control import require_not_stopping
from skm.modules.execution.application._primitives import save_attempt
from skm.modules.execution.application._worker_dtos import SealOutput, SealOutputResult
from skm.modules.execution.application._worker_evidence import register
from skm.modules.execution.application._worker_protocol import fenced_scope, lock_fenced_context, locked_stage
from skm.modules.execution.domain.attempt import record_output
from skm.modules.execution.domain.ids import StepId
from skm.modules.execution.domain.output import (
    ChangedPath,
    DiffStats,
    Output,
    OutputManifest,
    OutputMount,
    OutputSource,
    manifest_digest,
    matches_path,
    output_tree_digest,
    raw_path_bytes,
)
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES
from skm.modules.execution.domain.step import RoleId, StepState
from skm.modules.execution.domain.task import GATE_KINDS
from skm.modules.execution.ports import (
    EnvironmentRepository,
    EvidenceBindingRepository,
    OutputRepository,
    StepRepository,
)


def path(raw: Any) -> ChangedPath:
    return ChangedPath(
        raw["mount"],
        raw["path"],
        raw["path_bytes"],
        raw["change"],
        raw.get("old_path"),
        raw.get("old_path_bytes"),
        raw["fingerprint"],
    )


def covered(item: ChangedPath, patterns: Any, *, all_names: bool, raw_names: bool = False) -> bool:
    """A rename is inside scope only when both raw names are covered."""
    names = [item.path_bytes] + ([item.old_path_bytes] if item.old_path_bytes else [])
    covered_names: list[bool] = []
    for name in names:
        raw = raw_path_bytes(name)
        non_utf8 = False
        try:
            text = raw.decode("utf-8", "strict")
        except UnicodeDecodeError:
            if not raw_names:
                covered_names.append(False)
                continue
            text, non_utf8 = raw.decode("latin1"), True
        found = False
        for raw_pattern in patterns:
            pattern = raw_pattern.removeprefix(":(exclude,glob)")
            mount, separator, glob = pattern.partition(":")
            if not separator:
                mount, glob = item.mount, pattern
            if non_utf8:
                glob = glob.encode("utf-8").decode("latin1")
            if mount == item.mount and matches_path(text, glob):
                found = True
        covered_names.append(found)
    return all(covered_names) if all_names else any(covered_names)


def _producer(uow: UnitOfWork, cmd: SealOutput, fenced: Any, stage: Any) -> tuple[StepId | None, bool]:
    if cmd["source"] == "executor":
        if not cmd.get("step_id"):
            raise error_for(ErrorCode.INVALID_REFERENCE, "executor seal requires a step")
        step = uow.repo(StepRepository).get(StepId(UUID(cmd["step_id"])))
        reviewer_fix = step.role is RoleId.REVIEWER and step.admission.get("reviewer_with_fix") is True
        if (
            step.stage_record_id != stage.id
            or (step.role is not RoleId.EXECUTOR and not reviewer_fix)
            or step.state is not StepState.STARTED
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "output requires an active writing step")
        return step.id, reviewer_fix
    if stage.stage_type != "prepare_environment" or (
        fenced.task.kind not in GATE_KINDS and fenced.run.kind.value != "review_request"
    ):
        raise error_for(ErrorCode.INVALID_TRANSITION, "range output requires a gate preparation stage")
    return None, False


def handle(cmd: SealOutput, ctx: Any, uow: UnitOfWork) -> SealOutputResult:
    fenced = lock_fenced_context(uow, ctx, cmd["claim"])
    stage = locked_stage(uow, fenced, cmd["stage_record_id"])
    require_not_stopping(stage)
    if stage.state not in ACTIVE_STAGE_STATES:
        raise error_for(ErrorCode.INVALID_TRANSITION, "output requires an active stage")
    step_id, reviewer_fix = _producer(uow, cmd, fenced, stage)
    raw = cmd["manifest"]
    if raw.get("patch_file_version_id") is not None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "patch evidence must be a staged blob")
    env = uow.repo(EnvironmentRepository).for_attempt(fenced.attempt.id)
    if env is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "output requires a prepared environment")
    mounts = tuple(
        OutputMount(
            m["mount"],
            RepositoryId(UUID(m["repository_id"])),
            m["object_format"],
            m["base_commit"],
            m["head_commit"],
            m["tree_sha"],
        )
        for m in raw["mounts"]
    )
    expected = {b.mount: b.repository_id for b in env.baseline}
    baseline = {b.mount: b.commit_sha for b in env.baseline}
    if (
        len(mounts) != len(expected)
        or {m.mount: m.repository_id for m in mounts} != expected
        or any(m.base_commit != baseline[m.mount] for m in mounts)
    ):
        raise error_for(ErrorCode.INVALID_REFERENCE, "output mounts differ from the attempt environment")
    changed = tuple(path(p) for p in raw["changed_paths"])
    candidates = tuple(path(p) for p in raw.get("excluded_paths", ()))
    scope = [f"{p.mount}:{p.pattern}" for p in fenced.task.granted_write_scope]
    exclusions = ctx.config.get("execution.integration.exclude_paths") or ()
    try:
        tree_digest = output_tree_digest(mounts, changed, algorithm=raw["algorithm"])
        output_tree_digest(mounts, candidates)  # validate raw identity of excluded audit entries too
        outside = tuple(p for p in changed if not covered(p, scope, all_names=True))
        if any(covered(p, exclusions, all_names=False, raw_names=True) for p in changed):
            raise ValueError("sealed tree contains excluded paths")
        excluded = tuple(p for p in candidates if covered(p, exclusions, all_names=True, raw_names=True))
    except ValueError as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, str(exc)) from exc
    if raw["tree_digest"] != tree_digest:
        raise error_for(ErrorCode.SCHEMA_INVALID, "output tree digest differs from its raw paths and mounts")
    stats = raw["diff_stats"]
    manifest = OutputManifest(
        raw["algorithm"],
        mounts,
        changed,
        tree_digest,
        outside,
        excluded,
        None,
        DiffStats(stats["files"], stats["insertions"], stats["deletions"]),
        raw["empty"],
    )
    patch_id = None
    if cmd.get("patch") is not None:
        patch_id = register(uow, ctx, fenced, {**cmd["patch"], "role": "patch"})
        manifest = replace(manifest, patch_file_version_id=patch_id)
    md = manifest_digest(manifest)
    repo = uow.repo(OutputRepository)
    previous = repo.latest(fenced.attempt.id)
    if previous is not None and previous.manifest_digest == md and previous.produced_by_step_id == step_id:
        return SealOutputResult(output_id=str(previous.id), manifest_digest=md, seq=previous.seq)
    if reviewer_fix:
        if previous is None or previous.produced_by_step_id == step_id:
            raise error_for(ErrorCode.INVALID_TRANSITION, "reviewer fix requires one new output")
        if outside:
            raise error_for(ErrorCode.WRITE_SCOPE_VIOLATION, "reviewer fix exceeds the task write scope")
        if tuple(m.tree_sha for m in sorted(mounts, key=lambda m: m.mount)) == tuple(
            m.tree_sha for m in sorted(previous.manifest.mounts, key=lambda m: m.mount)
        ):
            raise error_for(ErrorCode.INVALID_TRANSITION, "reviewer fix requires changed output")
    output = Output(
        ctx.ids.new_id(),
        fenced.attempt.id,
        fenced.task.id,
        fenced.run.id,
        1 if previous is None else previous.seq + 1,
        OutputSource(cmd["source"]),
        manifest,
        md,
        fenced.now,
        step_id,
    )
    repo.add(output)
    bind_repair_output(uow, ctx, fenced, output, previous, reviewer_fix)
    if patch_id is not None:
        uow.repo(EvidenceBindingRepository).bind(
            "output", output.id, (patch_id,), artifacts.BindingRole.PATCH
        )
    save_attempt(uow, record_output(fenced.attempt, output, previous=previous))
    emit(
        uow,
        fenced.run,
        "output-sealed",
        {
            "task_id": str(fenced.task.id),
            "attempt_id": str(fenced.attempt.id),
            "output_id": str(output.id),
            "seq": output.seq,
            "source": output.source.value,
            "manifest_digest": md,
            "tree_digest": manifest.tree_digest,
            "files_changed": len(changed),
            "outside_write_scope_count": len(outside),
            "excluded_count": len(excluded),
            "produced_by_step_id": None if step_id is None else str(step_id),
        },
        cause("stage_outcome"),
    )
    return SealOutputResult(output_id=str(output.id), manifest_digest=md, seq=output.seq)


SPEC = CommandSpec(
    name="execution.seal_output",
    dto=SealOutput,
    result=SealOutputResult,
    permission="worker.claim",
    scope_of=None,
    scope_resolver=fenced_scope,
    handler=handle,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    idempotency=IdempotencyMode.REQUIRED,
)
