"""Work-source receipts and recovery validation."""
from __future__ import annotations

from typing import Optional

from aicore.util import timefmt
from aicore.util.digest import canonical_json_bytes, sha256_hex
from aicore.workspace import WorkspaceError, read_marker

from orch import journal
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure.commit_stages import operation_of, receipt_stem, stage_of
from orch.port import PortError
from orch.worksource import problems as source_problems


def read_receipt(item: Item, kind: str, *, project=None) -> Optional[dict]:
    """Read the work-source run, never the conductor item folder. Broken documents authorize only a repeat.

    ``kind`` is a step key: a stage commit (``checkpoint``, ``fix-commit.<n>``) reads its own receipt.
    Private metadata accompanies the raw answer for recovery; it never becomes a step result.
    ``project`` is the same project passed to the source CLI (machine state is used only without a project).
    """
    if not item.orch_run:
        return None
    stem = receipt_stem(kind)
    try:
        directory = journal.run_dir(item.orch_run, project=project)
        doc = journal.read_doc(directory, f"receipts/{stem}.json")
        request = journal.read_doc(directory, f"receipts/{stem}-request.json")
        request_mtime_ns = (directory / f"receipts/{stem}-request.json").stat().st_mtime_ns \
            if isinstance(request, dict) else None
        run_doc = journal.read_doc(directory, "run.json") or {}
        marker = read_marker(project) if project is not None else None
    except (OSError, ValueError, PortError, WorkspaceError):
        return None
    if not isinstance(doc, dict) or not isinstance(run_doc, dict):
        return None
    source = run_doc.get("source") or {}
    if not isinstance(source, dict):
        return None
    file_source = source.get("kind") == "file"
    workspace = not file_source and bool(marker and marker.get("plans_store") == "workspace")
    source_sha = None
    parameters = request.get("parameters") if isinstance(request, dict) else None
    if (isinstance(parameters, dict) and request.get("attempt_id") == item.claim.get("attempt_id")
            and parameters.get("attempt_id") == request.get("attempt_id")
            and parameters.get("run_id") == item.orch_run and parameters.get("ref") == item.ref
            and request.get("digest") == sha256_hex(canonical_json_bytes(parameters))):
        candidate = request.get("source_sha")
        if isinstance(candidate, str) and not source_problems({"op": "commit", "outcome": "committed", "sha": candidate}, "output"):
            source_sha = candidate
    return {**doc, "_request": request, "_request_mtime_ns": request_mtime_ns,
            "_workspace_required": workspace, "_source_sha": source_sha}


def receipt_closes(kind: str, doc: Optional[dict], item: Item, *, state_saved_ns: Optional[int] = None) -> tuple:
    """L11: successful outcome, this attempt, and a finished workspace part. Git history is never authority."""
    step = item.state.get("steps", {}).get(kind, {})
    staged = stage_of(kind) is not None  # a stage commit leaves the plan files: no workspace part to wait for
    kind = operation_of(kind)
    if not isinstance(doc, dict) or doc.get("op") != kind:
        return False, "repeated: receipt missing"
    if doc.get("outcome") not in (("recorded", "no-op") if kind == "register" else ("committed", "no-op")):
        return False, "repeated: receipt refused"
    # The fields recovered into a step obey the same contract as a live source answer.
    # Workspace completion has its own L11 rules below, including historical success statuses.
    fields = ("op", "outcome", "gate") if kind == "register" else ("op", "outcome", "sha", "message", "attempt")
    if source_problems({key: doc[key] for key in fields if key in doc}, "output"):
        return False, "repeated: receipt missing"
    recovering = step.get("status") == "started"
    if recovering:
        # started_at has second precision in existing journals. The publication of state.json also fences a retry
        # within that same second; a later state save can conservatively require an idempotent repeat.
        try:
            started = timefmt.parse_rfc3339(step["started_at"])
            if started is None:
                raise ValueError("started_at is not a timestamp")
            boundary = max(int(started.timestamp() * 1_000_000_000), state_saved_ns or 0)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return False, "repeated: receipt of another attempt"
        request_mtime = doc.get("_request_mtime_ns")
        if not isinstance(request_mtime, int) or request_mtime < boundary:
            return False, "repeated: receipt of another attempt"
    expected = item.claim.get("attempt_id")
    receipt = doc.get("receipt")
    if receipt is not None and not isinstance(receipt, dict):
        return False, "repeated: receipt missing"
    attempt = doc.get("attempt") or (receipt or {}).get("attempt_id")
    if not attempt or recovering:
        request = doc.get("_request")
        if not isinstance(request, dict) or not isinstance(request.get("parameters"), dict):
            return False, "repeated: receipt missing"
        parameters = request["parameters"]
        raw = {key: value for key, value in doc.items() if not key.startswith("_")}
        if (request.get("digest") != sha256_hex(canonical_json_bytes(parameters))
                or request.get("receipt_digest") != sha256_hex(canonical_json_bytes(raw))
                or parameters.get("run_id") != item.orch_run
                or parameters.get("ref") != item.ref
                or parameters.get("attempt_id") != request.get("attempt_id")):
            return False, "repeated: receipt missing"
        if attempt and attempt != request.get("attempt_id"):
            return False, "repeated: receipt of another attempt"
        attempt = request.get("attempt_id")
    if not expected or attempt != expected:
        return False, "repeated: receipt of another attempt"
    if kind == "commit" and not workspace_complete(doc, required=bool(doc.get("_workspace_required")) and not staged):
        return False, "repeated: workspace part incomplete"
    return True, "closed from receipt"


def workspace_complete(answer: dict, *, required: bool = False) -> bool:
    split = answer.get("workspace_commit")
    if not required and not any(key in answer for key in ("workspace_commit", "workspace_sha", "repo")):
        return True
    return isinstance(split, dict) and split.get("status") in ("committed", "no-op", "skipped-legacy", "skipped-no-git")


def receipt_result(kind: str, answer: dict) -> dict:
    """The same result shapes for live calls and recovered steps (finish reads close['by'])."""
    kind = operation_of(kind) if kind != "close" else kind
    if kind == "close":
        return {"by": "closer", "answer": "registration recovered from receipt"}
    if kind == "register":  # ``evidence``: where the source keeps the evidence for good (a workspace plan)
        return {"outcome": answer["outcome"], "gate": (answer.get("gate") or {}).get("verdict"),
                **({"evidence": answer["evidence"]} if answer.get("evidence") else {})}
    kept = {"outcome": answer["outcome"], "sha": answer.get("sha")}
    if answer.get("repo") == "workspace":
        kept["sha"] = answer.get("_source_sha")
        if not kept["sha"]:
            kept["message"] = f"workspace commit {answer.get('sha')}; source commit unknown"
    if answer.get("message"):
        kept["message"] = "; ".join(filter(None, (kept.get("message"), answer["message"])))
    return kept
