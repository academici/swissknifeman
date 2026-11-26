"""Host operation ``integrations.host.detect_drift`` and wire plan decoder (integrations §7.3, §7.5)."""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.ids import ProjectId, parse_uuid
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.contracts import DriftReport
from skm.modules.integrations.domain.decisions import (
    DIAG_LEFT_MODIFIED,
    DIAG_MISSING_RESTORED,
    FileDecision,
    FileDecisionKind,
)
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.projection import PlannedWrite, ProjectionPlan
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.integrations.generated.commands import RecordDrift, RecordDriftFilesItem
from skm.modules.integrations.generated.documents import HostProjectionPlan, host_projection_plan_from_json
from skm.modules.integrations.generated.host import (
    DetectDriftResult,
    detect_drift_request_from_json,
    detect_drift_result_from_json,
)
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.results import RecordDriftResult
from skm.modules.integrations.generated.views import AppliedStateView
from skm.modules.workspace.public import CheckoutBindingId

from .observe import boundary_from_wire
from .plan_projection import plan_projection

__all__ = [
    "SPEC",
    "DetectDriftOperation",
    "detect_drift",
    "is_drift_decision",
    "plan_from_wire",
    "run",
]

_DRIFT_KINDS: frozenset[FileDecisionKind] = frozenset(
    {
        FileDecisionKind.CONFLICT_WRITE_NEW,
        FileDecisionKind.BOUNDARY_INVALID,
        FileDecisionKind.ADOPT_REQUIRED,
        FileDecisionKind.LEAVE_MODIFIED,
        FileDecisionKind.UNSAFE_TARGET,
    }
)


def plan_from_wire(
    doc: HostProjectionPlan | Mapping[str, Any],
) -> tuple[ProjectionPlan, dict[str, tuple[Surface, ManagedBoundary]]]:
    """Decode wire ``HostProjectionPlan`` into ``(ProjectionPlan, meta_by_path)``."""
    parsed = cast("Mapping[str, Any]", host_projection_plan_from_json(doc))
    write_whole_by_path: dict[str, str | None] = {}
    writes: list[PlannedWrite] = []
    for raw_w in cast("Sequence[Mapping[str, Any]]", parsed["writes"]):
        b64 = cast("str | None", raw_w.get("new_bytes_base64") or raw_w.get("bytes_base64"))
        bnd = (
            boundary_from_wire(cast("Mapping[str, Any]", raw_w["boundary"]))
            if "boundary" in raw_w
            else ManagedBoundary(ownership=Ownership.MANAGED_FILE)
        )
        dkind = FileDecisionKind(str(raw_w.get("decision", FileDecisionKind.CREATE.value)))
        exp_whole = cast("str | None", raw_w.get("expected_observed_whole_digest"))
        rel_w = str(raw_w["relative_path"])
        if dkind is not FileDecisionKind.CONFLICT_WRITE_NEW:
            write_whole_by_path[rel_w] = exp_whole
        writes.append(
            PlannedWrite(
                relative_path=rel_w,
                decision=dkind,
                boundary=bnd,
                surface=Surface(str(raw_w.get("surface", Surface.INSTRUCTIONS.value))),
                new_bytes=None if b64 is None else base64.b64decode(b64.encode("ascii")),
                write_path=str(raw_w["write_path"]),
                expected_observed_whole_digest=exp_whole,
                needs_pre_image=bool(raw_w.get("needs_pre_image", False)),
                managed_digest_after=cast("str | None", raw_w.get("managed_digest_after")),
            )
        )

    decisions: list[FileDecision] = []
    meta_by_path: dict[str, tuple[Surface, ManagedBoundary]] = {}
    for raw_d in cast("Sequence[Mapping[str, Any]]", parsed["decisions"]):
        rel, raw_kind, reason = str(raw_d["relative_path"]), str(raw_d["decision"]), str(raw_d["reason"])
        if raw_kind == "leave_foreign":
            dkind, default_diag = FileDecisionKind.LEAVE_MODIFIED, DIAG_LEFT_MODIFIED
        elif raw_kind == "missing_restore":
            dkind, default_diag = FileDecisionKind.CREATE, DIAG_MISSING_RESTORED
        else:
            dkind, default_diag = FileDecisionKind(raw_kind), None
        diag = None if reason == dkind.value else (reason or default_diag)
        meta_by_path[rel] = (
            Surface(str(raw_d["surface"])),
            boundary_from_wire(cast("Mapping[str, Any]", raw_d["boundary"])),
        )
        decisions.append(
            FileDecision(
                rel,
                dkind,
                diag,
                cast("str | None", raw_d.get("observed_digest")),
                write_whole_by_path.get(rel),
            )
        )

    target_str = str(parsed["target"])
    raw_diags = cast("Sequence[Mapping[str, Any]]", parsed.get("diagnostics") or ())
    return (
        ProjectionPlan(
            project_id=ProjectId(parse_uuid(str(parsed["project_id"]))),
            checkout_binding_id=CheckoutBindingId(parse_uuid(str(parsed["checkout_binding_id"]))),
            target=TargetId(target_str),
            desired_digest=str(parsed["desired_digest"]),
            inputs_digest=str(parsed.get("inputs_digest") or sha256_tagged(b"")),
            renderer_version=str(parsed.get("renderer_version") or f"{target_str}@1"),
            base_projection_row_version=cast("int | None", parsed.get("base_projection_row_version")),
            decisions=tuple(decisions),
            writes=tuple(writes),
            diagnostics=tuple(dict(d) for d in raw_diags),
            plan_digest=str(parsed["plan_digest"]),
        ),
        meta_by_path,
    )


