"""Review shares runtime, cancellation, evidence and repair semantics with every agent role."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, override

from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.host.stages.agent_step import AgentStepStage

if TYPE_CHECKING:
    from skm.modules.execution.host.stages.base import StageOutcome, StageRequest
    from skm.modules.execution.ports import StageDeps


class AgentReviewStage(AgentStepStage):
    stage_type = "agent_review"

    @override
    def run(self, request: StageRequest, deps: StageDeps) -> StageOutcome:
        outcome = super().run(request, deps)
        payload = dict(outcome.payload)
        session_ref = payload.get("session_ref")
        if session_ref and outcome.kind is StageOutcomeKind.RESULT_INVALID:
            payload.pop("session_ref")
            payload["detail"] = json.dumps({**json.loads(str(payload["detail"])), "session_ref": session_ref})
        outcome = replace(outcome, payload=payload)
        result = outcome.payload.get("role_result")
        if not isinstance(result, dict):
            return outcome
        review = request.begin.get("review")
        if not isinstance(review, dict):
            raise ValueError("review stage requires server-created review identity")
        payload = {
            **outcome.payload,
            "review_id": review["review_id"],
            "verdict": result["verdict"],
            "findings": result.get("findings", []),
        }
        if review.get("reviewer_with_fix") is True:
            if self.seal_snapshot is None:
                raise ValueError("reviewer_with_fix requires a real output sealer")
            deps.cancel.raise_if_cancelled()
            output_id = self.seal_snapshot(request, deps)
            if output_id is not None:
                payload["output_id"] = output_id
        kind = {
            "green": StageOutcomeKind.VERDICT_GREEN,
            "red": StageOutcomeKind.VERDICT_RED,
            "attention": StageOutcomeKind.VERDICT_ATTENTION,
        }[str(result["verdict"])]
        reports = tuple(
            replace(file, owner=f"review:{review['review_id']}", role="report")
            for file in outcome.files
            if file.role == "raw_result"
        )
        return replace(outcome, kind=kind, payload=payload, files=(*outcome.files, *reports))
