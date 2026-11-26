"""Retain complete manual-check feedback as an artifact in the transition UoW."""

from __future__ import annotations

from typing import Any

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.ids import FileVersionId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.artifacts import public as artifacts
from skm.modules.execution.application._plain import plain
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.ports import EvidenceBindingRepository

from ._json_report import retain_json_report


def register_manual_report(
    uow: UnitOfWork, ctx: Any, state: Any, checks: Any, brief_id: Any
) -> FileVersionId:
    failed = [
        check for check in checks if check.kind is CheckKind.MANUAL and check.state is CheckState.FAILED
    ]
    if not failed or any(
        check.id not in state.manual or state.manual[check.id].verdict != "fail" for check in failed
    ):
        raise error_for(ErrorCode.NOT_ACCEPTABLE, "manual repair requires current human failure verdicts")
    document: JsonObject = {
        "kind": "fix_brief",
        "source": "manual_verdict",
        "fix_brief_id": str(brief_id),
        "run_id": str(state.run.id),
        "revision_id": str(state.run.revision_id) if state.run.revision_id is not None else None,
        "task_id": str(state.task.id),
        "attempt_id": str(state.attempt.id),
        "output_id": str(state.attempt.current_output_id),
        "checks": [
            {"check": plain(check), "manual_verdict": plain(state.manual[check.id])} for check in failed
        ],
    }
    version_id = retain_json_report(
        uow,
        ctx,
        state,
        document,
        title=f"Fix brief report for {state.task.display_key}",
        filename=f"fix-brief-{brief_id}.json",
        source_ref=f"fix_brief:{brief_id}",
    )
    bindings = uow.repo(EvidenceBindingRepository)
    for check in failed:
        bindings.bind("check_execution", check.id, (version_id,), artifacts.BindingRole.REPORT)
    return version_id
