"""Review receipts retain the digest of the output actually reviewed."""

from typing import Any, cast
from uuid import UUID

from skm.kernel.ids import RunId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.review_request import CommitReviewTarget
from skm.modules.execution.domain.stored_payloads import not_found

__all__ = ["build_review_receipt"]


def build_review_receipt(state: Any, run_id: RunId) -> JsonObject:
    run = state.runs.get(run_id)
    if run is None or run.review_request_id is None:
        raise not_found("review_receipt", run_id)
    req = state.review_requests.get(run.review_request_id)
    if req is None:
        raise not_found("review_request", run.review_request_id)
    revs = sorted(
        (r for r in state.reviews.values() if r.run_id == run_id),
        key=lambda r: (r.round_no, str(r.id)),
    )
    latest_rev = revs[-1] if revs else None
    outs = sorted(
        (
            o
            for o in state.outputs.values()
            if (att := state.attempts.get(o.attempt_id)) is not None and att.run_id == run_id
        ),
        key=lambda o: (o.sealed_at, o.seq),
    )
    latest_out = (
        state.outputs.get(latest_rev.output_id) if latest_rev is not None else (outs[-1] if outs else None)
    )
    fnds = (
        [
            {
                "finding_id": str(f.id),
                "finding_key": f.finding_key,
                "location": dict(f.location),
                "state": f.state.value,
                "severity": f.severity.value,
                "category": f.category,
                "message": f.message,
            }
            for f in state.findings.values()
            if f.review_id == latest_rev.id
        ]
        if latest_rev is not None
        else []
    )
    return {
        "request_id": str(req.id),
        "run_id": str(run.id),
        "status": run.status.value,
        "verdict": None if (latest_rev is None or latest_rev.verdict is None) else latest_rev.verdict.value,
        "findings": cast("list[JsonValue]", fnds),
        "output_id": str(latest_out.id if latest_out is not None else UUID(int=0)),
        "tree_digest": latest_out.manifest.tree_digest if latest_out is not None else ("sha256:" + "0" * 64),
        "base_commit": req.target.base_commit,
        "head_commit": req.target.head_commit
        if isinstance(req.target, CommitReviewTarget)
        else (
            next(
                (m.head_commit for m in latest_out.manifest.mounts if m.mount == req.mount),
                req.target.base_commit,
            )
            if latest_out is not None
            else req.target.base_commit
        ),
    }
