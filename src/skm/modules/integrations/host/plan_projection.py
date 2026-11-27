"""Host operation ``integrations.host.plan_projection`` (integrations §5.1, §7.1)."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from skm.application_bus.host import HostContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, error_for
from skm.kernel.ids import ProjectId, parse_uuid
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.conflict_names import conflict_path
from skm.modules.integrations.domain.contracts import Diagnostic
from skm.modules.integrations.domain.decisions import (
    FileDecision,
    FileDecisionKind,
    decide_file,
    is_safe_relative_path,
    is_shared_projection_path,
)
from skm.modules.integrations.domain.desired import (
    DesiredFile,
    DesiredProjection,
    HostSubscriptionEvent,
    ProjectionInputs,
    unsupported_surface_diagnostics,
)
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind, HookSurfaceId
from skm.modules.integrations.domain.hook_rules import HookMode
from skm.modules.integrations.domain.managed_block import replace_blocks
from skm.modules.integrations.domain.observed import AppliedFileRecord, extract_managed_digest
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.presets import (
    Preset,
    dart_package_name,
    php_package_slug,
    preset_renderer,
    read_preset,
)
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.projection import PlannedWrite, ProjectionPlan, build_planned_write
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.generated.documents import HostProjectionPlan, host_projection_plan_from_json
from skm.modules.integrations.generated.host import PlanProjectionResult, plan_projection_request_from_json
from skm.modules.integrations.generated.queries import GetAppliedState, GetDesiredProjection
from skm.modules.integrations.generated.views import AppliedStateView, DesiredProjectionView
from skm.modules.integrations.ports import CheckoutFs, IntegrationTargetRegistry
from skm.modules.workspace.public import CheckoutBindingId, CheckoutLocationView

from .observe import (
    active_sibling_files,
    applied_record_from_view,
    bind_checkout_fs,
    boundaries_overlap,
    boundary_from_wire,
    boundary_to_wire,
    collision_error,
    integrations_settings,
    observe_path,
    resolve_checkout_by_binding,
    resolve_checkout_for_mount,
)

__all__ = [
    "SPEC",
    "PlanProjectionOperation",
    "assemble_desired",
    "boundary_from_wire",
    "boundary_to_wire",
    "checkout_inputs",
    "collect_plan_meta",
    "compute_plan_digest",
    "inputs_from_view",
    "plan_projection",
    "plan_to_wire",
    "run",
]

_HOOK_SURFACE_BY_KEY: dict[str, HookSurfaceId] = {
    **{sid.value.rpartition(".")[2]: sid for sid in HookSurfaceId},
    **{sid.value: sid for sid in HookSurfaceId},
}


@dataclass(frozen=True, slots=True)
class _TargetStage:
    target: TargetId
    inputs_digest: str
    renderer_version: str
    desired_proj: DesiredProjection
    applied_view: AppliedStateView


def _json_clone(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_clone(v) for k, v in cast("Mapping[Any, Any]", value).items()}
    if isinstance(value, (list, tuple)):
        return [_json_clone(v) for v in cast("Sequence[Any]", value)]
    return value


def inputs_from_view(view: DesiredProjectionView) -> ProjectionInputs:
    """Convert bus ``DesiredProjectionView`` into pure domain ``ProjectionInputs``."""
    sub_events = tuple(
        HostSubscriptionEvent(HookEventKind(item.kind), tuple(HookClass(c) for c in item.classes))
        for item in view.host_subscription_events
    )
    return ProjectionInputs(
        project_id=ProjectId(view.project_id),
        target=TargetId(view.target),
        instructions_core=cast("dict[str, Any]", _json_clone(view.instructions_core)),
        instructions_project=cast("dict[str, Any]", _json_clone(view.instructions_project)),
        skills=tuple(cast("dict[str, Any]", _json_clone(s)) for s in view.skills),
        permissions=cast("dict[str, Any]", _json_clone(view.permissions)),
        profile=PermissionProfile(view.profile),
        hook_modes={
            sid: HookMode(v)
            for k, v in view.hook_modes.items()
            if (sid := _HOOK_SURFACE_BY_KEY.get(k)) is not None
        },
        host_subscription_events=sub_events,
        mcp_servers={str(k): cast("dict[str, Any]", _json_clone(v)) for k, v in view.mcp_servers.items()},
        agents=tuple(cast("dict[str, Any]", _json_clone(a)) for a in view.agents),
        inputs_digest=view.inputs_digest,
        config_generation=view.config_generation,
        diagnostics=tuple(cast("dict[str, Any]", _json_clone(d)) for d in view.diagnostics),
    )


def checkout_inputs(view: DesiredProjectionView, fs: CheckoutFs) -> ProjectionInputs:
    inputs = inputs_from_view(view)
    preset = read_preset(inputs.instructions_project.get("preset"))
    if preset not in ("php-package", "dart-package"):
        return inputs
    from .doctor import read_text

    if preset == "dart-package":
        key, value = "package_name", dart_package_name(read_text(fs, "pubspec.yaml"))
    else:
        key, value = "package_slug", php_package_slug(read_text(fs, "composer.json"))
    if value is None or value == inputs.instructions_project.get(key):
        return inputs
    return replace(
        inputs,
        instructions_project={**inputs.instructions_project, key: value},
        inputs_digest=sha256_tagged(json.dumps([inputs.inputs_digest, key, value]).encode()),
    )


def assemble_desired(
    target: TargetId,
    inputs: ProjectionInputs,
    files: Sequence[DesiredFile],
    *,
    renderer_version: str,
    capabilities: TargetCapabilities | None = None,
    max_desired_bytes: int = 8_388_608,
) -> DesiredProjection:
    """Validate rendered target files and compute canonical ``desired_digest`` (integrations §5.1)."""
    supported: list[DesiredFile] = []
    seen_paths: set[str] = set()
    total_bytes = 0
    for item in files:
        if (
            capabilities is not None
            and capabilities.surfaces.get(item.surface, SurfaceSupport.UNSUPPORTED)
            is SurfaceSupport.UNSUPPORTED
        ):
            continue
        if not is_safe_relative_path(item.relative_path) or any(
            seg.lower() == ".git" for seg in item.relative_path.split("/")
        ):
            raise error_for(
                ErrorCode.INTEGRATION_UNSAFE_TARGET,
                f"rendered file path {item.relative_path!r} is unsafe",
                details={"relative_path": item.relative_path, "target": target.value},
            )
        if item.relative_path in seen_paths:
            raise collision_error(
                item.relative_path, {"target": target.value, "reason": "duplicate_target_path"}
            )
        total_bytes += len(item.managed_bytes)
        if total_bytes > max_desired_bytes:
            raise PreconditionFailed(
                ErrorCode.INTEGRATION_DESIRED_TOO_LARGE,
                f"desired projection bytes ({total_bytes}) exceed max_bytes ({max_desired_bytes})",
                details={"bytes": total_bytes, "max_bytes": max_desired_bytes, "target": target.value},
            )
        seen_paths.add(item.relative_path)
        supported.append(item)

    ordered = tuple(sorted(supported, key=lambda f: f.relative_path))
    extra = () if capabilities is None else unsupported_surface_diagnostics(target, inputs, capabilities)
    digest_payload = [
        inputs.inputs_digest,
        renderer_version,
        [[f.relative_path, f.managed_digest, boundary_to_wire(f.boundary)] for f in ordered],
    ]
    canonical = json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return DesiredProjection(
        project_id=inputs.project_id,
        targets=(target,),
        files=ordered,
        diagnostics=(*inputs.diagnostics, *extra),
        desired_digest=sha256_tagged(canonical.encode("utf-8")),
    )


def _check_collisions(
    stages: Sequence[_TargetStage], siblings: Sequence[tuple[TargetId, AppliedFileRecord]]
) -> None:
    by_path = {rec.relative_path: (t, rec.boundary, rec.applied_managed_digest) for t, rec in siblings}
    for stage in stages:
        for dfile in stage.desired_proj.files:
            if (prev := by_path.get(dfile.relative_path)) is None:
                by_path[dfile.relative_path] = (stage.target, dfile.boundary, dfile.managed_digest)
                continue
            prev_target, prev_boundary, prev_digest = prev
            if is_shared_projection_path(dfile.relative_path, dfile.boundary):
                if dfile.boundary == prev_boundary and dfile.managed_digest == prev_digest:
                    continue
                raise collision_error(
                    dfile.relative_path,
                    {
                        "targets": [prev_target.value, stage.target.value],
                        "reason": "shared_skill_content_mismatch",
                    },
                )
            if boundaries_overlap(prev_boundary, dfile.boundary):
                raise collision_error(
                    dfile.relative_path,
                    {
                        "targets": [prev_target.value, stage.target.value],
                        "reason": "cross_target_boundary_overlap",
                    },
                )


def compute_plan_digest(plan: ProjectionPlan) -> str:
    """Compute canonical ``sha256:...`` digest of a ``ProjectionPlan``."""
    payload = {
        "project_id": str(plan.project_id),
        "checkout_binding_id": str(plan.checkout_binding_id),
        "target": plan.target.value,
        "desired_digest": plan.desired_digest,
        "inputs_digest": plan.inputs_digest,
        "renderer_version": plan.renderer_version,
        "base_projection_row_version": plan.base_projection_row_version,
        "decisions": [
            (
                d.relative_path,
                d.kind.value,
                d.diagnostic,
                d.expected_observed_managed_digest,
                d.expected_observed_whole_digest,
            )
            for d in plan.decisions
        ],
        "writes": [
            (
                w.relative_path,
                w.write_path,
                w.decision.value,
                w.expected_observed_whole_digest,
                w.needs_pre_image,
                w.managed_digest_after,
                None if w.new_bytes is None else sha256_tagged(w.new_bytes),
            )
            for w in plan.writes
        ],
    }
    return sha256_tagged(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def _plan_single_target(
    fs: CheckoutFs,
    *,
    project_id: ProjectId,
    checkout_binding_id: CheckoutBindingId,
    stage: _TargetStage,
    conflict_suffix: str,
    force_conflicts: bool,
) -> ProjectionPlan:
    desired_map = {f.relative_path: f for f in stage.desired_proj.files}
    applied_records = {
        r.relative_path: r for r in (applied_record_from_view(v) for v in stage.applied_view.files)
    }
    base_ver = None if stage.applied_view.projection is None else stage.applied_view.projection.row_version
    decisions: list[FileDecision] = []
    writes: list[PlannedWrite] = []
    extra_diags: list[Diagnostic] = list(stage.desired_proj.diagnostics)

    for rel_path in sorted(set(desired_map) | set(applied_records)):
        dfile, afile = desired_map.get(rel_path), applied_records.get(rel_path)
        boundary = dfile.boundary if dfile is not None else cast("Any", afile).boundary
        observed, raw_bytes, c_digest = observe_path(fs, rel_path, boundary, conflict_suffix=conflict_suffix)
        safe = is_safe_relative_path(rel_path) and not observed.outside_root
        if (
            safe
            and raw_bytes is not None
            and afile is not None
            and dfile is not None
            and afile.boundary.ownership is dfile.boundary.ownership is Ownership.MANAGED_BLOCK
            and afile.boundary != dfile.boundary
            and not observed.boundary_valid
            and extract_managed_digest(raw_bytes, afile.boundary) == (afile.applied_managed_digest, True)
        ):
            raw_bytes = replace_blocks(raw_bytes, b"", afile.boundary.block_ids)
            observed = replace(observed, boundary_valid=True, managed_digest=afile.applied_managed_digest)
        decision = decide_file(dfile, afile, observed, safe=safe, force_conflicts=force_conflicts)
        decisions.append(decision)
        if decision.diagnostic is not None:
            extra_diags.append(
                {
                    "code": decision.diagnostic,
                    "severity": "warning",
                    "target": stage.target.value,
                    "path": rel_path,
                    "decision": decision.kind.value,
                }
            )
        planned = build_planned_write(decision, desired=dfile, applied=afile, observed_bytes=raw_bytes)
        if planned is not None:
            if planned.decision is FileDecisionKind.CONFLICT_WRITE_NEW:
                planned = replace(
                    planned,
                    write_path=conflict_path(rel_path, suffix=conflict_suffix),
                    expected_observed_whole_digest=c_digest,
                    needs_pre_image=False,
                )
            writes.append(planned)

    draft = ProjectionPlan(
        project_id=project_id,
        checkout_binding_id=checkout_binding_id,
        target=stage.target,
        desired_digest=stage.desired_proj.desired_digest,
        inputs_digest=stage.inputs_digest,
        renderer_version=stage.renderer_version,
        base_projection_row_version=base_ver,
        decisions=tuple(decisions),
        writes=tuple(writes),
        diagnostics=tuple(extra_diags),
        plan_digest="",
    )
    return replace(draft, plan_digest=compute_plan_digest(draft))


def plan_projection(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    mount: str | None = None,
    targets: tuple[TargetId, ...] | None = None,
    force_conflicts: bool = False,
    preset: Preset | None = None,
    resolved_checkout: CheckoutLocationView | None = None,
) -> tuple[ProjectionPlan, ...]:
    """Build read-only ``ProjectionPlan`` records for each requested target (integrations §7.1)."""
    settings = integrations_settings(ctx)
    resolved_targets = targets if targets else tuple(TargetId(t) for t in settings.targets)
    checkout = resolved_checkout or resolve_checkout_for_mount(ctx, project_id, mount)
    binding_id = CheckoutBindingId(checkout.binding_id)
    fs = bind_checkout_fs(ctx, checkout.local_locator)
    registry = ctx.gateways.get(IntegrationTargetRegistry)

    staged: list[_TargetStage] = []
    for target in resolved_targets:
        adapter, t_val = registry.get(target), cast("Any", target.value)
        desired_view = ctx.client.ask(
            GetDesiredProjection(
                project_id=project_id, checkout_binding_id=binding_id, target=t_val, preset=preset
            )
        )
        assert isinstance(desired_view, DesiredProjectionView)  # noqa: S101
        applied_view = ctx.client.ask(
            GetAppliedState(project_id=project_id, checkout_binding_id=binding_id, target=t_val)
        )
        assert isinstance(applied_view, AppliedStateView)  # noqa: S101
        inputs = checkout_inputs(desired_view, fs)
        renderer_version = preset_renderer(
            adapter.renderer_version, read_preset(inputs.instructions_project.get("preset"))
        )
        desired_proj = assemble_desired(
            target,
            inputs,
            adapter.render(inputs),
            renderer_version=renderer_version,
            capabilities=adapter.capabilities(),
            max_desired_bytes=settings.desired.max_bytes,
        )
        staged.append(
            _TargetStage(target, inputs.inputs_digest, renderer_version, desired_proj, applied_view)
        )

    siblings = active_sibling_files(
        ctx,
        project_id=project_id,
        checkout_binding_id=binding_id,
        exclude_targets=frozenset(resolved_targets),
    )
    _check_collisions(staged, siblings)
    return tuple(
        _plan_single_target(
            fs,
            project_id=project_id,
            checkout_binding_id=binding_id,
            stage=stage,
            conflict_suffix=settings.conflict_suffix,
            force_conflicts=force_conflicts,
        )
        for stage in staged
    )


def collect_plan_meta(
    ctx: HostContext,
    plan: ProjectionPlan,
    *,
    prior_records: Mapping[str, AppliedFileRecord] | None = None,
    provided: Mapping[str, tuple[Surface, ManagedBoundary]] | None = None,
    preset: Preset | None = None,
) -> dict[str, tuple[Surface, ManagedBoundary]]:
    """Resolve ``(Surface, ManagedBoundary)`` for every decision path in ``plan``."""
    meta: dict[str, tuple[Surface, ManagedBoundary]] = dict(provided) if provided else {}
    for w in plan.writes:
        meta.setdefault(w.relative_path, (w.surface, w.boundary))
    if prior_records is not None:
        for path, rec in prior_records.items():
            meta.setdefault(path, (rec.surface, rec.boundary))
    missing = [d.relative_path for d in plan.decisions if d.relative_path not in meta]
    if not missing:
        return meta
    t_val = cast("Any", plan.target.value)
    if prior_records is None:
        applied = ctx.client.ask(
            GetAppliedState(
                project_id=plan.project_id, checkout_binding_id=plan.checkout_binding_id, target=t_val
            )
        )
        assert isinstance(applied, AppliedStateView)  # noqa: S101
        for item in applied.files:
            rec = applied_record_from_view(item)
            meta.setdefault(rec.relative_path, (rec.surface, rec.boundary))
    if any(p not in meta for p in missing):
        desired_view = ctx.client.ask(
            GetDesiredProjection(
                project_id=plan.project_id,
                checkout_binding_id=plan.checkout_binding_id,
                target=t_val,
                preset=preset,
            )
        )
        assert isinstance(desired_view, DesiredProjectionView)  # noqa: S101
        adapter = ctx.gateways.get(IntegrationTargetRegistry).get(plan.target)
        checkout = resolve_checkout_by_binding(ctx, plan.project_id, plan.checkout_binding_id)
        for df in adapter.render(
            checkout_inputs(desired_view, bind_checkout_fs(ctx, checkout.local_locator))
        ):
            meta.setdefault(df.relative_path, (df.surface, df.boundary))
    return meta


def plan_to_wire(
    plan: ProjectionPlan,
    *,
    meta_by_path: Mapping[str, tuple[Surface, ManagedBoundary]] | None = None,
    conflict_suffix: str = ".skm-new",
) -> HostProjectionPlan:
    """Encode ``ProjectionPlan`` to ``urn:skm:integrations:host:projection-plan:v1``."""
    write_map = {w.relative_path: w for w in plan.writes}
    counts: dict[str, int] = {}
    wire_decisions: list[dict[str, Any]] = []
    for dec in plan.decisions:
        if (w := write_map.get(dec.relative_path)) is not None:
            surf, bnd, after = w.surface, w.boundary, w.managed_digest_after
            cpath = w.write_path if dec.kind is FileDecisionKind.CONFLICT_WRITE_NEW else None
        elif meta_by_path is not None and dec.relative_path in meta_by_path:
            surf, bnd = meta_by_path[dec.relative_path]
            after = dec.expected_observed_managed_digest
            cpath = (
                conflict_path(dec.relative_path, suffix=conflict_suffix)
                if dec.kind is FileDecisionKind.CONFLICT_WRITE_NEW
                else None
            )
        else:
            surf, bnd = Surface.INSTRUCTIONS, ManagedBoundary(ownership=Ownership.MANAGED_FILE)
            after, cpath = dec.expected_observed_managed_digest, None

        wire_kind = "leave_foreign" if dec.kind is FileDecisionKind.LEAVE_MODIFIED else dec.kind.value
        counts[wire_kind] = counts.get(wire_kind, 0) + 1
        item: dict[str, Any] = {
            "relative_path": dec.relative_path,
            "surface": surf.value,
            "decision": wire_kind,
            "boundary": boundary_to_wire(bnd),
            "reason": dec.diagnostic or dec.kind.value,
            "managed_digest_after": after,
            "observed_digest": dec.expected_observed_managed_digest,
        }
        if cpath is not None:
            item["conflict_path"] = cpath
        wire_decisions.append(item)

    wire_writes = [
        {
            "relative_path": w.relative_path,
            "write_path": w.write_path,
            "decision": w.decision.value,
            "boundary": boundary_to_wire(w.boundary),
            "surface": w.surface.value,
            "expected_observed_whole_digest": w.expected_observed_whole_digest,
            "needs_pre_image": w.needs_pre_image,
            "managed_digest_after": w.managed_digest_after,
            "new_bytes_base64": None
            if w.new_bytes is None
            else base64.b64encode(w.new_bytes).decode("ascii"),
            "new_bytes_digest": None if w.new_bytes is None else sha256_tagged(w.new_bytes),
            **({} if w.new_bytes is None else {"bytes": len(w.new_bytes)}),
        }
        for w in plan.writes
    ]
    return host_projection_plan_from_json(
        {
            "schema": "urn:skm:integrations:host:projection-plan:v1",
            "project_id": str(plan.project_id),
            "checkout_binding_id": str(plan.checkout_binding_id),
            "target": plan.target.value,
            "desired_digest": plan.desired_digest,
            "inputs_digest": plan.inputs_digest,
            "renderer_version": plan.renderer_version,
            "base_projection_row_version": plan.base_projection_row_version,
            "decisions": wire_decisions,
            "writes": wire_writes,
            "diagnostics": [dict(d) for d in plan.diagnostics],
            "counts": counts,
            "plan_digest": plan.plan_digest,
        }
    )


def run(ctx: HostContext, request: object) -> PlanProjectionResult:
    """HostOperationSpec entrypoint for ``integrations.host.plan_projection``."""
    req = cast("Mapping[str, Any]", plan_projection_request_from_json(request))
    raw_targets = cast("Sequence[str] | None", req.get("targets"))
    preset = read_preset(req.get("preset"))
    plans = plan_projection(
        ctx,
        project_id=ProjectId(parse_uuid(str(req["project_id"]))),
        mount=None if req.get("mount") is None else str(req["mount"]),
        targets=None if not raw_targets else tuple(TargetId(t) for t in raw_targets),
        force_conflicts=bool(req.get("force_conflicts", False)),
        preset=preset,
    )
    suffix = integrations_settings(ctx).conflict_suffix
    return [
        plan_to_wire(p, meta_by_path=collect_plan_meta(ctx, p, preset=preset), conflict_suffix=suffix)
        for p in plans
    ]


class PlanProjectionOperation:
    """Host operation class wrapper for ``integrations.host.plan_projection``."""

    name = "integrations.host.plan_projection"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name="integrations.host.plan_projection",
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", list),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
