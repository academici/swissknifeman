"""Human decisions and approvals through their owning bus contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

from skm.entrypoints.cli._run_io import ask, dispatch, identifier, operations, run_id, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.modules.workspace.public import GetProject

commands = operations("execution", writes=True)
GetRun = operations("execution").GetRun
GetExecutionDetail = operations("execution").GetExecutionDetail
ListDecisionRequests = operations("execution").ListDecisionRequests
GetPlan = operations("planning").GetPlan
ApproveIntent = operations("policy", writes=True).ApproveIntent
DenyIntent = operations("policy", writes=True).DenyIntent
GetIntent = operations("policy").GetIntent
ListIntents = operations("policy").ListIntents

_HELP = {
    "list": "list human decisions and proposed approvals",
    "show": "show a decision request",
    "answer": "answer the exact current request revision",
    "approve": "approve exact intent arguments",
    "deny": "deny an intent",
    "verdict": "record a manual check verdict",
}


def _scope(args: argparse.Namespace, ctx: CliContext) -> dict[str, str]:
    if args.run_ref:
        return {"kind": "run", "id": str(run_id(ctx, args.run_ref))}
    return {"kind": "project", "id": str(resolve_project_id(ctx, args.project))}


def _requests(args: argparse.Namespace, ctx: CliContext, *, all_states: bool = False) -> Any:
    states = (
        ["open", "answered", "applied", "assumed", "denied", "stale", "expired", "cancelled"]
        if all_states or args.state == "all"
        else [args.state]
    )
    return ask(
        ctx,
        ListDecisionRequests,
        scope=_scope(args, ctx),
        kinds=None if args.kind is None else [args.kind],
        states=states,
        after=args.after,
        limit=args.limit,
    )


def _find(args: argparse.Namespace, ctx: CliContext) -> Any:
    wanted = identifier(args.request, "request")
    after = args.after
    while True:
        args.after = after
        view = _requests(args, ctx, all_states=True)
        for item in view.items:
            if str(item["request_id"]) == str(wanted):
                return item
        after = view.next_after
        if after is None:
            raise NotFound(ErrorCode.NOT_FOUND, "decision request not found in the selected scope")


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    items: list[Any] = []
    after = args.after
    while True:
        args.after = after
        view = _requests(args, ctx)
        items.extend(view.items)
        after = view.next_after
        if not args.all or after is None:
            break
    approvals: list[Any] = []
    if args.kind in (None, "approval"):
        scope = _scope(args, ctx)
        project_id = scope["id"]
        if scope["kind"] == "run":
            run = ask(ctx, GetRun, run_id=scope["id"])
            if run.plan_id is None:
                detail = ask(ctx, GetExecutionDetail, run_id=scope["id"])
                project_id = str(detail.project_id)
            else:
                project_id = str(ask(ctx, GetPlan, plan_id=str(run.plan_id)).project_id)
        project = ask(ctx, GetProject, project_id=project_id)
        cursor = None
        while True:
            intents = ask(
                ctx,
                ListIntents,
                workspace_id=str(project.workspace_id),
                scope_id=scope["id"],
                state="proposed",
                after=cursor,
                limit=args.limit,
            )
            approvals.extend(intents.items)
            cursor = intents.next_cursor
            if not args.all or cursor is None:
                break
        if cursor is not None:
            # Preserve the independent intent cursor; do not pretend the decision cursor resumes it.
            return show(
                ctx,
                "execution.list_decision_requests",
                {
                    "items": [*items, *[dict(item.to_json(), kind="approval") for item in approvals]],
                    "next": after,
                    "approvals": approvals,
                    "approvals_next": cursor,
                },
            )
    return show(
        ctx,
        "execution.list_decision_requests",
        {
            "items": [*items, *[dict(item.to_json(), kind="approval") for item in approvals]],
            "next": after,
            "approvals": approvals,
        },
    )


def _answer(args: argparse.Namespace, ctx: CliContext) -> int:
    request = _find(args, ctx)
    if args.verb == "show":
        return show(ctx, "execution.list_decision_requests", request)
    answer: dict[str, Any] = {}
    if args.answer is not None:
        answer["text"] = args.answer
    if args.option is not None:
        answer["option_id"] = args.option
    if args.file:
        try:
            with Path(args.file).open("rb") as stream:
                data = stream.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError("answer file exceeds 1 MiB")
            raw_answer: object = json.loads(data)
            if not isinstance(raw_answer, dict):
                raise ValueError("answer file requires an object")
            answer = cast("dict[str, Any]", raw_answer)
        except (OSError, ValueError) as error:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid JSON answer file") from error
    # Authority is enforced by the human bus handler; a CLI flag never grants a different authority.
    if args.authority != "owner":
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "human inbox answers require --authority owner")
    return show(
        ctx,
        "execution.answer_decision_request",
        dispatch(
            ctx,
            commands.AnswerDecisionRequest,
            request_id=str(request["request_id"]),
            answer=answer,
            expected_revision=int(request["revision"]),
            rationale=args.reason,
        ),
    )


def _duration(text: str) -> int:
    try:
        unit = text[-1:]
        seconds = (
            int(text[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] if unit in "smhd" else int(text)
        )
        if seconds <= 0:
            raise ValueError
    except (ValueError, KeyError):
        raise argparse.ArgumentTypeError("expected a positive duration such as 30m or 1h") from None
    return seconds


def _intent(args: argparse.Namespace, ctx: CliContext) -> int:
    intent = ask(ctx, GetIntent, intent_id=str(identifier(args.intent, "intent")))
    payload = {
        "intent_id": str(intent.intent_id),
        "expected_row_version": intent.row_version if args.if_version is None else args.if_version,
        "reason": args.reason,
    }
    if args.verb == "approve":
        payload.update(args_digest=args.digest or intent.args_digest, single_use=args.single_use)
        if args.expires_in is not None:
            payload["ttl_seconds"] = args.expires_in
        return show(ctx, "policy.approve_intent", dispatch(ctx, ApproveIntent, **payload))
    return show(ctx, "policy.deny_intent", dispatch(ctx, DenyIntent, **payload))


def _verdict(args: argparse.Namespace, ctx: CliContext) -> int:
    return show(
        ctx,
        "execution.record_manual_verdict",
        dispatch(
            ctx,
            commands.RecordManualVerdict,
            check_execution_id=str(identifier(args.check, "check")),
            verdict=args.verdict,
            comment=args.comment,
            supersedes_verdict_id=args.supersedes,
        ),
    )


def register(sub: SubParsers) -> None:
    parser = sub.add_parser("inbox", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("list", "show", "answer", "approve", "deny", "verdict"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if verb in ("list", "show", "answer"):
            command.add_argument("--run", dest="run_ref")
            command.add_argument("--project")
            command.add_argument("--kind", choices=("question", "approval", "manual_check", "escalation"))
            command.add_argument("--state", choices=("open", "answered", "all"), default="open")
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--all", action="store_true")
            command.set_defaults(run=_list)
        if verb in ("show", "answer"):
            command.add_argument("request")
            command.set_defaults(run=_answer)
        if verb == "answer":
            answers = command.add_mutually_exclusive_group(required=True)
            answers.add_argument("--answer")
            answers.add_argument("--option")
            answers.add_argument("--file")
            command.add_argument("--authority", choices=("scope", "plan", "owner"), default="owner")
            command.add_argument("--reason")
        if verb in ("approve", "deny"):
            command.add_argument("intent")
            command.add_argument("--if-version", type=int)
            command.add_argument("--digest")
            command.add_argument("--reason", default="CLI human decision")
            command.set_defaults(run=_intent)
        if verb == "approve":
            reuse = command.add_mutually_exclusive_group()
            reuse.add_argument("--single-use", dest="single_use", action="store_true", default=True)
            reuse.add_argument("--reusable", dest="single_use", action="store_false")
            command.add_argument("--expires-in", type=_duration)
        if verb == "verdict":
            command.add_argument("check")
            command.add_argument("verdict", choices=("pass", "fail"))
            command.add_argument("--comment", default="")
            command.add_argument("--supersedes")
            command.set_defaults(run=_verdict)
        command.set_defaults(command_name="inbox." + verb)


GROUP = CommandGroup(
    name="inbox",
    help="inspect and answer human decision requests",
    register=register,
    module="execution",
    order=31,
)

__all__ = ["GROUP"]
