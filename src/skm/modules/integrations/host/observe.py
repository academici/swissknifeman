"""Host-side checkout observation and shared binding/journal/pre-image helpers (integrations §7)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext, suppress
from dataclasses import replace
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, SkmError, error_for
from skm.kernel.ids import FileVersionId, ProjectId, WorkspaceId, parse_uuid
from skm.modules.artifacts.public import AddFile, AddFileResult
from skm.modules.integrations.domain.conflict_names import DEFAULT_CONFLICT_SUFFIX, conflict_path
from skm.modules.integrations.domain.decisions import is_safe_relative_path
from skm.modules.integrations.domain.merged_json import OwnedKeyPath
from skm.modules.integrations.domain.observed import AppliedFileRecord, FileKind, ObservedFile, observe_bytes
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.projection import ApplyOutcome, LocalPreImageKey, ProjectionId
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated import settings as _gen_settings
from skm.modules.integrations.generated.commands import (
    RecordProjectionApplied,
    RecordProjectionAppliedDefsAppliedFileInput,
    RecordProjectionAppliedDefsOwnedKeyPath,
    RemoveProjection,
)
from skm.modules.integrations.generated.host import (
    ApplyProjectionResultDefsApplyOutcome,
    apply_projection_result_defs_apply_outcome_from_json,
)
from skm.modules.integrations.generated.queries import GetAppliedState, ListProjections
from skm.modules.integrations.generated.settings import IntegrationsSettings
from skm.modules.integrations.generated.views import (
    AppliedStateView,
    AppliedStateViewDefsAppliedFileRecord,
    AppliedStateViewDefsManagedBoundary,
    ProjectionSummaryView,
    ProjectionsView,
)
from skm.modules.integrations.ports import CheckoutFs, LocalCheckoutProjections
from skm.modules.workspace.public import (
    CheckoutBindingId,
    CheckoutLocationView,
    GetProject,
    ProjectView,
    ResolveCheckout,
    checkout_id_from_locator,
)

__all__ = [
    "active_sibling_files",
    "applied_file_input",
    "applied_record_from_view",
    "bind_checkout_fs",
    "boundaries_overlap",
    "boundary_from_view",
    "boundary_from_wire",
    "boundary_to_wire",
    "capture_pre_image",
    "collision_error",
    "has_regular_conflict",
    "hold_binding_lock",
    "integrations_settings",
    "list_all_projections",
    "list_binding_journals",
    "list_local_projections",
    "observe",
    "observe_path",
    "outcome_to_wire",
    "prior_file_input",
    "read_pre_image_bytes",
    "reconcile_binding_journals",
    "reconcile_removal_step",
    "record_previous_absence",
    "register_journal_reconciler",
    "remove_binding_journal",
    "require_local_apply",
    "resolve_checkout_by_binding",
    "resolve_checkout_for_mount",
    "resolve_project_workspace_id",
    "write_atomic_fs",
    "write_binding_journal",
]

type JournalReconciler = Callable[
    [HostContext, CheckoutFs, CheckoutBindingId, str, Mapping[str, Any], str],
    None,
]

_JOURNAL_RECONCILERS: dict[str, JournalReconciler] = {}

_PRE_IMAGE_ACK: tuple[str, ...] = (
    "CS-SECRET-NAME",
    "CS-SECRET-CONTENT",
    "CS-ABSOLUTE-PATH",
    "CS-HOME-PATH",
    "CS-BINARY",
    "CS-NOT-SCANNED",
    "CS-SYMLINK",
    "CS-MEDIA-MISMATCH",
    "CS-EXECUTABLE",
)


def register_journal_reconciler(kind: str, reconciler: JournalReconciler) -> None:
    """Register a crash-journal reconciler for ``kind`` (``'apply'`` or ``'remove'``)."""
    _JOURNAL_RECONCILERS[kind] = reconciler


def outcome_to_wire(outcome: ApplyOutcome) -> ApplyProjectionResultDefsApplyOutcome:
    """Encode ``ApplyOutcome`` into wire JSON dictionary."""
    return apply_projection_result_defs_apply_outcome_from_json(
        {
            "target": outcome.target.value,
            "projection_id": str(outcome.projection_id),
            "state": outcome.state.value,
            "written": list(outcome.written),
            "conflicts": list(outcome.conflicts),
            "failed": [[path, code] for path, code in outcome.failed],
            "adopted_clean": list(outcome.adopted_clean),
            "left_modified": list(outcome.left_modified),
        }
    )


def reconcile_removal_step(
    fs: CheckoutFs,
    rel: str,
    observed: ObservedFile,
    new_bytes: bytes | None,
    before_w: str | None,
    after_w: str | None,
) -> tuple[str, str | None]:
    """Reconcile a single ``remove_owned`` or ``remove`` journal entry under CAS."""
    if (after_w is None and not observed.exists) or (
        after_w is not None and observed.exists and observed.whole_digest == after_w
    ):
        return ("removed", None)
    if observed.exists and before_w is not None and observed.whole_digest == before_w:
        try:
            if new_bytes is None:
                fs.remove(rel, expected_whole_digest=before_w)
            else:
                write_atomic_fs(fs, rel, new_bytes, expected_whole_digest=before_w)
        except SkmError as exc:
            return ("failed", exc.code.value)
        else:
            return ("removed", None)
    return ("left_modified", None)


def reconcile_binding_journals(ctx: HostContext, fs: CheckoutFs, binding_id: CheckoutBindingId) -> None:
    """Replay or reconcile incomplete crash journals for ``binding_id`` under binding lock (§7.2)."""
    suffix = integrations_settings(ctx).conflict_suffix
    for journal_id, jdoc in list_binding_journals(fs, binding_id):
        stage = str(jdoc.get("stage", ""))
        kind = str(jdoc.get("kind", ""))
        idem = str(jdoc["idempotency_key"])
        if stage == "recording":
            if kind == "apply":
                ctx.client.dispatch(
                    RecordProjectionApplied.from_json(jdoc["command_payload"]), idempotency_key=idem
                )
            elif kind == "remove":
                ctx.client.dispatch(RemoveProjection.from_json(jdoc["command_payload"]), idempotency_key=idem)
            remove_binding_journal(fs, binding_id, journal_id)
        elif stage == "mutating" and (reconciler := _JOURNAL_RECONCILERS.get(kind)) is not None:
            reconciler(ctx, fs, binding_id, journal_id, jdoc, suffix)


def _collect_settings_defaults(cls: Any, out: dict[str, Any]) -> None:
    for _wire, _name, spec, _req, default, _has_def, key in cls._FIELDS:
        if key:
            out.setdefault(key, default)
        elif spec[0] == "ref":
            _collect_settings_defaults(getattr(_gen_settings, spec[3][1]), out)


def integrations_settings(ctx: HostContext) -> IntegrationsSettings:
    """Resolve ``IntegrationsSettings`` from ``ctx.config`` with schema defaults."""
    cfg = ctx.config
    section_fn = getattr(cfg, "section", None)
    if callable(section_fn):
        with suppress(Exception):
            res = section_fn(IntegrationsSettings)
            if isinstance(res, IntegrationsSettings):
                return res
    merged: dict[str, Any] = {}
    _collect_settings_defaults(IntegrationsSettings, merged)
    if isinstance(cfg, Mapping):
        merged.update(cast("Mapping[str, Any]", cfg))
    return IntegrationsSettings.from_settings(merged)


def resolve_checkout_for_mount(
    ctx: HostContext, project_id: ProjectId, mount: str | None
) -> CheckoutLocationView:
    """Resolve the checkout binding on ``ctx.host_id`` for ``project_id`` and ``mount``."""
    mount_name = mount if mount is not None and mount != "" else "main"
    view = ctx.client.ask(ResolveCheckout(project_id=project_id, mount_name=mount_name, host_id=ctx.host_id))
    assert isinstance(view, CheckoutLocationView)  # noqa: S101
    if view.state != "active":
        raise PreconditionFailed(
            ErrorCode.CHECKOUT_UNBOUND,
            f"checkout binding for mount {mount_name!r} is {view.state}",
            details={"mount": mount_name, "state": view.state, "binding_id": str(view.binding_id)},
        )
    if ctx.gateways.has(LocalCheckoutProjections):
        binding_id, root = ctx.gateways.get(LocalCheckoutProjections).resolve(project_id, mount_name)
        if view.binding_id != binding_id:
            raise PreconditionFailed(ErrorCode.CHECKOUT_MISMATCH, "Checkout changed during projection lookup")
        return replace(view, local_locator=str(root))
    if checkout_id_from_locator(view.local_locator) is not None:
        raise PreconditionFailed(ErrorCode.CHECKOUT_UNBOUND, "A verified local checkout is required")
    return view


def require_local_apply(ctx: HostContext, project_id: ProjectId) -> None:
    if ctx.gateways.has(LocalCheckoutProjections):
        ctx.gateways.get(LocalCheckoutProjections).require_apply(project_id)


def resolve_checkout_by_binding(
    ctx: HostContext, project_id: ProjectId, binding_id: CheckoutBindingId
) -> CheckoutLocationView:
    """Resolve the active ``CheckoutLocationView`` matching ``binding_id`` on ``ctx.host_id``."""
    proj = ctx.client.ask(GetProject(project_id=project_id))
    assert isinstance(proj, ProjectView)  # noqa: S101
    for mount_name in [m.mount_name for m in proj.mounts] or ["main"]:
        try:
            loc = resolve_checkout_for_mount(ctx, project_id, mount_name)
        except (NotFound, PreconditionFailed):
            continue
        if UUID(str(loc.binding_id)) == UUID(str(binding_id)):
            return loc
    raise PreconditionFailed(
        ErrorCode.CHECKOUT_UNBOUND,
        f"checkout binding {binding_id} is not active on host {ctx.host_id}",
        details={"binding_id": str(binding_id), "host_id": str(ctx.host_id)},
    )


def bind_checkout_fs(ctx: HostContext, local_locator: str) -> CheckoutFs:
    """Return a ``CheckoutFs`` rooted at ``local_locator``."""
    base_fs = ctx.gateways.get(CheckoutFs)
    binder = getattr(base_fs, "for_checkout", None)
    return cast("CheckoutFs", binder(local_locator)) if callable(binder) else base_fs


def hold_binding_lock(fs: CheckoutFs, binding_id: CheckoutBindingId) -> AbstractContextManager[Any]:
    """Enter the exclusive lock for ``binding_id`` when supported by ``fs``."""
    holder = getattr(fs, "hold_binding_lock", None)
    return cast("AbstractContextManager[Any]", holder(str(binding_id))) if callable(holder) else nullcontext()


def write_binding_journal(
    fs: CheckoutFs, binding_id: CheckoutBindingId, journal_id: str, doc: Mapping[str, Any]
) -> None:
    """Serialize and durably persist a journal document for ``binding_id``."""
    writer = getattr(fs, "write_journal", None)
    if callable(writer):
        payload = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        writer(str(binding_id), journal_id, payload)


def list_binding_journals(
    fs: CheckoutFs, binding_id: CheckoutBindingId
) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Load pending journal documents for ``binding_id``."""
    lister = getattr(fs, "list_journals", None)
    if not callable(lister):
        return ()
    raw_entries = cast("tuple[tuple[str, bytes], ...]", lister(str(binding_id)))
    parsed: list[tuple[str, dict[str, Any]]] = []
    for journal_id, payload in raw_entries:
        data = json.loads(payload.decode("utf-8"))
        if isinstance(data, dict):
            parsed.append((journal_id, cast("dict[str, Any]", data)))
    return tuple(parsed)


