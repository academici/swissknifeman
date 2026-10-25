"""The commits of the stages of a split run (``commit.mode: implementation-and-fixes``): which step stands for which stage, the
receipt each stage keeps, the trailers that make its commit findable again and the lookup that closes a stage whose
receipt a crash left unwritten."""
from __future__ import annotations

from typing import Optional

from aicore.util.digest import canonical_json_bytes, sha256_hex
from aicore.workspace import WorkspaceError, read_marker

from orch import journal
from orch.conductor import checks as checks_mod
from orch.conductor.domain.item import Item
from orch.port import PortError

CHECKPOINT_STEP = "checkpoint"  # the step of the implementation commit of a split run (stage ``implementation``)
FIX_COMMIT_PREFIX = "fix-commit."  # ``fix-commit.<n>``: the step of the fix commit of the correction after review round n


def stage_of(key: str) -> Optional[str]:
    """The stage of a commit step of a split run (``checkpoint``: ``implementation``, ``fix-commit.<n>``:
    ``correction.<n>``); ``None`` for every other step, the final ``commit`` included."""
    if key == CHECKPOINT_STEP:
        return "implementation"
    return "correction." + key[len(FIX_COMMIT_PREFIX):] if key.startswith(FIX_COMMIT_PREFIX) else None


def stage_step(stage: str) -> str:
    """The step key of a stage commit: the inverse of :func:`stage_of`."""
    return CHECKPOINT_STEP if stage == "implementation" else FIX_COMMIT_PREFIX + stage.split(".", 1)[1]


def receipt_stem(key: str) -> str:
    """The name (without ``.json``) of the receipt of the step ``key`` in ``receipts/``: ``commit-<stage>`` for a stage
    commit, else the operation (``close`` shares the receipt of ``register``)."""
    stage = stage_of(key)
    return f"commit-{stage}" if stage else "register" if key == "close" else key


def operation_of(key: str) -> str:
    """The work-source operation a step stands for: a stage commit is a ``commit``, ``close`` is a ``register``."""
    return "commit" if stage_of(key) else "register" if key == "close" else key


def stage_trailers(item: Item, stage: str, *, review: Optional[str] = None, findings=()) -> list:
    """The trailers of the commit of a stage of a split run: the run, the attempt and the stage, which is how a resume finds
    the commit again (:func:`committed_stage`); a fix commit also names the review round and the findings it answers."""
    lines = [f"Plan-Run: {item.orch_run}", f"Plan-Attempt: {item.claim.get('attempt_id')}", f"Plan-Stage: {stage}"]
    if review:
        lines.append(f"Plan-Review: {review}")
    if findings:
        lines.append("Plan-Findings: " + ",".join(findings))
    return lines


def committed_stage(item: Item, stage: str, *, project) -> Optional[str]:
    """The sha of the commit of ``stage`` (``final`` included) that the crash left without a receipt: the request of the
    stage exists for this attempt, names the stage, and the newest commit carries its ``Plan-Run``, ``Plan-Attempt`` and
    ``Plan-Stage`` trailers. ``None`` when it is not that commit (the stage was not committed: a repeat commits it; a run of
    ``final-only`` names no stage, so its commit is never looked up in the history) and for the final commit of a workspace plan
    (the repeat finishes its workspace part and keeps the source sha of its request)."""
    if not item.orch_run:
        return None
    try:
        directory = journal.run_dir(item.orch_run, project=project)
        request = journal.read_doc(directory, f"receipts/{'commit' if stage == 'final' else 'commit-' + stage}-request.json")
    except (OSError, ValueError, PortError):
        return None
    if not isinstance(request, dict) or request.get("attempt_id") != item.claim.get("attempt_id"):
        return None
    if stage == "final" and workspace_plan(item, directory, project):
        return None  # the commit of the source is only half of it: the plan files wait in the workspace repository
    parameters = request.get("parameters")
    if not (isinstance(parameters, dict) and request.get("digest") == sha256_hex(canonical_json_bytes(parameters))
            and parameters.get("stage") == stage and parameters.get("run_id") == item.orch_run
            and parameters.get("ref") == item.ref):
        return None
    try:
        message = checks_mod.git(project, "log", "-1", "--format=%B")
        sha = checks_mod.git(project, "rev-parse", "HEAD").strip()
    except RuntimeError:
        return None
    wanted = set(stage_trailers(item, stage))
    return sha if wanted <= {line.strip() for line in message.splitlines()} else None


def workspace_plan(item: Item, directory, project) -> bool:
    """The plan of the piece lives in the portable workspace (its final commit has a workspace part that the trailer of the
    source commit does not prove), as :func:`work_source.read_receipt` decides it."""
    try:
        source = (journal.read_doc(directory, "run.json") or {}).get("source") or {}
        marker = read_marker(project)
    except (OSError, ValueError, PortError, WorkspaceError):
        return False
    return not (isinstance(source, dict) and source.get("kind") == "file") and bool(marker and marker.get("plans_store") == "workspace")


def run_attempt(orch_run: str, project) -> Optional[str]:
    """The attempt of a work-source run (its ``run.json``): what a ``stopped`` step, which keeps no attempt, belonged to."""
    try:
        return (journal.read_doc(journal.run_dir(orch_run, project=project), "run.json") or {}).get("attempt_id")
    except (OSError, ValueError, PortError, AttributeError):
        return None