def is_drift_decision(decision: FileDecision) -> bool:
    """Return True when ``decision`` represents checkout drift against applied ownership (§7.3)."""
    if decision.kind in _DRIFT_KINDS:
        return True
    return decision.kind is FileDecisionKind.CREATE and decision.diagnostic == DIAG_MISSING_RESTORED


def detect_drift(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    mount: str | None = None,
    targets: tuple[TargetId, ...] | None = None,
) -> tuple[DriftReport, ...]:
    """Compute drift per target without touching checkout files, recording active projections on the bus."""
    plans = plan_projection(ctx, project_id=project_id, mount=mount, targets=targets, force_conflicts=False)
    reports: list[DriftReport] = []

    for plan in plans:
        drifted_decisions = [dec for dec in plan.decisions if is_drift_decision(dec)]
        applied_view = ctx.client.ask(
            GetAppliedState(
                project_id=plan.project_id,
                checkout_binding_id=plan.checkout_binding_id,
                target=cast("Any", plan.target.value),
            )
        )
        assert isinstance(applied_view, AppliedStateView)  # noqa: S101

        projection_id_str: str | None = None
        state_str = "pending"
        recorded = False

        if applied_view.projection is not None and applied_view.projection.state != "removed":
            cmd = RecordDrift(
                project_id=UUID(str(plan.project_id)),
                checkout_binding_id=UUID(str(plan.checkout_binding_id)),
                target=cast("Any", plan.target.value),
                desired_digest=plan.desired_digest,
                base_row_version=applied_view.projection.row_version,
                files=tuple(
                    RecordDriftFilesItem(
                        relative_path=dec.relative_path,
                        decision=cast("Any", dec.kind.value),
                        diagnostic=dec.diagnostic,
                    )
                    for dec in drifted_decisions
                ),
            )
            res = ctx.client.dispatch(cmd, idempotency_key=ctx.client.new_idempotency_key())
            assert isinstance(res, RecordDriftResult)  # noqa: S101
            projection_id_str = str(res.projection_id)
            state_str = str(res.state)
            recorded = True
        elif applied_view.projection is not None:
            projection_id_str = str(applied_view.projection.projection_id)
            state_str = str(applied_view.projection.state)
        elif drifted_decisions:
            state_str = "drifted"

        reports.append(
            {
                "project_id": str(plan.project_id),
                "checkout_binding_id": str(plan.checkout_binding_id),
                "target": plan.target.value,
                "projection_id": projection_id_str,
                "state": state_str,
                "desired_digest": plan.desired_digest,
                "drifted": len(drifted_decisions),
                "recorded": recorded,
                "files": [
                    {
                        "relative_path": dec.relative_path,
                        "decision": dec.kind.value,
                        "diagnostic": dec.diagnostic,
                    }
                    for dec in drifted_decisions
                ],
            }
        )

    return tuple(reports)


def run(ctx: HostContext, request: object) -> DetectDriftResult:
    """HostOperationSpec entrypoint for ``integrations.host.detect_drift``."""
    req = cast("Mapping[str, Any]", detect_drift_request_from_json(request))
    project_id = ProjectId(parse_uuid(str(req["project_id"])))
    raw_targets = cast("Sequence[str] | None", req.get("targets"))
    targets = None if not raw_targets else tuple(TargetId(t) for t in raw_targets)
    mount = None if req.get("mount") is None else str(req["mount"])
    reports = detect_drift(ctx, project_id=project_id, mount=mount, targets=targets)
    return detect_drift_result_from_json([dict(r) for r in reports])


class DetectDriftOperation:
    """Host operation class wrapper for ``integrations.host.detect_drift``."""

    name = "integrations.host.detect_drift"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name="integrations.host.detect_drift",
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", list),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