def remove_binding_journal(fs: CheckoutFs, binding_id: CheckoutBindingId, journal_id: str) -> None:
    """Remove a completed journal entry for ``binding_id``."""
    remover = getattr(fs, "remove_journal", None)
    if callable(remover):
        remover(str(binding_id), journal_id)


def write_atomic_fs(
    fs: CheckoutFs,
    relative_path: str,
    data: bytes,
    *,
    expected_whole_digest: str | None,
    executable: bool | None = None,
) -> str:
    """Invoke ``fs.write_atomic`` passing ``executable`` when the implementation accepts it."""
    writer: Callable[..., str] = fs.write_atomic
    try:
        return writer(relative_path, data, expected_whole_digest=expected_whole_digest, executable=executable)
    except TypeError:
        return fs.write_atomic(relative_path, data, expected_whole_digest=expected_whole_digest)


def observe_path(
    fs: CheckoutFs,
    relative_path: str,
    boundary: ManagedBoundary,
    *,
    conflict_suffix: str = DEFAULT_CONFLICT_SUFFIX,
) -> tuple[ObservedFile, bytes | None, str | None]:
    """Observe ``relative_path`` on ``fs`` and return ``(observed, raw_bytes, conflict_whole_digest)``."""
    has_conflict = False
    conflict_digest: str | None = None
    if is_safe_relative_path(relative_path) and not any(
        seg.lower() == ".git" for seg in relative_path.split("/")
    ):
        cpath = conflict_path(relative_path, suffix=conflict_suffix)
        conflict_obs = _read_entry(fs, cpath)
        if conflict_obs[0] is FileKind.REGULAR and conflict_obs[1] is not None:
            has_conflict = True
            conflict_digest = sha256_tagged(conflict_obs[1])
        elif conflict_obs[0] is not FileKind.MISSING:
            has_conflict = True

    kind, raw, is_symlink, outside_root = _read_entry(fs, relative_path)
    observed = observe_bytes(
        relative_path,
        raw,
        boundary,
        is_symlink=is_symlink,
        has_conflict_file=has_conflict,
        file_kind=kind,
        outside_root=outside_root,
    )
    return observed, raw, conflict_digest


