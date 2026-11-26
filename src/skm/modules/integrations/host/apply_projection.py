"""Host operation ``integrations.host.apply_projection`` with lock & journal (integrations §7.2)."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Any, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, SkmError, error_for
from skm.kernel.ids import FileVersionId
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.decisions import FileDecisionKind, is_safe_relative_path
from skm.modules.integrations.domain.observed import AppliedFileRecord, FileKind
from skm.modules.integrations.domain.ownership import ManagedBoundary, sha256_tagged
from skm.modules.integrations.domain.projection import (
    ApplyOutcome,
    LocalPreImageKey,
    PlannedWrite,
    ProjectionId,
    ProjectionPlan,
    ProjectionState,
)
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.commands import RecordProjectionAppliedFailedItem
from skm.modules.integrations.generated.host import ApplyProjectionResult, apply_projection_request_from_json
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.results import RecordProjectionAppliedResult
from skm.modules.integrations.generated.views import AppliedStateView
from skm.modules.integrations.ports import CheckoutFs, LocalCheckoutProjections
from skm.modules.workspace.public import CheckoutBindingId

from .adopt_file import ApplyBatchState, reconcile_apply_journal
from .detect_drift import plan_from_wire
from .observe import (
    active_sibling_files,
    applied_file_input,
    applied_record_from_view,
    bind_checkout_fs,
    boundaries_overlap,
    boundary_to_wire,
    capture_pre_image,
    collision_error,
    hold_binding_lock,
    integrations_settings,
    observe_path,
    outcome_to_wire,
    read_pre_image_bytes,
    reconcile_binding_journals,
    record_previous_absence,
    remove_binding_journal,
    require_local_apply,
    resolve_checkout_by_binding,
    write_atomic_fs,
    write_binding_journal,
)
from .plan_projection import collect_plan_meta
from .remove_projection import reconcile_remove_journal

__all__ = [
    "SPEC",
    "ApplyProjectionOperation",
    "apply_projection",
    "outcome_to_wire",
    "reconcile_binding_journals",
    "run",
]

_ = (reconcile_remove_journal, reconcile_apply_journal)
_SHARED_SKILLS_PREFIX = ".agents/skills/"


def _check_apply_collisions(
    plan: ProjectionPlan,
    meta: Mapping[str, tuple[Surface, ManagedBoundary]],
    siblings: Sequence[tuple[TargetId, AppliedFileRecord]],
) -> tuple[set[str], dict[str, str]]:
    shared_skill_keep: set[str] = set()
    shared_skill_digests: dict[str, str] = {}
    write_by_path = {w.relative_path: w for w in plan.writes}
    for dec in plan.decisions:
        if dec.kind in (FileDecisionKind.LEAVE_MODIFIED, FileDecisionKind.UNSAFE_TARGET):
            continue
        if (entry := meta.get(dec.relative_path)) is None:
            continue
        _, bnd = entry
        for sib_target, sib_rec in siblings:
            if sib_rec.relative_path != dec.relative_path:
                continue
            if dec.relative_path.startswith(_SHARED_SKILLS_PREFIX):
                if dec.kind is FileDecisionKind.REMOVE_OWNED:
                    shared_skill_keep.add(dec.relative_path)
                    continue
                w = write_by_path.get(dec.relative_path)
                after_m = w.managed_digest_after if w is not None else dec.expected_observed_managed_digest
                if bnd == sib_rec.boundary and after_m == sib_rec.applied_managed_digest:
                    shared_skill_digests[dec.relative_path] = sib_rec.applied_whole_digest
                    continue
            if boundaries_overlap(sib_rec.boundary, bnd):
                raise collision_error(
                    dec.relative_path,
                    {"targets": [sib_target.value, plan.target.value], "reason": "active_sibling_overlap"},
                )
    return shared_skill_keep, shared_skill_digests


def _stage_writes(
    ctx: HostContext,
    fs: CheckoutFs,
    plan: ProjectionPlan,
    prior_records: Mapping[str, AppliedFileRecord],
    *,
    restore_pre_image: bool,
    conflict_suffix: str,
) -> list[tuple[PlannedWrite, bytes | None, FileVersionId | None, str | None]]:
    staged: list[tuple[PlannedWrite, bytes | None, FileVersionId | None, str | None]] = []
    for w in sorted(plan.writes, key=lambda item: item.relative_path):
        key = LocalPreImageKey(plan.project_id, plan.checkout_binding_id, plan.target, w.relative_path)
        prior = prior_records.get(w.relative_path)
        pre_id = None if prior is None else prior.pre_image_file_version_id
        eff_bytes = w.new_bytes
        if (
            prior is None
            and w.decision is FileDecisionKind.CREATE
            and w.expected_observed_whole_digest is None
        ):
            record_previous_absence(ctx, key)
        if (
            w.decision is FileDecisionKind.REMOVE_OWNED
            and restore_pre_image
            and prior is not None
            and w.expected_observed_whole_digest == prior.applied_whole_digest
        ):
            original = read_pre_image_bytes(ctx, key, prior.pre_image_file_version_id)
            if original is not None:
                eff_bytes = original

        pre_err: str | None = None
        if w.needs_pre_image and pre_id is None:
            obs, raw, _ = observe_path(fs, w.relative_path, w.boundary, conflict_suffix=conflict_suffix)
            if obs.outside_root or obs.is_symlink or obs.file_kind is not FileKind.REGULAR or raw is None:
                pre_err = ErrorCode.INTEGRATION_UNSAFE_TARGET.value
            elif obs.whole_digest != w.expected_observed_whole_digest:
                pre_err = ErrorCode.PROJECTION_CONFLICT.value
            else:
                _, pre_id = capture_pre_image(ctx, key, raw, replace_local=prior is None)
        staged.append((w, eff_bytes, pre_id, pre_err))
    return staged


def _is_hook_exec(surface: Surface, data: bytes | None) -> bool | None:
    return True if (surface is Surface.HOOKS and data is not None and data.startswith(b"#!")) else None


def _write_desired_step(
    fs: CheckoutFs,
    w: PlannedWrite,
    eff_b: bytes | None,
    pre_id: FileVersionId | None,
    acc: ApplyBatchState,
    shared_skill_digests: Mapping[str, str],
) -> None:
    if eff_b is None or w.managed_digest_after is None:
        acc.fail(w.relative_path, ErrorCode.PROJECTION_CONFLICT)
        return
    exec_flag = _is_hook_exec(w.surface, eff_b)
    try:
        write_atomic_fs(
            fs,
            w.write_path,
            eff_b,
            expected_whole_digest=w.expected_observed_whole_digest,
            executable=exec_flag,
        )
    except SkmError as exc:
        sib_w = shared_skill_digests.get(w.relative_path)
        if exc.code is not ErrorCode.PROJECTION_CONFLICT or sib_w != sha256_tagged(eff_b):
            acc.fail(w.relative_path, exc.code)
            return
        try:
            write_atomic_fs(fs, w.write_path, eff_b, expected_whole_digest=sib_w, executable=exec_flag)
        except SkmError as retry_exc:
            acc.fail(w.relative_path, retry_exc.code)
            return
    acc.written.append(w.relative_path)
    acc.verify.append((w.relative_path, w.surface, w.boundary, w.managed_digest_after, pre_id))


def _execute_write_step(
    fs: CheckoutFs,
    step: tuple[PlannedWrite, bytes | None, FileVersionId | None, str | None],
    acc: ApplyBatchState,
    *,
    shared_skill_keep: set[str],
    shared_skill_digests: Mapping[str, str],
) -> None:
    w, eff_b, pre_id, pre_err = step
    if pre_err is not None:
        acc.fail(w.relative_path, pre_err)
        return
    if w.decision in (FileDecisionKind.CREATE, FileDecisionKind.UPDATE):
        _write_desired_step(fs, w, eff_b, pre_id, acc, shared_skill_digests)
    elif w.decision is FileDecisionKind.CONFLICT_WRITE_NEW:
        if eff_b is not None:
            try:
                write_atomic_fs(
                    fs, w.write_path, eff_b, expected_whole_digest=w.expected_observed_whole_digest
                )
            except SkmError as exc:
                acc.failed.append(
                    RecordProjectionAppliedFailedItem(
                        relative_path=w.relative_path, error_code=exc.code.value
                    )
                )
        acc.conflicts.append(w.relative_path)
        acc.keep_prior(w.relative_path)
    elif w.decision is FileDecisionKind.REMOVE_OWNED:
        if w.relative_path in shared_skill_keep:
            acc.removed.append(w.relative_path)
            return
        try:
            if eff_b is None:
                if w.expected_observed_whole_digest is None:
                    raise error_for(ErrorCode.PROJECTION_CONFLICT, "missing expected digest for remove")
                fs.remove(w.relative_path, expected_whole_digest=w.expected_observed_whole_digest)
            else:
                write_atomic_fs(
                    fs, w.relative_path, eff_b, expected_whole_digest=w.expected_observed_whole_digest
                )
            acc.removed.append(w.relative_path)
        except SkmError as exc:
            acc.fail(w.relative_path, exc.code)


def _verify_desired_files(
    ctx: HostContext, fs: CheckoutFs, plan: ProjectionPlan, acc: ApplyBatchState, *, conflict_suffix: str
) -> None:
    for rel, surf, bnd, exp_m, pre_id in acc.verify:
        obs, raw, _ = observe_path(fs, rel, bnd, conflict_suffix=conflict_suffix)
        if obs.outside_root or obs.is_symlink or obs.file_kind is not FileKind.REGULAR:
            acc.fail(rel, ErrorCode.INTEGRATION_UNSAFE_TARGET)
        elif not (obs.exists and obs.boundary_valid and obs.managed_digest == exp_m and obs.whole_digest):
            acc.conflicts.append(rel)
            acc.keep_prior(rel)
        else:
            if rel in acc.adopted and raw is not None and ctx.gateways.has(LocalCheckoutProjections):
                key = LocalPreImageKey(plan.project_id, plan.checkout_binding_id, plan.target, rel)
                ctx.gateways.get(LocalCheckoutProjections).save_pre_image(key, raw, replace=True)
            acc.next_files[rel] = applied_file_input(
                rel, surf, bnd, exp_m, obs.whole_digest, pre_id, acc.renderer_ver
            )


def _classify_plan_decisions(
    plan: ProjectionPlan,
    meta: Mapping[str, tuple[Surface, ManagedBoundary]],
    prior_records: Mapping[str, AppliedFileRecord],
    acc: ApplyBatchState,
) -> None:
    for dec in plan.decisions:
        surf, bnd = meta[dec.relative_path]
        prior = prior_records.get(dec.relative_path)
        prior_pre = None if prior is None else prior.pre_image_file_version_id
        if dec.kind in (FileDecisionKind.NOOP, FileDecisionKind.ADOPT_CLEAN):
            if dec.kind is FileDecisionKind.ADOPT_CLEAN:
                acc.adopted.append(dec.relative_path)
            if dec.expected_observed_managed_digest is not None:
                acc.verify.append(
                    (dec.relative_path, surf, bnd, dec.expected_observed_managed_digest, prior_pre)
                )
        elif dec.kind is FileDecisionKind.LEAVE_MODIFIED:
            acc.left_modified.append(dec.relative_path)
        elif dec.kind in (FileDecisionKind.ADOPT_REQUIRED, FileDecisionKind.BOUNDARY_INVALID):
            acc.conflicts.append(dec.relative_path)
            acc.keep_prior(dec.relative_path)
        elif dec.kind is FileDecisionKind.UNSAFE_TARGET:
            acc.fail(dec.relative_path, ErrorCode.INTEGRATION_UNSAFE_TARGET)


def _build_journal_doc(
    ctx: HostContext,
    plan: ProjectionPlan,
    idem_key: str,
    effective_writes: Sequence[tuple[PlannedWrite, bytes | None, FileVersionId | None, str | None]],
    passthru: Sequence[tuple[str, Surface, ManagedBoundary, str, FileVersionId | None]],
    acc: ApplyBatchState,
) -> dict[str, Any]:
    return {
        "kind": "apply",
        "stage": "mutating",
        "host_id": str(ctx.host_id),
        "project_id": str(plan.project_id),
        "checkout_binding_id": str(plan.checkout_binding_id),
        "target": plan.target.value,
        "plan_digest": plan.plan_digest,
        "desired_digest": plan.desired_digest,
        "inputs_digest": plan.inputs_digest,
        "renderer_version": plan.renderer_version,
        "base_row_version": plan.base_projection_row_version,
        "idempotency_key": idem_key,
        "entries": [
            {
                "relative_path": w.relative_path,
                "write_path": w.write_path,
                "decision": w.decision.value,
                "surface": w.surface.value,
                "boundary": boundary_to_wire(w.boundary),
                "before_whole_digest": w.expected_observed_whole_digest,
                "after_whole_digest": None if eff_b is None else sha256_tagged(eff_b),
                "after_managed_digest": w.managed_digest_after,
                "new_bytes_base64": None if eff_b is None else base64.b64encode(eff_b).decode("ascii"),
                "pre_image_file_version_id": None if pre_id is None else str(pre_id),
                "executable": _is_hook_exec(w.surface, eff_b),
            }
            for w, eff_b, pre_id, _ in effective_writes
        ],
        "passthru_files": [
            {
                "relative_path": rel,
                "surface": surf.value,
                "boundary": boundary_to_wire(bnd),
                "managed_digest": exp_m,
                "pre_image_file_version_id": None if pre_id is None else str(pre_id),
            }
            for rel, surf, bnd, exp_m, pre_id in passthru
        ],
        "static_conflicts": list(acc.conflicts),
        "adopted": list(acc.adopted),
        "left_modified": list(acc.left_modified),
    }


def _apply_one_plan(
    ctx: HostContext,
    fs: CheckoutFs,
    plan: ProjectionPlan,
    *,
    restore_pre_image: bool,
    conflict_suffix: str,
    siblings: Sequence[tuple[TargetId, AppliedFileRecord]],
    batch_desired_skills: frozenset[str],
    provided_meta: Mapping[str, tuple[Surface, ManagedBoundary]] | None,
) -> ApplyOutcome:
    for dec in plan.decisions:
        if not is_safe_relative_path(dec.relative_path):
            raise error_for(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"unsafe relative path in plan: {dec.relative_path!r}",
                details={"relative_path": dec.relative_path, "target": plan.target.value},
            )
    applied_view = ctx.client.ask(
        GetAppliedState(
            project_id=plan.project_id,
            checkout_binding_id=plan.checkout_binding_id,
            target=cast("Any", plan.target.value),
        )
    )
    assert isinstance(applied_view, AppliedStateView)  # noqa: S101
    actual_version = None if applied_view.projection is None else applied_view.projection.row_version
    if actual_version != plan.base_projection_row_version:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "projection row_version changed since plan was computed",
            details={"expected": plan.base_projection_row_version, "actual": actual_version},
        )

    prior_records = {r.relative_path: r for r in (applied_record_from_view(v) for v in applied_view.files)}
    meta = collect_plan_meta(ctx, plan, prior_records=prior_records, provided=provided_meta)
    sib_keep, shared_skill_digests = _check_apply_collisions(plan, meta, siblings)
    shared_skill_keep = sib_keep | set(batch_desired_skills)
    effective_writes = _stage_writes(
        ctx, fs, plan, prior_records, restore_pre_image=restore_pre_image, conflict_suffix=conflict_suffix
    )
    acc = ApplyBatchState(prior_records, plan.renderer_version)
    _classify_plan_decisions(plan, meta, prior_records, acc)

    idem_key = ctx.client.new_idempotency_key()
    journal_id = f"{plan.plan_digest.removeprefix('sha256:')[:24]}_{plan.target.value}"
    jdoc = _build_journal_doc(ctx, plan, idem_key, effective_writes, list(acc.verify), acc)
    write_binding_journal(fs, plan.checkout_binding_id, journal_id, jdoc)

    for step in effective_writes:
        _execute_write_step(
            fs, step, acc, shared_skill_keep=shared_skill_keep, shared_skill_digests=shared_skill_digests
        )
    _verify_desired_files(ctx, fs, plan, acc, conflict_suffix=conflict_suffix)

    clean_adopted = [p for p in acc.adopted if p in acc.next_files and p not in acc.conflicts]
    cmd = acc.to_command(
        project_id=plan.project_id,
        binding_id=plan.checkout_binding_id,
        target=plan.target,
        desired_digest=plan.desired_digest,
        inputs_digest=plan.inputs_digest,
        base_row_version=plan.base_projection_row_version,
        adopted=clean_adopted,
    )
    write_binding_journal(
        fs,
        plan.checkout_binding_id,
        journal_id,
        {**jdoc, "stage": "recording", "command_payload": cmd.to_json()},
    )
    res = ctx.client.dispatch(cmd, idempotency_key=idem_key)
    assert isinstance(res, RecordProjectionAppliedResult)  # noqa: S101
    remove_binding_journal(fs, plan.checkout_binding_id, journal_id)
    return ApplyOutcome(
        target=plan.target,
        projection_id=ProjectionId(res.projection_id),
        state=ProjectionState(res.state),
        written=tuple(sorted(acc.written)),
        conflicts=tuple(sorted(set(acc.conflicts))),
        failed=tuple((f.relative_path, f.error_code) for f in acc.failed),
        adopted_clean=tuple(sorted(set(clean_adopted))),
        left_modified=tuple(sorted(set(acc.left_modified))),
    )


def apply_projection(
    ctx: HostContext,
    plans: Sequence[ProjectionPlan],
    *,
    restore_pre_image: bool = False,
    meta_by_target: Mapping[TargetId, Mapping[str, tuple[Surface, ManagedBoundary]]] | None = None,
    expected_locators: Mapping[CheckoutBindingId, str] | None = None,
) -> tuple[ApplyOutcome, ...]:
    """Execute ``ProjectionPlan`` writes under per-binding ``FileLock`` and record bus outcomes (§7.2)."""
    if not plans:
        return ()
    suffix = integrations_settings(ctx).conflict_suffix
    outcomes: list[ApplyOutcome] = []
    by_binding: dict[CheckoutBindingId, list[ProjectionPlan]] = {}
    for plan in plans:
        by_binding.setdefault(plan.checkout_binding_id, []).append(plan)

    for project_id in dict.fromkeys(plan.project_id for plan in plans):
        require_local_apply(ctx, project_id)
    for binding_id, group in by_binding.items():
        checkout = resolve_checkout_by_binding(ctx, group[0].project_id, binding_id)
        expected = None if expected_locators is None else expected_locators.get(binding_id)
        if expected is not None and checkout.local_locator != expected:
            raise Conflict(
                ErrorCode.VERSION_CONFLICT,
                "Checkout binding moved during projection synchronization",
                details={"binding_id": str(binding_id)},
            )
        fs = bind_checkout_fs(ctx, checkout.local_locator)
        with hold_binding_lock(fs, binding_id):
            reconcile_binding_journals(ctx, fs, binding_id)
            for idx, plan in enumerate(group):
                siblings = active_sibling_files(
                    ctx,
                    project_id=plan.project_id,
                    checkout_binding_id=binding_id,
                    exclude_targets=frozenset({plan.target}),
                )
                sib_targets = {s[0] for s in siblings}
                other_skills = frozenset(
                    dec.relative_path
                    for j, other in enumerate(group)
                    if j != idx and other.target not in sib_targets
                    for dec in other.decisions
                    if dec.relative_path.startswith(_SHARED_SKILLS_PREFIX)
                    and dec.kind not in (FileDecisionKind.REMOVE_OWNED, FileDecisionKind.LEAVE_MODIFIED)
                )
                outcomes.append(
                    _apply_one_plan(
                        ctx,
                        fs,
                        plan,
                        restore_pre_image=restore_pre_image,
                        conflict_suffix=suffix,
                        siblings=siblings,
                        batch_desired_skills=other_skills,
                        provided_meta=None if meta_by_target is None else meta_by_target.get(plan.target),
                    )
                )
    return tuple(outcomes)


def run(ctx: HostContext, request: object) -> ApplyProjectionResult:
    """HostOperationSpec entrypoint for ``integrations.host.apply_projection``."""
    req = cast("Mapping[str, Any]", apply_projection_request_from_json(request))
    decoded = [plan_from_wire(raw) for raw in cast("Sequence[Mapping[str, Any]]", req["plans"])]
    outcomes = apply_projection(
        ctx,
        [item[0] for item in decoded],
        restore_pre_image=bool(req.get("restore_pre_image", False)),
        meta_by_target={plan.target: meta for plan, meta in decoded},
    )
    return [outcome_to_wire(item) for item in outcomes]


class ApplyProjectionOperation:
    """Host operation class wrapper for ``integrations.host.apply_projection``."""

    name = "integrations.host.apply_projection"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name="integrations.host.apply_projection",
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", list),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
