"""Run control and inspection through the execution and context bus contracts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

from skm.bootstrap.local_execution import LocalRun, local_run_root, run_ephemeral
from skm.entrypoints.cli._run_io import (
    ask,
    changes,
    dispatch,
    identifier,
    named_query,
    operations,
    run_id,
    show,
    task_id,
)
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.plan import resolve_plan_id, resolve_revision_id
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext, CliSession
from skm.entrypoints.cli.follow import follow
from skm.entrypoints.cli.output import render, render_error, render_waiting
from skm.entrypoints.cli.refs import as_uuid
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, SkmError, ValidationFailed
from skm.kernel.ids import FileVersionId, RunId
from skm.kernel.outcomes import Waiting

from .export import register_run_report_args

commands = operations("execution", writes=True)
queries = operations("execution")

_HELP = {
    "export": "render a run report as Markdown",
    "readiness": "validate a plan revision for execution",
    "start": "start a pinned plan revision",
    "local": "run a prompt in a host-local session",
    "list": "list runs in the active project",
    "show": "show run status, stops, selection and blocking reasons",
    "follow": "follow events of this run",
    "pause": "pause a run",
    "resume": "resume a run",
    "cancel": "cancel a run",
    "reconfigure": "apply changes at a drained CAS checkpoint",
    "budget": "show run budgets",
    "timeline": "show run event history",
    "health": "explain run health",
    "tasks": "list run tasks",
    "task": "show a task and its attempts",
    "restart": "schedule a new task attempt",
    "skip": "skip a task with a reason",
    "attempt": "show an attempt",
    "step": "show an attempt step",
    "step-context": "explain or compare step context manifests",
    "step-prompt": "read a step prompt or a stored context block",
    "logs": "read attempt logs and transcripts",
    "deviation": "accept a bounded task deviation",
    "carry-forward": "carry a compatible result to another task",
}


def _local(args: argparse.Namespace, ctx: CliContext) -> int:
    session = cast("CliSession", ctx)
    run = LocalRun(local_run_root(session.environ, session.home), RunId(session.ids.new_id()))
    try:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "cannot read the local prompt file") from exc
    if not prompt.strip():
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "the local prompt must not be empty")
    text = run_ephemeral(
        run, prompt, model=args.model, workdir=Path.cwd(), environ=session.environ, ids=session.ids
    )
    return render(ctx, {"run_id": str(run.id), "text": text}, command=args.command_name, human=lambda _: text)


def _start(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.verb == "start" and args.mode == "progressive_per_phase" and args.visa is None:
        raise ValidationFailed(ErrorCode.READINESS_REQUIRED, "progressive execution requires --visa-id")
    plan = resolve_plan_id(ctx, args.plan)
    revision_ref = args.revision
    if revision_ref and as_uuid(revision_ref):
        revision_ref = "revision:" + revision_ref
    revision = resolve_revision_id(ctx, plan, revision_ref)
    pairs = list(args.run_sets or ())
    # Leading --set flags are run overrides too; do not silently drop their admission binding.
    if isinstance(ctx, CliSession):
        pairs = [*ctx.options.sets, *pairs]
    overrides = changes(ctx, pairs, level="plan", scope_id=plan)
    if args.workflow:
        overrides["execution.workflow.profile"] = args.workflow
    selection = {
        "task_keys": [key for group in args.tasks or () for key in group.split(",")],
        "phases": args.phase or [],
        **({"stop_after": args.stop_after} if args.stop_after is not None else {}),
    }
    selected = selection if args.tasks or args.phase or args.stop_after else None
    report = None
    if args.verb == "readiness" or (not args.skip_readiness and args.visa is None):
        report = dispatch(
            ctx,
            commands.ValidateForExecution,
            plan_id=str(plan),
            revision_id=str(revision),
            overrides=overrides,
            selection=selected,
            mode=args.mode,
            semantic_audit=getattr(args, "semantic_audit", None),
        )
        if args.verb == "readiness" or report.status not in {"ready", "ready_with_advisories"}:
            show(ctx, "execution.validate_for_execution", report)
            return 0 if report.status in {"ready", "ready_with_advisories"} else 1
    result = dispatch(
        ctx,
        commands.StartRun,
        plan_id=str(plan),
        revision_id=str(revision),
        readiness_report_id=None if report is None else str(report.report_id),
        overrides=overrides,
        reason=args.reason,
        selection=selected,
        mode=args.mode,
        visa_id=args.visa,
    )
    if args.follow:
        return follow(ctx, result.run_id)
    return show(ctx, "execution.start_run", result)


def _list(args: argparse.Namespace, ctx: CliContext) -> int:
    project = resolve_project_id(ctx, args.project)
    plan = None if args.plan is None else resolve_plan_id(ctx, args.plan, project_ref=str(project))
    after = args.after
    items: list[Any] = []
    while True:
        view = ask(
            ctx,
            queries.ListRuns,
            project_id=str(project),
            plan_id=None if plan is None else str(plan),
            statuses=args.status,
            after=after,
            limit=args.limit,
        )
        items.extend(view.items)
        after = view.next_after
        if not args.all or after is None:
            break
    return show(ctx, "execution.list_runs", {"items": items, "next": after})


def _control(args: argparse.Namespace, ctx: CliContext) -> int:
    rid = run_id(ctx, args.run_ref)
    operation = {
        "pause": commands.PauseRun,
        "resume": commands.ResumeRun,
        "cancel": commands.CancelRun,
        "reconfigure": commands.ReconfigureRun,
    }[args.verb]
    payload: dict[str, Any] = {"run_id": str(rid)}
    if args.verb != "resume":
        payload["reason"] = args.reason
    if args.verb == "reconfigure":
        payload["expected_row_version"] = args.if_version
        if args.if_version is None:
            payload["expected_row_version"] = ask(ctx, queries.GetRun, run_id=str(rid)).row_version
        payload["changes"] = changes(ctx, args.changes, level="run", scope_id=rid)
    if args.verb == "cancel" and not ctx.confirm(f"Cancel run {rid}?"):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "cancel requires --yes or confirmation")
    try:
        if args.verb == "reconfigure":
            # Preserve integers parsed against the settings schema. The generic JSON-value codec
            # represents numbers as floats; the reconfigure handler intentionally requires integers.
            dto = commands.ReconfigureRun(
                rid, payload["expected_row_version"], cast("Any", payload["changes"]), args.reason
            )
            result = ctx.client.dispatch(dto, idempotency_key=ctx.new_idempotency_key())
        else:
            result = dispatch(ctx, operation, **payload)
    except SkmError as error:
        if args.verb != "reconfigure":
            raise
        return render_error(
            ctx,
            error,
            command="execution.reconfigure_run",
            extra=[
                "CAS/checkpoint refused; pause the run and drain inflight assignments. Inspect its version.",
                "Use --if-version to apply explicitly; VERSION_CONFLICT is never retried automatically.",
            ],
        )
    return show(
        ctx, "execution." + {"reconfigure": "reconfigure_run"}.get(args.verb, args.verb + "_run"), result
    )


def _inspect(args: argparse.Namespace, ctx: CliContext) -> int:
    rid = run_id(ctx, args.run_ref)
    if args.verb == "follow":
        return follow(ctx, rid, types=args.types, history=args.history)
    operation = {
        "show": queries.GetRun,
        "budget": queries.GetRunBudget,
        "health": queries.GetRunHealth,
        "timeline": queries.GetRunTimeline,
        "tasks": queries.ListTasks,
    }[args.verb]
    payload: dict[str, Any] = {"run_id": str(rid)}
    if args.verb == "timeline":
        payload.update(limit=args.limit, after_seq=args.after_seq)
    if args.verb == "tasks":
        payload["statuses"] = args.status
    view = ask(ctx, operation, **payload)
    command = (
        "execution."
        + {
            "show": "get_run",
            "budget": "get_run_budget",
            "health": "get_run_health",
            "timeline": "get_run_timeline",
            "tasks": "list_tasks",
        }[args.verb]
    )
    if args.verb == "show":
        tasks = ask(ctx, queries.ListTasks, run_id=str(rid))
        result = view.to_json()
        result["pause_source"] = view.pause_source
        result["selection"] = view.selection
        result["blocking_reasons"] = [
            item["blocking_reason"] for item in tasks.tasks if item.get("blocking_reason")
        ]
        if args.tasks or args.graph:
            result["tasks"] = tasks.tasks
        if args.graph:
            keys = {str(item["task_id"]): str(item["display_key"]) for item in tasks.tasks}
            result["graph"] = [
                f"{keys[str(edge['prerequisite_task_id'])]} -> "
                f"{keys[str(edge['dependent_task_id'])]} [{edge['kind']}]"
                for edge in tasks.edges
            ]
        if view.status == "waiting":
            if not ctx.json:
                show(ctx, command, result)
            return render_waiting(
                ctx,
                Waiting(ErrorCode.WAITING_FOR_ANSWER, f"Run {rid} waiting; skm inbox list --run {rid}"),
                command=command,
            )
        show(ctx, command, result)
        return 6 if view.status in {"failed", "cancelled"} else 0
    return show(ctx, command, view)


def _task(args: argparse.Namespace, ctx: CliContext) -> int:
    tid = task_id(ctx, args.task, args.run_ref)
    if args.verb == "task":
        return show(ctx, "execution.get_task", ask(ctx, queries.GetTask, task_id=str(tid)))
    payload: dict[str, Any] = {"task_id": str(tid), "reason": args.reason}
    if args.verb == "restart":
        if not ctx.confirm(f"Restart task {tid}?"):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "restart requires --yes or confirmation")
        operation, name = commands.RestartTask, "restart_task"
    elif args.verb == "skip":
        operation, name = commands.SkipTask, "skip_task"
        payload["decision_ref"] = args.decision
    else:
        operation, name = commands.AcceptDeviation, "accept_deviation"
        payload.update(
            scope="finding" if args.finding else "criterion" if args.criterion else args.deviation_scope,
            finding_id=args.finding,
            criterion_id=args.criterion,
        )
    return show(ctx, "execution." + name, dispatch(ctx, operation, **payload))


def _detail(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.verb == "attempt":
        return show(
            ctx,
            "execution.get_attempt",
            ask(ctx, queries.GetAttempt, attempt_id=str(identifier(args.ref, "attempt"))),
        )
    step = ask(ctx, queries.GetStep, step_id=str(identifier(args.ref, "step")))
    if args.verb == "step":
        return show(ctx, "execution.get_step", step)
    project = str(resolve_project_id(ctx, args.project))
    if args.verb == "step-prompt":
        return _prompt(args, ctx, step, project)
    if args.diff:
        other = ask(ctx, queries.GetStep, step_id=str(identifier(args.diff, "step")))
        result = named_query(
            ctx,
            "context.diff_contexts",
            project_id=project,
            base_manifest_id=str(step.context_manifest_id),
            target_manifest_id=str(other.context_manifest_id),
        )
        return show(ctx, "context.diff_contexts", result)
    result = named_query(
        ctx, "context.explain_context", project_id=project, manifest_id=str(step.context_manifest_id)
    )
    if args.blocks and not ctx.json:
        return show(ctx, "context.explain_context", {"items": result["rows"]})
    return show(ctx, "context.explain_context", result)


def _prompt(args: argparse.Namespace, ctx: CliContext, step: Any, project: str) -> int:
    if args.block is not None and args.block < 0:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "block position must be nonnegative")
    # GetStep projects payload visibility; the context and artifact queries authorize each boundary.
    # Emit nothing until both queries and the artifact opener have authorized this request.
    if step.payload_visibility == "restricted":
        raise Forbidden(ErrorCode.FORBIDDEN, "file.read is required for this prompt")
    result = named_query(
        ctx,
        "context.get_context_text",
        project_id=project,
        manifest_id=str(step.context_manifest_id),
    )
    reference = result["prompt_file_version_id"]
    if reference is None:
        raise Forbidden(ErrorCode.FORBIDDEN, "prompt artifact is unavailable or access is restricted")
    version = identifier(str(reference), "file_version")
    named_query(ctx, "artifacts.get_file_version", file_version_id=str(version))
    with ctx.client.open_file_version_content(FileVersionId(version)) as stream:
        content = stream.read() if args.block is None else b""
    if args.block is None:
        text = content.decode("utf-8")
    else:
        result = named_query(
            ctx,
            "context.get_context_text",
            project_id=project,
            manifest_id=str(step.context_manifest_id),
            position=args.block,
        )
        if not result["available"] or result["text"] is None:
            raise ValidationFailed(ErrorCode.NOT_FOUND, "context block text is unavailable")
        text = result["text"]
    return render(
        ctx,
        {"text": text},
        human=lambda _: text,
        command="context.get_context_text",
        essential=lambda _: text,
    )


def _logs(args: argparse.Namespace, ctx: CliContext) -> int:
    from skm.entrypoints.cli._run_logs import logs

    return logs(args, ctx)


def _carry(args: argparse.Namespace, ctx: CliContext) -> int:
    return show(
        ctx,
        "execution.carry_forward_result",
        dispatch(
            ctx,
            commands.CarryForwardResult,
            source_task_id=str(task_id(ctx, args.source)),
            target_task_id=str(task_id(ctx, args.target)),
            reason=args.reason,
        ),
    )


def register(sub: SubParsers) -> None:  # noqa: PLR0912, PLR0915 - one parser branch per verb
    parser = sub.add_parser("run", help=GROUP.help)
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in (
        "export",
        "readiness",
        "start",
        "local",
        "list",
        "show",
        "follow",
        "pause",
        "resume",
        "cancel",
        "reconfigure",
        "budget",
        "timeline",
        "health",
        "tasks",
        "task",
        "restart",
        "skip",
        "attempt",
        "step",
        "step-context",
        "step-prompt",
        "logs",
        "deviation",
        "carry-forward",
    ):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        command.add_argument("--yes", action="store_true", default=argparse.SUPPRESS)
        if verb == "export":
            register_run_report_args(command)
        elif verb in ("readiness", "start"):
            command.add_argument("plan")
            command.add_argument("--revision")
            command.add_argument("--set", dest="run_sets", action="append")
            command.add_argument("--workflow")
            command.add_argument("--tasks", action="append")
            command.add_argument("--phase", action="append")
            command.add_argument("--mode", choices=("full", "progressive_per_phase"))
            if verb == "start":
                command.add_argument(
                    "--visa-id", "--visa", dest="visa", help="use the signed readiness report"
                )
            else:
                command.add_argument(
                    "--semantic-audit", action="store_true", help="start a semantic audit when ready"
                )
            command.add_argument("--stop-after")
            command.add_argument("--reason", default="CLI run start")
            command.add_argument("--follow", action="store_true")
            command.add_argument("--skip-readiness", action="store_true")
            command.set_defaults(run=_start)
        if verb == "local":
            command.add_argument("--ephemeral", action="store_true", required=True)
            command.add_argument("--model", required=True)
            command.add_argument("prompt_file", type=Path)
            command.set_defaults(run=_local, host_local=True)
        if verb == "list":
            command.add_argument("--project")
            command.add_argument("--plan")
            command.add_argument("--status", action="append")
            command.add_argument("--after")
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--all", action="store_true")
            command.set_defaults(run=_list)
        if verb in (
            "show",
            "follow",
            "pause",
            "resume",
            "cancel",
            "reconfigure",
            "budget",
            "timeline",
            "health",
            "tasks",
        ):
            command.add_argument("run_ref", metavar="RUN")
            command.set_defaults(run=_route_run)
        if verb in ("pause", "resume", "cancel", "reconfigure"):
            command.add_argument("--reason", default="CLI run control")
        if verb == "reconfigure":
            command.add_argument("changes", nargs="+")
            command.add_argument("--if-version", type=int)
        if verb == "show":
            command.add_argument("--tasks", action="store_true")
            command.add_argument("--graph", action="store_true")
        if verb == "follow":
            command.add_argument("--types", action="append")
            command.add_argument("--history", action="store_true")
        if verb == "timeline":
            command.add_argument("--limit", type=int, default=100)
            command.add_argument("--after-seq", type=int)
        if verb == "tasks":
            command.add_argument("--status", action="append")
        if verb in ("task", "restart", "skip"):
            command.add_argument("task")
            command.add_argument("--run", dest="run_ref")
            command.set_defaults(run=_task)
        if verb in ("restart", "skip"):
            command.add_argument("--reason", required=True)
        if verb == "skip":
            command.add_argument("--decision")
        if verb in ("attempt", "step", "step-context", "step-prompt"):
            command.add_argument("ref")
            command.set_defaults(run=_detail)
        if verb == "step-context":
            command.add_argument("--project")
            command.add_argument("--diff")
            command.add_argument("--blocks", action="store_true")
        if verb == "step-prompt":
            command.add_argument("--project")
            command.add_argument("--block", type=int)
        if verb == "logs":
            command.add_argument("ref", metavar="ATTEMPT")
            command.add_argument("--step")
            command.add_argument("--transcript", action="store_true")
            command.add_argument("--follow", action="store_true")
            command.set_defaults(run=_logs)
        if verb == "deviation":
            actions = command.add_subparsers(required=True)
            accept = actions.add_parser("accept", help="accept a deviation")
            accept.add_argument("task")
            accept.add_argument("--run", dest="run_ref")
            accept.add_argument("--finding")
            accept.add_argument("--criterion")
            accept.add_argument(
                "--scope",
                dest="deviation_scope",
                choices=("coverage", "attention_verdict"),
                default="attention_verdict",
            )
            accept.add_argument("--reason", required=True)
            accept.set_defaults(run=_task)
        if verb == "carry-forward":
            command.add_argument("--from", dest="source", required=True)
            command.add_argument("--to", dest="target", required=True)
            command.add_argument("--reason", required=True)
            command.set_defaults(run=_carry)
        if verb != "export":
            command.set_defaults(command_name="run." + verb)


def _route_run(args: argparse.Namespace, ctx: CliContext) -> int:
    return (
        _control(args, ctx)
        if args.verb in {"pause", "resume", "cancel", "reconfigure"}
        else _inspect(args, ctx)
    )


GROUP = CommandGroup(
    name="run",
    help="start, inspect and control execution runs",
    register=register,
    module="execution",
    order=30,
)

__all__ = ["GROUP"]