def has_regular_conflict(fs: CheckoutFs, relative_path: str) -> bool:
    kind, raw, _, _ = _read_entry(fs, relative_path)
    return kind is FileKind.REGULAR and raw is not None


def observe(
    fs: CheckoutFs,
    relative_path: str,
    boundary: ManagedBoundary,
    *,
    conflict_suffix: str = DEFAULT_CONFLICT_SUFFIX,
) -> ObservedFile:
    """Observe ``relative_path`` on ``fs`` into a pure ``ObservedFile`` value."""
    return observe_path(fs, relative_path, boundary, conflict_suffix=conflict_suffix)[0]


def _read_entry(fs: CheckoutFs, relative_path: str) -> tuple[FileKind, bytes | None, bool, bool]:
    if not is_safe_relative_path(relative_path) or any(
        seg.lower() == ".git" for seg in relative_path.split("/")
    ):
        return FileKind.OTHER, None, False, True
    entry_fn = getattr(fs, "observe_entry", None)
    if callable(entry_fn):
        return cast("tuple[FileKind, bytes | None, bool, bool]", entry_fn(relative_path))
    st = fs.stat(relative_path)
    if st.is_symlink:
        return FileKind.SYMLINK, None, True, False
    if not st.exists:
        return FileKind.MISSING, None, False, False
    try:
        raw = fs.read(relative_path)
    except SkmError as exc:
        if exc.code is ErrorCode.INTEGRATION_UNSAFE_TARGET:
            return FileKind.OTHER, None, False, True
        raise
    if raw is None:
        return FileKind.MISSING, None, False, False
    return FileKind.REGULAR, raw, False, False


