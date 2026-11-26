"""Read run and task data within the session project and assignment scope."""

import re
from collections.abc import Iterator
from typing import cast
from uuid import UUID

from skm.entrypoints.mcp.session import McpSession
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context import public as context
from skm.modules.execution import public as execution
from skm.modules.planning import public as planning

from .plan import get_entity, revision_id
from .questions import decision_summary

__all__ = ["run_history", "run_status", "task_context", "task_status"]

_RUN_KINDS = ("plan", "review_request", "readiness_audit")
_UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.IGNORECASE)
_RUN_PREFIX = re.compile(r"[0-9a-f][0-9a-f-]*", re.IGNORECASE)


def _ref_uuid(ref: str, kind: str) -> UUID | None:
    raw = ref.removeprefix(f"{kind}:")
    if _UUID.fullmatch(raw):
        return UUID(raw)
    if raw != ref:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, f"Invalid {kind} UUID reference")
    return None


def _run_id(session: McpSession, ref: str) -> UUID:
    explicit = _ref_uuid(ref, "run")
    last = ref == "last"
    prefix = ref.lower().replace("-", "")
    if not last and explicit is None and (not 12 <= len(prefix) <= 32 or not _RUN_PREFIX.fullmatch(ref)):
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "Run requires a UUID, a UUID prefix or last")
    assigned = session.run_id
    if assigned is not None:
        if last or assigned == explicit or (explicit is None and assigned.hex.startswith(prefix)):
            return assigned
        raise NotFound(ErrorCode.NOT_FOUND, "run not found in this session")

    after = None
    matches: list[UUID] = []
    while True:
        page = cast(
            "execution.RunsView",
            session.client.ask(
                execution.ListRuns(
                    session.project_id,
                    kinds=_RUN_KINDS,
                    after=after,
                    limit=1 if last else 200,
                )
            ),
        )
        for item in page.items:
            candidate = UUID(str(item["run_id"]))
            if last or candidate == explicit:
                return candidate
            if explicit is None and candidate.hex.startswith(prefix):
                matches.append(candidate)
                if len(matches) > 1:
                    raise ValidationFailed(ErrorCode.AMBIGUOUS_REFERENCE, "multiple runs match this prefix")
        after = page.next_after
        if after is None:
            break
    if matches:
        return matches[0]
    raise NotFound(ErrorCode.NOT_FOUND, "run not found in this project")


def _task_rows(session: McpSession, run_id: UUID) -> list[JsonObject]:
    page = cast("execution.TasksView", session.client.ask(execution.ListTasks(run_id)))
    return cast("list[JsonObject]", page.to_json()["tasks"])


def _task(session: McpSession, task_id: JsonValue) -> execution.TaskView:
    return cast("execution.TaskView", session.client.ask(execution.GetTask(UUID(str(task_id)))))


def _task_by_ref(session: McpSession, run_id: UUID, ref: str) -> execution.TaskView:
    explicit = _ref_uuid(ref, "task")
    for row in _task_rows(session, run_id):
        if row["task_id"] == str(explicit) or row["display_key"] == ref:
            return _task(session, row["task_id"])
    raise NotFound(ErrorCode.NOT_FOUND, "task not found in this run")


def _attempts(session: McpSession, task: execution.TaskView) -> Iterator[execution.AttemptView]:
    for row in reversed(task.attempts):
        yield cast(
            "execution.AttemptView",
            session.client.ask(execution.GetAttempt(UUID(str(row["attempt_id"])))),
        )


def _assignment_task(session: McpSession, run_id: UUID) -> execution.TaskView:
    if session.assignment_id is None or session.step_id is None:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "Select a task with the task argument")
    for row in _task_rows(session, run_id):
        task = _task(session, row["task_id"])
        for attempt in _attempts(session, task):
            if any(step["step_id"] == str(session.step_id) for step in attempt.steps):
                return task
    raise NotFound(ErrorCode.NOT_FOUND, "task not found for the current assignment step")


def _run(session: McpSession, run_id: UUID) -> execution.RunView:
    return cast("execution.RunView", session.client.ask(execution.GetRun(run_id)))


def _decisions(session: McpSession, run_id: UUID) -> list[JsonObject]:
    try:
        view = cast(
            "execution.DecisionRequestsView",
            session.client.ask(
                execution.ListDecisionRequests.from_json({"scope": {"kind": "run", "id": str(run_id)}})
            ),
        )
    except Forbidden:
        return []  # run.read can be granted independently of inbox.read
    return cast("list[JsonObject]", view.to_json()["items"])


def _budget(session: McpSession, run_id: UUID) -> JsonObject:
    view = cast("execution.RunBudgetView", session.client.ask(execution.GetRunBudget(run_id)))
    for account in view.accounts:
        if account.get("scope") == "run" and account.get("dimension") == "usd":
            limit = account.get("limit")
            return {
                "usd_spent": int(str(account["spent"])) / 1_000_000,
                "usd_limit": None if limit is None else int(str(limit)) / 1_000_000,
            }
    return {"usd_spent": 0, "usd_limit": None}


def run_status(session: McpSession, args: JsonObject) -> JsonValue:
    run_id = _run_id(session, str(args.get("run", "last")))
    run = _run(session, run_id)
    return {
        "run_id": str(run_id),
        "status": run.status,
        "tasks": {"by_status": cast("JsonObject", run.to_json()["counts_by_status"])},
        "waiting": [
            {"request_id": row["request_id"], "kind": row["kind"], "summary": decision_summary(row)}
            for row in _decisions(session, run_id)
        ],
        "budget": _budget(session, run_id),
    }


