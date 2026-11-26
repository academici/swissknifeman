"""Host operation ``integrations.host.adopt_file`` & apply journal reconciler (integrations §7.2-§7.3)."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, SkmError, ValidationFailed, error_for
from skm.kernel.ids import FileVersionId, ProjectId, parse_uuid
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.conflict_names import conflict_path
from skm.modules.integrations.domain.contracts import AdoptOutcome
from skm.modules.integrations.domain.decisions import FileDecisionKind, decide_file, is_safe_relative_path
from skm.modules.integrations.domain.observed import AppliedFileRecord, FileKind, ObservedFile
from skm.modules.integrations.domain.ownership import ManagedBoundary
from skm.modules.integrations.domain.projection import LocalPreImageKey
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.commands import (
    RecordProjectionApplied,
    RecordProjectionAppliedDefsAppliedFileInput,
    RecordProjectionAppliedFailedItem,
)
from skm.modules.integrations.generated.host import (
    AdoptFileResult,
    adopt_file_request_from_json,
    adopt_file_result_from_json,
)
from skm.modules.integrations.generated.queries import GetAppliedState, GetDesiredProjection
from skm.modules.integrations.generated.results import RecordProjectionAppliedResult
from skm.modules.integrations.generated.views import AppliedStateView, DesiredProjectionView
from skm.modules.integrations.ports import CheckoutFs, IntegrationTargetRegistry
from skm.modules.workspace.public import CheckoutBindingId

from .observe import (
    active_sibling_files,
    applied_file_input,
    applied_record_from_view,
    bind_checkout_fs,
    boundaries_overlap,
    boundary_from_wire,
    capture_pre_image,
    collision_error,
    hold_binding_lock,
    integrations_settings,
    observe_path,
    prior_file_input,
    reconcile_binding_journals,
    reconcile_removal_step,
    register_journal_reconciler,
    remove_binding_journal,
    require_local_apply,
    resolve_checkout_for_mount,
    write_atomic_fs,
    write_binding_journal,
)
from .plan_projection import assemble_desired, inputs_from_view
from .remove_projection import reconcile_remove_journal

__all__ = [
    "SPEC",
    "AdoptFileOperation",
    "ApplyBatchState",
    "adopt_file",
    "reconcile_apply_journal",
    "run",
]

_ = reconcile_remove_journal
_SHARED_SKILLS_PREFIX = ".agents/skills/"


class ApplyBatchState:
    """Mutable batch accumulator shared by ``apply_projection`` and crash-journal reconciliation."""

    def __init__(
        self,
        prior_by_path: Mapping[str, AppliedFileRecord],
        renderer_ver: str,
        *,
        conflicts: Sequence[str] = (),
        adopted: Sequence[str] = (),
        left_modified: Sequence[str] = (),
    ) -> None:
        self.prior_by_path = prior_by_path
        self.renderer_ver = renderer_ver
        self.next_files: dict[str, RecordProjectionAppliedDefsAppliedFileInput] = {}
        self.written: list[str] = []
        self.removed: list[str] = []
        self.conflicts: list[str] = list(conflicts)
        self.failed: list[RecordProjectionAppliedFailedItem] = []
        self.adopted: list[str] = list(adopted)
        self.left_modified: list[str] = list(left_modified)
        self.verify: list[tuple[str, Surface, ManagedBoundary, str, FileVersionId | None]] = []

    def keep_prior(self, rel: str) -> None:
        if (prior := self.prior_by_path.get(rel)) is not None:
            self.next_files[rel] = prior_file_input(prior)

    def fail(self, rel: str, code: ErrorCode | str) -> None:
        raw = code.value if isinstance(code, ErrorCode) else code
        self.failed.append(RecordProjectionAppliedFailedItem(relative_path=rel, error_code=raw))
        self.keep_prior(rel)

    def to_command(
        self,
        *,
        project_id: ProjectId,
        binding_id: CheckoutBindingId,
        target: TargetId,
        desired_digest: str,
        inputs_digest: str,
        base_row_version: int | None,
        adopted: Sequence[str] | None = None,
    ) -> RecordProjectionApplied:
        clean_adopted = self.adopted if adopted is None else adopted
        return RecordProjectionApplied(
            project_id=UUID(str(project_id)),
            checkout_binding_id=UUID(str(binding_id)),
            target=cast("Any", target.value),
            desired_digest=desired_digest,
            inputs_digest=inputs_digest,
            renderer_version=self.renderer_ver,
            base_row_version=base_row_version,
            files=tuple(self.next_files[k] for k in sorted(self.next_files)),
            removed=tuple(sorted(set(self.removed))),
            conflicts=tuple(sorted(set(self.conflicts))),
            failed=tuple(self.failed),
            adopted=tuple(sorted(set(clean_adopted))),
            left_modified=tuple(sorted(set(self.left_modified))),
        )


def _is_unsafe_obs(obs: ObservedFile) -> bool:
    return obs.outside_root or obs.is_symlink or obs.file_kind not in (FileKind.REGULAR, FileKind.MISSING)


def _reconcile_create_or_update(
    fs: CheckoutFs,
    entry: Mapping[str, Any],
    observed: ObservedFile,
    c_digest: str | None,
    new_bytes: bytes | None,
    acc: ApplyBatchState,
    *,
    conflict_suffix: str,
) -> None:
    rel = str(entry["relative_path"])
    if new_bytes is None:
        acc.fail(rel, ErrorCode.PROJECTION_CONFLICT)
        return
    bnd = boundary_from_wire(cast("Mapping[str, Any]", entry["boundary"]))
    surf, after_m = Surface(str(entry["surface"])), str(entry["after_managed_digest"])
    raw_pre = entry.get("pre_image_file_version_id")
    pre_id = None if raw_pre is None else FileVersionId(parse_uuid(str(raw_pre)))
    before_w = cast("str | None", entry.get("before_whole_digest"))
    after_w = cast("str | None", entry.get("after_whole_digest"))

    if observed.exists and observed.whole_digest == after_w:
        acc.next_files[rel] = applied_file_input(
            rel, surf, bnd, after_m, str(observed.whole_digest), pre_id, acc.renderer_ver
        )
    elif (before_w is None and not observed.exists) or (
        observed.exists and observed.whole_digest == before_w
    ):
        try:
            w_whole = write_atomic_fs(
                fs, rel, new_bytes, expected_whole_digest=before_w, executable=entry.get("executable")
            )
            acc.next_files[rel] = applied_file_input(
                rel, surf, bnd, after_m, w_whole, pre_id, acc.renderer_ver
            )
        except SkmError as exc:
            acc.fail(rel, exc.code)
    else:
        with suppress(SkmError):
            write_atomic_fs(
                fs, conflict_path(rel, suffix=conflict_suffix), new_bytes, expected_whole_digest=c_digest
            )
        acc.conflicts.append(rel)
        acc.keep_prior(rel)


def _reconcile_apply_entry(
    fs: CheckoutFs, entry: Mapping[str, Any], acc: ApplyBatchState, *, conflict_suffix: str
) -> None:
    rel, dec = str(entry["relative_path"]), str(entry["decision"])
    bnd = boundary_from_wire(cast("Mapping[str, Any]", entry["boundary"]))
    b64 = entry.get("new_bytes_base64")
    new_bytes = None if b64 is None else base64.b64decode(str(b64).encode("ascii"))
    observed, _, c_digest = observe_path(fs, rel, bnd, conflict_suffix=conflict_suffix)
    if _is_unsafe_obs(observed):
        acc.fail(rel, ErrorCode.INTEGRATION_UNSAFE_TARGET)
        return
    if dec in ("create", "update"):
        _reconcile_create_or_update(
            fs, entry, observed, c_digest, new_bytes, acc, conflict_suffix=conflict_suffix
        )
    elif dec == "conflict_write_new":
        if new_bytes is not None:
            try:
                write_atomic_fs(fs, str(entry["write_path"]), new_bytes, expected_whole_digest=c_digest)
            except SkmError as exc:
                acc.failed.append(
                    RecordProjectionAppliedFailedItem(relative_path=rel, error_code=exc.code.value)
                )
        acc.conflicts.append(rel)
        acc.keep_prior(rel)
    elif dec == "remove_owned":
        before_w = cast("str | None", entry.get("before_whole_digest"))
        after_w = cast("str | None", entry.get("after_whole_digest"))
        tag, err = reconcile_removal_step(fs, rel, observed, new_bytes, before_w, after_w)
        if tag == "removed":
            acc.removed.append(rel)
        elif tag == "failed" and err is not None:
            acc.fail(rel, err)
        else:
            acc.left_modified.append(rel)


def reconcile_apply_journal(
    ctx: HostContext,
    fs: CheckoutFs,
    binding_id: CheckoutBindingId,
    journal_id: str,
    jdoc: Mapping[str, Any],
    conflict_suffix: str,
) -> None:
    """Reconcile an interrupted ``kind='apply'`` journal under binding lock."""
    project_id, target = ProjectId(parse_uuid(str(jdoc["project_id"]))), TargetId(str(jdoc["target"]))
    applied_view = ctx.client.ask(
        GetAppliedState(
            project_id=project_id, checkout_binding_id=binding_id, target=cast("Any", target.value)
        )
    )
    assert isinstance(applied_view, AppliedStateView)  # noqa: S101
    current_version = None if applied_view.projection is None else applied_view.projection.row_version
    if current_version != jdoc.get("base_row_version"):
        remove_binding_journal(fs, binding_id, journal_id)
        return

    prior_by_path = {r.relative_path: r for r in (applied_record_from_view(v) for v in applied_view.files)}
    acc = ApplyBatchState(
        prior_by_path,
        str(jdoc["renderer_version"]),
        conflicts=cast("Sequence[str]", jdoc.get("static_conflicts", ())),
        adopted=cast("Sequence[str]", jdoc.get("adopted", ())),
        left_modified=cast("Sequence[str]", jdoc.get("left_modified", ())),
    )
    for c_rel in acc.conflicts:
        acc.keep_prior(c_rel)
    for entry in cast("Sequence[Mapping[str, Any]]", jdoc.get("entries", ())):
        _reconcile_apply_entry(fs, entry, acc, conflict_suffix=conflict_suffix)

    for p_entry in cast("Sequence[Mapping[str, Any]]", jdoc.get("passthru_files", ())):
        rel = str(p_entry["relative_path"])
        bnd = boundary_from_wire(cast("Mapping[str, Any]", p_entry["boundary"]))
        surf, exp_m = Surface(str(p_entry["surface"])), str(p_entry["managed_digest"])
        raw_pre = p_entry.get("pre_image_file_version_id")
        pre_id = None if raw_pre is None else FileVersionId(parse_uuid(str(raw_pre)))
        obs, _, _ = observe_path(fs, rel, bnd, conflict_suffix=conflict_suffix)
        if obs.exists and obs.boundary_valid and obs.managed_digest == exp_m and obs.whole_digest is not None:
            acc.next_files[rel] = applied_file_input(
                rel, surf, bnd, exp_m, obs.whole_digest, pre_id, acc.renderer_ver
            )
        else:
            acc.conflicts.append(rel)
            acc.keep_prior(rel)

    cmd = acc.to_command(
        project_id=project_id,
        binding_id=binding_id,
        target=target,
        desired_digest=str(jdoc["desired_digest"]),
        inputs_digest=str(jdoc["inputs_digest"]),
        base_row_version=cast("int | None", jdoc.get("base_row_version")),
    )
    write_binding_journal(
        fs, binding_id, journal_id, {**jdoc, "stage": "recording", "command_payload": cmd.to_json()}
    )
    ctx.client.dispatch(cmd, idempotency_key=str(jdoc["idempotency_key"]))
    remove_binding_journal(fs, binding_id, journal_id)


register_journal_reconciler("apply", reconcile_apply_journal)


def adopt_file(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    target: TargetId,
    relative_path: str,
    reason: str,
    mount: str | None = None,
) -> AdoptOutcome:
    """Adopt an unmanaged existing file in ``ADOPT_REQUIRED`` state, capturing its pre-image (§7.3)."""
    if not reason or not reason.strip():
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "adoption reason must not be empty", details={"field": "reason"}
        )
    if not is_safe_relative_path(relative_path) or any(
        seg.lower() == ".git" for seg in relative_path.split("/")
    ):
        raise error_for(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"cannot adopt unsafe path {relative_path!r}",
            details={"relative_path": relative_path, "target": target.value},
        )

    settings = integrations_settings(ctx)
    require_local_apply(ctx, project_id)
    checkout = resolve_checkout_for_mount(ctx, project_id, mount)
    binding_id = CheckoutBindingId(checkout.binding_id)
    fs = bind_checkout_fs(ctx, checkout.local_locator)
    adapter = ctx.gateways.get(IntegrationTargetRegistry).get(target)

    with hold_binding_lock(fs, binding_id):
        reconcile_binding_journals(ctx, fs, binding_id)
        t_val = cast("Any", target.value)
        desired_view = ctx.client.ask(
            GetDesiredProjection(project_id=project_id, checkout_binding_id=binding_id, target=t_val)
        )
        assert isinstance(desired_view, DesiredProjectionView)  # noqa: S101
        applied_view = ctx.client.ask(
            GetAppliedState(project_id=project_id, checkout_binding_id=binding_id, target=t_val)
        )
        assert isinstance(applied_view, AppliedStateView)  # noqa: S101

        inputs = inputs_from_view(desired_view)
        desired_proj = assemble_desired(
            target,
            inputs,
            adapter.render(inputs),
            renderer_version=adapter.renderer_version,
            capabilities=adapter.capabilities(),
            max_desired_bytes=settings.desired.max_bytes,
        )
        desired_map = {f.relative_path: f for f in desired_proj.files}
        applied_records = {
            r.relative_path: r for r in (applied_record_from_view(v) for v in applied_view.files)
        }
        dfile, afile = desired_map.get(relative_path), applied_records.get(relative_path)
        if dfile is None:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                f"path {relative_path!r} is not part of desired projection for target {target.value!r}",
                details={"relative_path": relative_path, "target": target.value, "decision": "not_desired"},
            )

        for sib_target, sib_rec in active_sibling_files(
            ctx, project_id=project_id, checkout_binding_id=binding_id, exclude_targets=frozenset({target})
        ):
            if sib_rec.relative_path != relative_path:
                continue
            if relative_path.startswith(_SHARED_SKILLS_PREFIX) and sib_rec.boundary == dfile.boundary:
                continue
            if boundaries_overlap(sib_rec.boundary, dfile.boundary):
                raise collision_error(
                    relative_path,
                    {"targets": [sib_target.value, target.value], "reason": "active_sibling_overlap"},
                )

        observed, raw_bytes, _ = observe_path(
            fs, relative_path, dfile.boundary, conflict_suffix=settings.conflict_suffix
        )
        decision = decide_file(
            dfile,
            afile,
            observed,
            safe=is_safe_relative_path(relative_path) and not observed.outside_root,
            force_conflicts=False,
        )
        if decision.kind is FileDecisionKind.UNSAFE_TARGET:
            raise error_for(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"cannot adopt unsafe target {relative_path!r}",
                details={"relative_path": relative_path, "target": target.value},
            )
        if decision.kind is not FileDecisionKind.ADOPT_REQUIRED:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                f"path {relative_path!r} has decision {decision.kind.value!r}, expected 'adopt_required'",
                details={
                    "relative_path": relative_path,
                    "target": target.value,
                    "decision": decision.kind.value,
                },
            )
        if (
            observed.file_kind is not FileKind.REGULAR
            or raw_bytes is None
            or observed.managed_digest is None
            or observed.whole_digest is None
        ):
            raise error_for(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"observed file {relative_path!r} is not readable as regular file",
                details={"relative_path": relative_path, "target": target.value},
            )

        pre_image_id, project_version = capture_pre_image(
            ctx,
            LocalPreImageKey(project_id, binding_id, target, relative_path),
            raw_bytes,
            replace_local=True,
            reason=f"adopt:{reason.strip()}",
        )
        next_files: dict[str, RecordProjectionAppliedDefsAppliedFileInput] = {
            path: prior_file_input(rec) for path, rec in applied_records.items()
        }
        next_files[relative_path] = applied_file_input(
            relative_path,
            dfile.surface,
            dfile.boundary,
            observed.managed_digest,
            observed.whole_digest,
            project_version,
            adapter.renderer_version,
        )
        other_unapplied = [p for p in sorted(desired_map) if p != relative_path and p not in next_files]
        base_version = None if applied_view.projection is None else applied_view.projection.row_version
        cmd = RecordProjectionApplied(
            project_id=UUID(str(project_id)),
            checkout_binding_id=UUID(str(binding_id)),
            target=t_val,
            desired_digest=desired_proj.desired_digest,
            inputs_digest=inputs.inputs_digest,
            renderer_version=adapter.renderer_version,
            base_row_version=base_version,
            files=tuple(next_files[k] for k in sorted(next_files)),
            removed=(),
            conflicts=tuple(other_unapplied),
            failed=(),
            adopted=(relative_path,),
            left_modified=(),
        )
        res = ctx.client.dispatch(cmd, idempotency_key=ctx.client.new_idempotency_key())
        assert isinstance(res, RecordProjectionAppliedResult)  # noqa: S101
        return {
            "project_id": str(project_id),
            "checkout_binding_id": str(binding_id),
            "target": target.value,
            "projection_id": str(res.projection_id),
            "state": str(res.state),
            "relative_path": relative_path,
            "pre_image_file_version_id": str(pre_image_id),
            "pre_image_storage": "machine" if project_version is None else "project",
            "applied_managed_digest": observed.managed_digest,
            "applied_whole_digest": observed.whole_digest,
            "reason": reason.strip(),
        }


def run(ctx: HostContext, request: object) -> AdoptFileResult:
    """HostOperationSpec entrypoint for ``integrations.host.adopt_file``."""
    req = cast("Mapping[str, Any]", adopt_file_request_from_json(request))
    outcome = adopt_file(
        ctx,
        project_id=ProjectId(parse_uuid(str(req["project_id"]))),
        target=TargetId(str(req["target"])),
        relative_path=str(req["relative_path"]),
        reason=str(req["reason"]),
        mount=None if req.get("mount") is None else str(req["mount"]),
    )
    return adopt_file_result_from_json(dict(outcome))


class AdoptFileOperation:
    """Host operation class wrapper for ``integrations.host.adopt_file``."""

    name = "integrations.host.adopt_file"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name="integrations.host.adopt_file",
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", dict),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