def boundary_to_wire(boundary: ManagedBoundary) -> dict[str, Any]:
    """Encode ``ManagedBoundary`` into wire dictionary representation."""
    out: dict[str, Any] = {"ownership": boundary.ownership.value}
    if boundary.block_ids:
        out["block_ids"] = list(boundary.block_ids)
    if boundary.owned_keys:
        out["owned_keys"] = [{"path": list(item.path), "mode": item.mode} for item in boundary.owned_keys]
    return out


def boundary_from_wire(data: Mapping[str, Any]) -> ManagedBoundary:
    """Decode wire dictionary representation into ``ManagedBoundary``."""
    raw_owned = cast("Sequence[Mapping[str, Any]]", data.get("owned_keys") or ())
    owned = tuple(
        OwnedKeyPath(
            path=tuple(str(seg) for seg in cast("Sequence[Any]", item["path"])),
            mode=cast("Any", str(item["mode"])),
        )
        for item in raw_owned
    )
    raw_blocks = cast("Sequence[Any]", data.get("block_ids") or ())
    return ManagedBoundary(
        ownership=Ownership(str(data["ownership"])),
        block_ids=tuple(str(b) for b in raw_blocks),
        owned_keys=owned,
    )


def boundary_from_view(view: AppliedStateViewDefsManagedBoundary) -> ManagedBoundary:
    owned = tuple(OwnedKeyPath(path=tuple(item.path), mode=item.mode) for item in (view.owned_keys or ()))
    return ManagedBoundary(
        ownership=Ownership(view.ownership),
        block_ids=tuple(view.block_ids or ()),
        owned_keys=owned,
    )


def applied_record_from_view(view: AppliedStateViewDefsAppliedFileRecord) -> AppliedFileRecord:
    return AppliedFileRecord(
        projection_id=ProjectionId(view.projection_id),
        relative_path=view.relative_path,
        surface=Surface(view.surface),
        boundary=boundary_from_view(view.boundary),
        applied_managed_digest=view.applied_managed_digest,
        applied_whole_digest=view.applied_whole_digest,
        pre_image_file_version_id=(
            None if view.pre_image_file_version_id is None else FileVersionId(view.pre_image_file_version_id)
        ),
        renderer=view.renderer,
        applied_at=view.applied_at,
    )


