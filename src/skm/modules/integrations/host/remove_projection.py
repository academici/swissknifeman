"""Host operation ``integrations.host.remove_projection`` (integrations §7.3, §7.6)."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, SkmError, error_for
from skm.kernel.ids import ProjectId, parse_uuid
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.decisions import FileDecisionKind, decide_file, is_safe_relative_path
from skm.modules.integrations.domain.observed import AppliedFileRecord, FileKind
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.projection import (
    ApplyOutcome,
    LocalPreImageKey,
    PlannedWrite,
    ProjectionId,
    ProjectionState,
    build_planned_write,
    is_empty_document,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.commands import RemoveProjection, RemoveProjectionFailedItem
from skm.modules.integrations.generated.host import (
    RemoveProjectionReport,
    remove_projection_report_from_json,
    remove_projection_request_from_json,
)
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.results import RemoveProjectionResult
from skm.modules.integrations.generated.views import AppliedStateView
from skm.modules.integrations.ports import CheckoutFs, LocalCheckoutProjections
from skm.modules.workspace.public import CheckoutBindingId

from .observe import (
    active_sibling_files,
    applied_record_from_view,
    bind_checkout_fs,
    boundaries_overlap,
    boundary_from_wire,
    boundary_to_wire,
    collision_error,
    hold_binding_lock,
    integrations_settings,
    observe_path,
    outcome_to_wire,
    read_pre_image_bytes,
    reconcile_binding_journals,
    reconcile_removal_step,
    register_journal_reconciler,
    remove_binding_journal,
    require_local_apply,
    resolve_checkout_for_mount,
    write_atomic_fs,
    write_binding_journal,
)

__all__ = [
    "SPEC",
    "RemoveProjectionOperation",
    "reconcile_remove_journal",
    "remove_projection",
    "run",
]

_SHARED_SKILLS_PREFIX = ".agents/skills/"


def reconcile_remove_journal(
    ctx: HostContext,
    fs: CheckoutFs,
    binding_id: CheckoutBindingId,
    journal_id: str,
    jdoc: Mapping[str, Any],
    _conflict_suffix: str,
) -> None:
    """Reconcile an interrupted ``kind='remove'`` journal under binding lock."""
    project_id, target = ProjectId(parse_uuid(str(jdoc["project_id"]))), TargetId(str(jdoc["target"]))
    applied_view = ctx.client.ask(
        GetAppliedState(
            project_id=project_id, checkout_binding_id=binding_id, target=cast("Any", target.value)
        )
    )
    assert isinstance(applied_view, AppliedStateView)  # noqa: S101
    if (
        applied_view.projection is None
        or applied_view.projection.state == "removed"
        or applied_view.projection.row_version != jdoc.get("base_row_version")
    ):
        remove_binding_journal(fs, binding_id, journal_id)
        return

    prior_by_path = {r.relative_path: r for r in (applied_record_from_view(v) for v in applied_view.files)}
    removed: list[str] = []
    left_modified: list[str] = list(cast("Sequence[str]", jdoc.get("left_modified", ())))
    failed: list[RemoveProjectionFailedItem] = []

    for entry in cast("Sequence[Mapping[str, Any]]", jdoc.get("entries", ())):
        rel = str(entry["relative_path"])
        raw_bnd = entry.get("boundary")
        bnd = (
            boundary_from_wire(cast("Mapping[str, Any]", raw_bnd))
            if raw_bnd is not None
            else (
                prior_by_path[rel].boundary
                if rel in prior_by_path
                else ManagedBoundary(Ownership.MANAGED_FILE)
            )
        )
        b64 = entry.get("new_bytes_base64")
        new_bytes = None if b64 is None else base64.b64decode(str(b64).encode("ascii"))
        before_w = cast("str | None", entry.get("before_whole_digest"))
        after_w = cast("str | None", entry.get("after_whole_digest"))
        observed, _, _ = observe_path(fs, rel, bnd)
        if (
            observed.outside_root
            or observed.is_symlink
            or observed.file_kind not in (FileKind.REGULAR, FileKind.MISSING)
        ):
            failed.append(
                RemoveProjectionFailedItem(
                    relative_path=rel, error_code=ErrorCode.INTEGRATION_UNSAFE_TARGET.value
                )
            )
            continue
        tag, err = reconcile_removal_step(fs, rel, observed, new_bytes, before_w, after_w)
        if tag == "removed":
            removed.append(rel)
        elif tag == "failed" and err is not None:
            failed.append(RemoveProjectionFailedItem(relative_path=rel, error_code=err))
        else:
            left_modified.append(rel)

    proj_id = (
        parse_uuid(str(jdoc["projection_id"]))
        if "projection_id" in jdoc
        else applied_view.projection.projection_id
    )
    cmd = RemoveProjection(
        project_id=UUID(str(project_id)),
        projection_id=proj_id,
        base_row_version=int(jdoc["base_row_version"]),
        removed=tuple(sorted(set(removed))),
        left_modified=tuple(sorted(set(left_modified) - set(removed))),
        failed=tuple(failed),
    )
    write_binding_journal(
        fs, binding_id, journal_id, {**jdoc, "stage": "recording", "command_payload": cmd.to_json()}
    )
    ctx.client.dispatch(cmd, idempotency_key=str(jdoc["idempotency_key"]))
    remove_binding_journal(fs, binding_id, journal_id)


register_journal_reconciler("remove", reconcile_remove_journal)


def _check_remove_siblings(
    target: TargetId,
    records: Sequence[AppliedFileRecord],
    siblings: Sequence[tuple[TargetId, AppliedFileRecord]],
) -> set[str]:
    shared_skill_keep: set[str] = set()
    for rec in records:
        for sib_target, sib_rec in siblings:
            if sib_rec.relative_path != rec.relative_path:
                continue
            if rec.relative_path.startswith(_SHARED_SKILLS_PREFIX):
                shared_skill_keep.add(rec.relative_path)
                continue
            if boundaries_overlap(sib_rec.boundary, rec.boundary):
                raise collision_error(
                    rec.relative_path,
                    {"targets": [sib_target.value, target.value], "reason": "active_sibling_overlap"},
                )
    return shared_skill_keep


def _created_by_skm(ctx: HostContext, key: LocalPreImageKey) -> bool:
    """The recorded before-state of ``key`` is "did not exist": the first apply created the file."""
    if not ctx.gateways.has(LocalCheckoutProjections):
        return False
    recorded = ctx.gateways.get(LocalCheckoutProjections).read_pre_image(key)
    return recorded is not None and recorded.contents is None and recorded.verified_absence


def _stage_removals(
    ctx: HostContext,
    fs: CheckoutFs,
    records: Sequence[AppliedFileRecord],
    *,
    projection: tuple[ProjectId, CheckoutBindingId, TargetId],
    shared_skill_keep: set[str],
    restore_pre_image: bool,
    conflict_suffix: str,
) -> tuple[
    list[tuple[PlannedWrite, bytes | None, bool]],
    list[str],
    list[str],
    list[RemoveProjectionFailedItem],
]:
    staged: list[tuple[PlannedWrite, bytes | None, bool]] = []
    already_missing: list[str] = []
    left_modified: list[str] = []
    failed: list[RemoveProjectionFailedItem] = []

    for rec in records:
        observed, raw_bytes, _ = observe_path(
            fs, rec.relative_path, rec.boundary, conflict_suffix=conflict_suffix
        )
        safe = is_safe_relative_path(rec.relative_path) and not observed.outside_root
        decision = decide_file(None, rec, observed, safe=safe, force_conflicts=False)
        if decision.kind is FileDecisionKind.UNSAFE_TARGET:
            failed.append(
                RemoveProjectionFailedItem(
                    relative_path=rec.relative_path,
                    error_code=ErrorCode.INTEGRATION_UNSAFE_TARGET.value,
                )
            )
            continue
        if decision.kind is FileDecisionKind.NOOP:
            already_missing.append(rec.relative_path)
            continue
        if decision.kind in (FileDecisionKind.LEAVE_MODIFIED, FileDecisionKind.BOUNDARY_INVALID):
            left_modified.append(rec.relative_path)
            continue
        planned = build_planned_write(decision, desired=None, applied=rec, observed_bytes=raw_bytes)
        if planned is None:
            left_modified.append(rec.relative_path)
            continue
        eff_bytes = planned.new_bytes
        key = LocalPreImageKey(*projection, rec.relative_path)
        if (
            rec.boundary.ownership is Ownership.MERGED_TOML
            and raw_bytes
            and eff_bytes is not None
            and planned.expected_observed_whole_digest != rec.applied_whole_digest
            and any(line not in eff_bytes.splitlines() for line in raw_bytes.splitlines() if b"#" in line)
        ):
            left_modified.append(rec.relative_path)
            continue
        if (
            eff_bytes is not None
            and rec.pre_image_file_version_id is None
            and is_empty_document(rec.boundary, eff_bytes)
            and _created_by_skm(ctx, key)
        ):
            eff_bytes = None  # SKM created it and nothing else lives in it: delete, no empty shell
        elif restore_pre_image and planned.expected_observed_whole_digest == rec.applied_whole_digest:
            original = read_pre_image_bytes(ctx, key, rec.pre_image_file_version_id)
            if original is not None:
                eff_bytes = original
        keep = rec.relative_path in shared_skill_keep
        if (
            eff_bytes is None
            and rec.boundary.ownership is Ownership.MANAGED_FILE
            and ctx.gateways.has(LocalCheckoutProjections)
        ):
            keep |= rec.pre_image_file_version_id is not None or not _created_by_skm(ctx, key)
        staged.append((planned, eff_bytes, keep))

    return staged, already_missing, left_modified, failed


def remove_projection(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    target: TargetId,
    mount: str | None = None,
    restore_pre_image: bool = False,
) -> ApplyOutcome:
    """Safely remove or cut owned spans/keys of ``target`` and record ``RemoveProjection`` (§7.6)."""
    settings = integrations_settings(ctx)
    require_local_apply(ctx, project_id)
    checkout = resolve_checkout_for_mount(ctx, project_id, mount)
    binding_id = CheckoutBindingId(checkout.binding_id)
    fs = bind_checkout_fs(ctx, checkout.local_locator)

    with hold_binding_lock(fs, binding_id):
        reconcile_binding_journals(ctx, fs, binding_id)

        applied_view = ctx.client.ask(
            GetAppliedState(
                project_id=project_id, checkout_binding_id=binding_id, target=cast("Any", target.value)
            )
        )
        assert isinstance(applied_view, AppliedStateView)  # noqa: S101
        if applied_view.projection is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"projection for target {target.value!r} not found",
                details={"kind": "projection", "project_id": str(project_id), "target": target.value},
            )
        if applied_view.projection.state == "removed":
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                f"projection {applied_view.projection.projection_id} is already removed",
                details={
                    "projection_id": str(applied_view.projection.projection_id),
                    "state": applied_view.projection.state,
                },
            )

        projection_id = ProjectionId(applied_view.projection.projection_id)
        base_version = applied_view.projection.row_version
        applied_records = sorted(
            (applied_record_from_view(v) for v in applied_view.files), key=lambda r: r.relative_path
        )
        siblings = active_sibling_files(
            ctx, project_id=project_id, checkout_binding_id=binding_id, exclude_targets=frozenset({target})
        )
        shared_skill_keep = _check_remove_siblings(target, applied_records, siblings)
        staged, already_missing, left_modified, failed = _stage_removals(
            ctx,
            fs,
            applied_records,
            projection=(project_id, binding_id, target),
            shared_skill_keep=shared_skill_keep,
            restore_pre_image=restore_pre_image,
            conflict_suffix=settings.conflict_suffix,
        )

        idem_key = ctx.client.new_idempotency_key()
        journal_id = f"remove_{str(projection_id).replace('-', '')[:24]}_{target.value}"
        journal_doc: dict[str, Any] = {
            "kind": "remove",
            "stage": "mutating",
            "host_id": str(ctx.host_id),
            "project_id": str(project_id),
            "projection_id": str(projection_id),
            "checkout_binding_id": str(binding_id),
            "target": target.value,
            "base_row_version": base_version,
            "idempotency_key": idem_key,
            "entries": [
                {
                    "relative_path": w.relative_path,
                    "boundary": boundary_to_wire(w.boundary),
                    "before_whole_digest": w.expected_observed_whole_digest,
                    "after_whole_digest": None if eff_b is None else sha256_tagged(eff_b),
                    "new_bytes_base64": None if eff_b is None else base64.b64encode(eff_b).decode("ascii"),
                }
                for w, eff_b, keep_shared in staged
                if not keep_shared
            ],
            "left_modified": left_modified,
        }
        write_binding_journal(fs, binding_id, journal_id, journal_doc)

        removed = list(already_missing)
        written: list[str] = []
        for w, eff_b, keep_shared in staged:
            if keep_shared:
                removed.append(w.relative_path)
                continue
            try:
                if eff_b is None:
                    if w.expected_observed_whole_digest is None:
                        raise error_for(ErrorCode.PROJECTION_CONFLICT, "missing expected digest for remove")
                    fs.remove(w.relative_path, expected_whole_digest=w.expected_observed_whole_digest)
                    prune = getattr(fs, "prune_created_parents", None)
                    if prune is not None:
                        prune(w.relative_path)
                else:
                    write_atomic_fs(
                        fs, w.relative_path, eff_b, expected_whole_digest=w.expected_observed_whole_digest
                    )
                removed.append(w.relative_path)
                written.append(w.relative_path)
            except SkmError as exc:
                failed.append(
                    RemoveProjectionFailedItem(relative_path=w.relative_path, error_code=exc.code.value)
                )

        cmd = RemoveProjection(
            project_id=UUID(str(project_id)),
            projection_id=UUID(str(projection_id)),
            base_row_version=base_version,
            removed=tuple(sorted(set(removed))),
            left_modified=tuple(sorted(set(left_modified) - set(removed))),
            failed=tuple(failed),
        )
        write_binding_journal(
            fs,
            binding_id,
            journal_id,
            {**journal_doc, "stage": "recording", "command_payload": cmd.to_json()},
        )
        res = ctx.client.dispatch(cmd, idempotency_key=idem_key)
        assert isinstance(res, RemoveProjectionResult)  # noqa: S101
        remove_binding_journal(fs, binding_id, journal_id)

        return ApplyOutcome(
            target=target,
            projection_id=ProjectionId(res.projection_id),
            state=ProjectionState(res.state),
            written=tuple(sorted(written)),
            conflicts=(),
            failed=tuple((f.relative_path, f.error_code) for f in failed),
            adopted_clean=(),
            left_modified=tuple(sorted(set(left_modified) - set(removed))),
        )


def run(ctx: HostContext, request: object) -> RemoveProjectionReport:
    """HostOperationSpec entrypoint for ``integrations.host.remove_projection``."""
    req = cast("Mapping[str, Any]", remove_projection_request_from_json(request))
    mount = None if req.get("mount") is None else str(req["mount"])
    outcome = remove_projection(
        ctx,
        project_id=ProjectId(parse_uuid(str(req["project_id"]))),
        target=TargetId(str(req["target"])),
        mount=mount,
        restore_pre_image=bool(req.get("restore_pre_image", False)),
    )
    return remove_projection_report_from_json(outcome_to_wire(outcome))


class RemoveProjectionOperation:
    """Host operation class wrapper for ``integrations.host.remove_projection``."""

    name = "integrations.host.remove_projection"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name="integrations.host.remove_projection",
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", dict),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
