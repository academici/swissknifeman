"""Doctor host operation; observes without fixing files or recording drift (§5.6, §8)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from skm.application_bus.host import HostContext
from skm.kernel.ids import ProjectId, parse_uuid
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.checks import run_checks, summarize
from skm.modules.integrations.domain.reports import CheckResult, DoctorReport
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.host import (
    RunDoctorResult,
    run_doctor_request_from_json,
    run_doctor_result_from_json,
)
from skm.modules.workspace.public import CheckoutBindingId

from .detect_drift import is_drift_decision
from .doctor import budget_settings, doctor_context, native_inputs
from .observe import list_binding_journals, resolve_checkout_for_mount
from .plan_projection import plan_projection

__all__ = ["SPEC", "RunDoctorOperation", "run", "run_doctor"]


def run_doctor(
    ctx: HostContext,
    *,
    project_id: ProjectId,
    mount: str | None = None,
    targets: tuple[TargetId, ...] | None = None,
) -> DoctorReport:
    selected = targets if targets is not None else tuple(TargetId(t) for t in budget_settings(ctx).targets)
    checks: list[CheckResult] = []
    for target in dict.fromkeys(selected):
        fs, adapter, inputs, files = native_inputs(ctx, project_id, mount, target)
        plans = plan_projection(ctx, project_id=project_id, mount=mount, targets=(target,))
        paths = [
            decision.relative_path
            for plan in plans
            for decision in plan.decisions
            if is_drift_decision(decision)
        ]
        binding = resolve_checkout_for_mount(ctx, project_id, mount)
        paths.extend(
            "host-journal:" + name
            for name, _ in list_binding_journals(fs, CheckoutBindingId(binding.binding_id))
        )
        observed = doctor_context(
            ctx,
            fs,
            adapter,
            inputs,
            files,
            repository_id=binding.repository_id,
            mount=mount or "main",
            drift_paths=tuple(paths),
        )
        checks.extend(run_checks(observed).checks)
    return summarize(tuple(checks))


def run(ctx: HostContext, request: object) -> RunDoctorResult:
    req = cast("Mapping[str, Any]", run_doctor_request_from_json(request))
    project_id = ProjectId(parse_uuid(str(req["project_id"])))
    raw_targets = cast("Sequence[str] | None", req.get("targets"))
    targets = None if raw_targets is None else tuple(TargetId(t) for t in raw_targets)
    report = run_doctor(ctx, project_id=project_id, mount=req.get("mount"), targets=targets)
    return run_doctor_result_from_json(
        {
            "schema": "urn:skm:integrations:host:doctor-report:v1",
            "project_id": str(project_id),
            "host_id": str(ctx.host_id),
            "targets": list(dict.fromkeys(check.target.value for check in report.checks)),
            "status": report.status,
            "counts": dict(report.counts),
            "checks": [
                {
                    "check_id": check.check_id,
                    "target": check.target.value,
                    "level": check.level,
                    "title": check.title,
                    "detail": check.detail,
                    "path": check.path,
                    "hint": check.hint,
                }
                for check in report.checks
            ],
        }
    )


class RunDoctorOperation:
    name = "integrations.host.run_doctor"
    run = staticmethod(run)


SPEC = HostOperationSpec(
    name=RunDoctorOperation.name,
    run=run,
    request=cast("type[object]", dict),
    result=cast("type[object]", dict),
    surfaces=cast("frozenset[Any]", frozenset({"cli", "worker"})),
)