def applied_file_input(
    relative_path: str,
    surface: Surface,
    boundary: ManagedBoundary,
    applied_managed_digest: str,
    applied_whole_digest: str,
    pre_image_file_version_id: FileVersionId | None,
    renderer: str,
) -> RecordProjectionAppliedDefsAppliedFileInput:
    """Build bus ``RecordProjectionAppliedDefsAppliedFileInput`` from domain values."""
    return RecordProjectionAppliedDefsAppliedFileInput(
        relative_path=relative_path,
        surface=cast("Any", surface.value),
        ownership=cast("Any", boundary.ownership.value),
        block_ids=tuple(boundary.block_ids),
        owned_keys=tuple(
            RecordProjectionAppliedDefsOwnedKeyPath(path=tuple(k.path), mode=k.mode)
            for k in boundary.owned_keys
        ),
        applied_managed_digest=applied_managed_digest,
        applied_whole_digest=applied_whole_digest,
        pre_image_file_version_id=(
            None if pre_image_file_version_id is None else UUID(str(pre_image_file_version_id))
        ),
        renderer=(
            renderer
            if "." in renderer
            else f"{renderer.partition('@')[0]}.{surface.value}@{renderer.partition('@')[2] or '1'}"
        ),
    )


def prior_file_input(rec: AppliedFileRecord) -> RecordProjectionAppliedDefsAppliedFileInput:
    """Convert an existing ``AppliedFileRecord`` back into ``RecordProjectionAppliedDefsAppliedFileInput``."""
    return applied_file_input(
        rec.relative_path,
        rec.surface,
        rec.boundary,
        rec.applied_managed_digest,
        rec.applied_whole_digest,
        rec.pre_image_file_version_id,
        rec.renderer,
    )


def boundaries_overlap(first: ManagedBoundary, second: ManagedBoundary) -> bool:
    """Return True when two ``ManagedBoundary`` definitions overlap on the same file."""
    if first.ownership is Ownership.MANAGED_FILE or second.ownership is Ownership.MANAGED_FILE:
        return True
    if first.ownership is not second.ownership:
        return True
    if first.ownership is Ownership.MANAGED_BLOCK:
        return bool(set(first.block_ids) & set(second.block_ids))
    for left in first.owned_keys:
        for right in second.owned_keys:
            prefix_len = min(len(left.path), len(right.path))
            if left.path[:prefix_len] == right.path[:prefix_len]:
                return True
    return False


def list_all_projections(ctx: HostContext, project_id: ProjectId) -> tuple[ProjectionSummaryView, ...]:
    """Fetch every page of ``ListProjections`` for ``project_id``."""
    collected: list[ProjectionSummaryView] = []
    cursor: str | None = None
    while True:
        page = ctx.client.ask(ListProjections(project_id=project_id, after=cursor, limit=100))
        assert isinstance(page, ProjectionsView)  # noqa: S101
        collected.extend(page.items)
        if not page.has_more or page.next_cursor is None:
            break
        cursor = page.next_cursor
    return tuple(collected)


def list_local_projections(ctx: HostContext, query: ListProjections) -> ProjectionsView:
    """Screen a project page through the caller's live current-host bindings."""
    view = ctx.client.ask(query)
    assert isinstance(view, ProjectionsView)  # noqa: S101
    if not ctx.gateways.has(LocalCheckoutProjections):
        return view
    project = ctx.client.ask(GetProject(project_id=query.project_id))
    assert isinstance(project, ProjectView)  # noqa: S101
    bindings: set[UUID] = set()
    for mount in project.mounts:
        try:
            binding = resolve_checkout_for_mount(ctx, ProjectId(query.project_id), mount.mount_name)
        except PreconditionFailed as exc:
            if exc.code not in {ErrorCode.CHECKOUT_UNBOUND, ErrorCode.CHECKOUT_MISMATCH}:
                raise
        else:
            bindings.add(binding.binding_id)
    return replace(
        view,
        items=tuple(
            item
            for item in view.items
            if item.host_id == ctx.host_id and item.checkout_binding_id in bindings
        ),
    )