def run_history(session: McpSession, args: JsonObject) -> JsonValue:
    run_id = _run_id(session, str(args["run"]))
    query = execution.GetRunHistory.from_json(
        {**{k: v for k, v in args.items() if k != "run"}, "run_id": str(run_id)}
    )
    return cast("execution.RunHistoryResult", session.client.ask(query)).to_json()


def task_status(session: McpSession, args: JsonObject) -> JsonValue:
    task = _task_by_ref(session, _run_id(session, str(args.get("run", "last"))), str(args["task"]))
    reason = task.blocking_reason
    return {
        "task_key": task.display_key,
        "status": task.status,
        "attempts": len(task.attempts),
        "rework_rounds": task.check_fix_rounds + task.review_rounds,
        "blocking_reason": None if reason is None else str(reason.get("message") or reason["code"]),
    }


def _context_blocks(session: McpSession, own_step: bool) -> dict[str, str]:
    if not own_step or session.step_id is None:
        return {}
    step = cast("execution.StepView", session.client.ask(execution.GetStep(session.step_id)))
    scope = {"project_id": str(session.project_id), "manifest_id": str(step.context_manifest_id)}
    try:
        view = cast(
            "context.ContextExplainResponse", session.client.ask(context.ExplainContextRequest(scope))
        )
        blocks: dict[str, str] = {}
        for row in cast("list[JsonObject]", view["rows"]):
            kind = row.get("block_type")
            if kind not in ("task_contract", "decision_answers") or row.get("pos") is None:
                continue
            query = context.GetContextTextRequest({**scope, "position": row["pos"]})
            text = cast("context.ContextTextResponse", session.client.ask(query))
            if text["available"] and isinstance(text["text"], str):
                blocks[str(kind)] = text["text"]
    except Forbidden:
        return {}  # context.read is a separate permission
    return blocks


def _records(doc: JsonObject, key: str) -> list[JsonObject]:
    return cast("list[JsonObject]", doc.get(key) or [])


def _read_ref(read: JsonObject) -> str:
    if read["kind"] == "path":
        return f"{read['mount']}:{read['path']}"
    return str(read.get("ref") or read.get("url") or read.get("external_source_id") or "")


def _check(check: JsonObject) -> JsonObject:
    result = {"key": check["key"], "kind": check["kind"]}
    definition = cast("JsonObject", check.get("definition") or {})
    if "argv" in definition:
        result["argv"] = definition["argv"]
    return result


def task_context(session: McpSession, args: JsonObject) -> JsonValue:
    explicit = args.get("task")
    run_id = _run_id(session, "last")
    task = (
        _assignment_task(session, run_id)
        if explicit is None
        else _task_by_ref(session, run_id, str(explicit))
    )
    run = _run(session, run_id)
    if run.plan_id is None or run.revision_no is None:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "task context requires a revision-backed run")
    rev_id = revision_id(session, run.plan_id, run.revision_no)
    entity = get_entity(session, planning.GetEntity(run.plan_id, task.display_key, revision_id=rev_id))
    revision = cast(
        "planning.RevisionView",
        session.client.ask(planning.GetRevision(run.plan_id, revision_id=rev_id, include_document=True)),
    )
    doc = cast("JsonObject", revision.to_json()["document"])
    target = cast("JsonObject", entity.to_json()["document"])
    parent_key = task.display_key.partition("/")[0] if entity.entity_kind == "unit" else None
    parent = next((row for row in _records(doc, "items") if row["key"] == parent_key), dict[str, JsonValue]())
    owners = {task.display_key, str(parent_key), str(target.get("phase") or parent.get("phase"))}
    scope = cast("JsonObject", target.get("scope") or parent.get("scope") or {})
    write_scope = (
        [f"{entry['mount']}:{entry['pattern']}" for entry in _records(target, "write_scope")]
        if "write_scope" in target
        else cast("list[str]", scope.get("include", []))
    )
    attempts = list(_attempts(session, task))
    own_step = any(step["step_id"] == str(session.step_id) for attempt in attempts for step in attempt.steps)
    blocks = _context_blocks(session, own_step)
    decision_keys = cast("list[str]", target.get("decisions") or parent.get("decisions") or [])
    return {
        "task_key": task.display_key,
        "goal": target.get("goal") or target.get("summary") or target["title"],
        "instructions_md": blocks.get("task_contract")
        or target.get("instructions_md")
        or target.get("guidance_md")
        or "",
        "write_scope": list[JsonValue](write_scope),
        "reads": list[JsonValue](
            dict.fromkeys(_read_ref(row) for row in [*_records(parent, "reads"), *_records(target, "reads")])
        ),
        "criteria": [
            {"key": row["key"], "statement": row["statement"]}
            for row in _records(doc, "criteria")
            if str(row["owner"]) in owners
        ],
        "checks": [
            _check(row)
            for row in _records(doc, "checks")
            if str(row["owner"]) in owners or row["key"] in cast("list[str]", target.get("checks") or [])
        ],
        "decisions": [
            row
            for row in _records(doc, "decisions")
            if row["key"] in decision_keys
            or row.get("global") is True
            or owners.intersection(cast("list[str]", row.get("applies_to") or []))
        ],
        "review": {"mode": task.review_mode, "profile": task.review_profile},
        "previous_findings": [
            row
            for attempt in reversed(attempts)
            for row in cast("list[JsonObject]", attempt.to_json()["findings"])
        ],
        "answers": [blocks["decision_answers"]] if "decision_answers" in blocks else [],
    }