def active_sibling_files(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    checkout_binding_id: CheckoutBindingId,
    exclude_targets: frozenset[TargetId],
) -> tuple[tuple[TargetId, AppliedFileRecord], ...]:
    """Return applied file records of active sibling projections on ``checkout_binding_id``."""
    siblings: list[tuple[TargetId, AppliedFileRecord]] = []
    for summary in list_all_projections(ctx, project_id):
        if summary.checkout_binding_id != checkout_binding_id or summary.state == "removed":
            continue
        target = TargetId(summary.target)
        if target in exclude_targets:
            continue
        applied = ctx.client.ask(
            GetAppliedState(
                project_id=project_id, checkout_binding_id=checkout_binding_id, target=summary.target
            )
        )
        assert isinstance(applied, AppliedStateView)  # noqa: S101
        siblings.extend((target, applied_record_from_view(item)) for item in applied.files)
    return tuple(siblings)


def resolve_project_workspace_id(ctx: HostContext, project_id: ProjectId) -> WorkspaceId:
    """Resolve the owning ``WorkspaceId`` of ``project_id`` through ``workspace.GetProject``."""
    view = ctx.client.ask(GetProject(project_id=project_id))
    assert isinstance(view, ProjectView)  # noqa: S101
    return WorkspaceId(view.workspace_id)


def capture_pre_image(
    ctx: HostContext,
    key: LocalPreImageKey,
    raw_bytes: bytes,
    *,
    replace_local: bool,
    reason: str = "integration pre-image",
) -> tuple[UUID, FileVersionId | None]:
    """Capture machine-managed originals locally and keep legacy artifact restoration available."""
    if ctx.gateways.has(LocalCheckoutProjections):
        local = ctx.gateways.get(LocalCheckoutProjections)
        return local.save_pre_image(key, raw_bytes, replace=replace_local), None
    project_id = key.project_id
    workspace_id = resolve_project_workspace_id(ctx, project_id)
    relative_path = key.relative_path
    leaf_name = relative_path.rsplit("/", 1)[-1] or "pre-image.bin"
    safe_filename = "".join(ch if ch.isalnum() or ch in (".", "-", "_") else "_" for ch in leaf_name)
    if safe_filename.startswith("."):
        safe_filename = f"dot{safe_filename}"
    if not safe_filename:
        safe_filename = "pre_image.bin"

    staged = ctx.client.upload_blob(
        workspace_id,
        (raw_bytes,),
        size=len(raw_bytes),
        expected_digest=sha256_tagged(raw_bytes),
        media_type="application/octet-stream",
    )
    add_cmd = AddFile.from_json(
        {
            "workspace_id": str(workspace_id),
            "project_id": str(project_id),
            "title": f"pre-image:{relative_path}",
            "origin": "capture",
            "blob": staged.to_json(),
            "original_filename": safe_filename,
            "source": {"kind": "capture", "ref": relative_path},
            "classification": "internal",
            "declared_media_type": "application/octet-stream",
            "description": reason,
            "acknowledge": list(_PRE_IMAGE_ACK),
        }
    )
    result = ctx.client.dispatch(add_cmd, idempotency_key=ctx.client.new_idempotency_key())
    assert isinstance(result, AddFileResult)  # noqa: S101
    version_id = FileVersionId(parse_uuid(str(result.file_version_id)))
    return version_id, version_id


def read_pre_image_bytes(
    ctx: HostContext, key: LocalPreImageKey, project_version: FileVersionId | None
) -> bytes | None:
    """Read the current caller's local original or an older explicit project artifact."""
    if project_version is not None:
        with ctx.client.open_file_version_content(project_version) as stream:
            return stream.read()
    if ctx.gateways.has(LocalCheckoutProjections):
        local = ctx.gateways.get(LocalCheckoutProjections).read_pre_image(key)
        if local is None:
            raise error_for(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                "Projection original is unavailable in the current caller's local state",
                details={"relative_path": key.relative_path, "reason": "pre_image_unavailable"},
            )
        return local.contents
    return None


def record_previous_absence(ctx: HostContext, key: LocalPreImageKey) -> None:
    if ctx.gateways.has(LocalCheckoutProjections):
        ctx.gateways.get(LocalCheckoutProjections).save_pre_image(key, None, replace=True)


def collision_error(relative_path: str, details: Mapping[str, Any]) -> SkmError:
    """Build the canonical ``INTEGRATION_PATH_COLLISION`` error."""
    return error_for(
        ErrorCode.INTEGRATION_PATH_COLLISION,
        f"overlapping integration ownership on {relative_path!r}",
        details={"relative_path": relative_path, **details},
    )
