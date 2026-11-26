"""Thin autopilot bus surface and project/current-run event display (PARITY-12)."""

import argparse
import json
import math
import time
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from functools import partial
from pathlib import Path
from typing import Any, cast

from skm.entrypoints.cli._run_io import ask, dispatch, named_query, operations, show
from skm.entrypoints.cli.commands import CommandGroup, SubParsers
from skm.entrypoints.cli.commands.project import resolve_project_id
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, to_jsonable
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.events import EventEnvelope
from skm.modules.settings import public as settings
from skm.modules.workspace.public import GetProject
from skm.platform.fs.atomic_write import UnsafePathError, assert_safe_replace_target, atomic_write
from skm.platform.fs.file_lock import FileLock, LockTimeout

__all__ = ["GROUP", "follow", "register"]

commands = operations("execution", writes=True)
queries = operations("execution")
_HELP = {
    "enable": "enable the approved project queue",
    "disable": "disable automatic dispatch",
    "start": "start or continue the persisted campaign session",
    "pause": "pause new runs while existing runs continue",
    "drain": "wait for current runs, then return to idle",
    "stop": "stop dispatch; emergency also cancels project runs",
    "status": "show campaign state, counters and approved queue",
    "explain": "explain configuration provenance and ordered stop conditions",
    "follow": "follow project events and the current run, switching when it changes",
}


def _duration(text: str) -> int:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        seconds = int(text[:-1]) * units[text[-1]] if text[-1:] in units else int(text)
    except (ValueError, KeyError) as error:
        raise argparse.ArgumentTypeError("expected seconds or a duration such as 2h") from error
    if seconds < 60:
        raise argparse.ArgumentTypeError("max wall must be at least 60 seconds")
    return seconds


def _line(ctx: CliContext, text: str, data: Any) -> None:
    render(ctx, data, command="autopilot.follow", human=lambda _: text, essential=lambda _: text)
    ctx.stdout.flush()


def _finish(ctx: CliContext, status: Any) -> int | None:
    state = status["effective_state"]
    if state in {"paused", "disabled"}:
        return 4
    if state == "idle":
        return 0
    if state == "stopped":
        code = status.get("stop_code")
        return (
            0
            if code
            in {
                "AUTOPILOT_NO_WORK",
                "AUTOPILOT_DRAINED",
                "AUTOPILOT_STOPPED",
                "AUTOPILOT_MAX_RUNS",
                "AUTOPILOT_MAX_WALL",
                "AUTOPILOT_DISABLED",
                "AUTOPILOT_BUSY",
            }
            else 6
        )
    rid = status.get("current_run_id")
    if rid:
        run: Any = to_jsonable(ask(ctx, queries.GetRun, run_id=rid))
        if run["status"] in {"waiting", "paused"}:
            return 4
    return None


def _seconds(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("seconds must be finite and nonnegative")
    return value


def follow(
    ctx: CliContext,
    project: Any,
    *,
    cursor_file: Path | None = None,
    seconds: float | None = None,
    lock: str | None = None,
) -> int:
    if lock == "" and cursor_file is None:
        raise error_for(ErrorCode.SCHEMA_INVALID, "--lock requires a path or --cursor-file")
    lock_path = Path(lock or f"{cursor_file}.lock") if lock is not None else None
    if lock_path and cursor_file and lock_path.resolve() == cursor_file.resolve():
        raise error_for(ErrorCode.SCHEMA_INVALID, "lock and cursor must use separate files")
    try:
        if lock_path:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(lock_path).hold(timeout_seconds=0) if lock_path else nullcontext():
            return _watch(ctx, project, cursor_file, seconds)
    except LockTimeout as exc:
        raise error_for(ErrorCode.CHECKOUT_BUSY, "another follower holds the lock") from exc
    except (OSError, UnsafePathError) as exc:
        raise error_for(ErrorCode.INVALID_REFERENCE, "cannot access follower state") from exc


def _checkpoint(path: Path, scope: dict[str, str], head: int) -> int:
    assert_safe_replace_target(path)
    try:
        doc = json.loads(path.read_bytes())
    except FileNotFoundError:
        atomic_write(path, json.dumps({**scope, "after": head}).encode(), mode=0o600)
        return head
    except ValueError as exc:
        raise error_for(ErrorCode.SCHEMA_INVALID, "invalid follow cursor") from exc
    cursor = cast("dict[str, object]", doc) if isinstance(doc, dict) else {}
    if any(cursor.get(k) != v for k, v in scope.items()):
        raise error_for(ErrorCode.INVALID_REFERENCE, "cursor belongs to another feed")
    after = cursor.get("after")
    if type(after) is not int or not 0 <= after <= head:
        raise error_for(ErrorCode.SCHEMA_INVALID, "cursor outside the workspace feed")
    return after


def _watch(ctx: CliContext, project: Any, cursor_file: Path | None, seconds: float | None) -> int:
    project_id = str(project)
    deadline = None if seconds is None else time.monotonic() + seconds
    try:
        status, meta = ctx.client.ask_with_meta(queries.GetAutopilotStatus({"project_id": project_id}))
    except SkmError as error:
        if error.code is not ErrorCode.FORBIDDEN:
            raise
        # A project.read-only credential can follow project transitions without reading run status.
        details, meta = ctx.client.ask_with_meta(GetProject.from_json({"project_id": project_id}))
        workspace = cast("Any", details).workspace_id
        status = None
    else:
        if cursor_file is None and (code := _finish(ctx, status)) is not None:
            return code
        workspace = named_query(ctx, "workspace.get_project", project_id=project_id).workspace_id
    if meta.events_cursor is None:
        raise error_for(ErrorCode.CAPABILITY_UNAVAILABLE, "project feed has no event cursor")
    scope = {"workspace_id": str(workspace), "project_id": project_id}
    after = _checkpoint(cursor_file, scope, meta.events_cursor) if cursor_file else meta.events_cursor
    if (
        status is not None
        and cursor_file
        and after == meta.events_cursor
        and (code := _finish(ctx, status)) is not None
    ):
        return code
    project_events = getattr(ctx.client, "project_events", None)
    stream = (
        partial(
            cast("Callable[..., Iterator[EventEnvelope]]", project_events),
            project_id=project,
            workspace_id=workspace,
        )
        if callable(project_events)
        else partial(ctx.client.events, workspace_id=workspace)
    )
    return _follow_events(ctx, scope, stream, after, cursor_file, deadline, status)


def _current_run(ctx: CliContext, previous: str | None, view: Any) -> str | None:
    current = view.get("current_run_id") if view else None
    if current != previous:
        _line(ctx, f"-- autopilot switched to run {current} --", {"current_run_id": current})
    return current


def _follow_events(
    ctx: CliContext,
    scope: dict[str, str],
    stream: Callable[..., Iterator[EventEnvelope]],
    after: int,
    cursor_file: Path | None,
    deadline: float | None,
    view: Any,
) -> int:
    project_id = scope["project_id"]
    can_read_runs = view is not None
    current = _current_run(ctx, None, view)
    while True:
        wait = 0.5 if deadline is None else min(0.5, deadline - time.monotonic())
        if wait <= 0:
            return 0
        for event in stream(after=after, wait_seconds=wait):
            if can_read_runs:
                view = ask(ctx, queries.GetAutopilotStatus, project_id=project_id)
                current = _current_run(ctx, current, view)
            project_event = event.stream_kind == "project" and str(event.stream_id) == project_id
            if project_event or (event.stream_kind == "run" and str(event.stream_id) == current):
                # Event bodies can contain sensitive result content. Display only envelope metadata.
                data = {
                    "type": event.type,
                    "stream_kind": event.stream_kind,
                    "stream_id": str(event.stream_id),
                }
                _line(ctx, f"{event.type}  {event.stream_kind}:{event.stream_id}", data)
            after = event.workspace_seq or after
            if cursor_file:
                atomic_write(cursor_file, json.dumps({**scope, "after": after}).encode(), mode=0o600)
            if (
                not can_read_runs
                and project_event
                and event.type == "urn:skm:execution:event:autopilot-state-changed:v1"
            ):
                view = {"effective_state": event.payload["to"], "stop_code": event.payload.get("code")}
            if deadline is not None and time.monotonic() >= deadline:
                return 0
        if can_read_runs:
            view = ask(ctx, queries.GetAutopilotStatus, project_id=project_id)
            current = _current_run(ctx, current, view)
        if view is not None and (code := _finish(ctx, view)) is not None:
            return code


def _run(args: argparse.Namespace, ctx: CliContext) -> int:
    project = resolve_project_id(ctx, args.project)
    verb = args.verb
    if verb == "follow":
        return follow(ctx, project, cursor_file=args.cursor_file, seconds=args.seconds, lock=args.lock)
    if verb in {"enable", "disable"}:
        result = dispatch(
            ctx,
            settings.SetValue,
            scope={"level": "project", "scope_id": str(project)},
            key="execution.autopilot.enabled",
            value=verb == "enable",
            reason=args.reason,
            confirmed=ctx.assume_yes,
        )
        return show(ctx, "settings.set_value", result)
    if verb in {"status", "explain"}:
        operation = queries.GetAutopilotStatus if verb == "status" else queries.ExplainAutopilot
        return show(
            ctx,
            "execution." + ("get_autopilot_status" if verb == "status" else "explain_autopilot"),
            ask(ctx, operation, project_id=str(project)),
        )
    payload = {"project_id": str(project), "reason": args.reason}
    if verb == "pause" and args.stop_after:
        payload["stop_after"] = args.stop_after
    session = None
    if verb == "start":
        previous = ask(ctx, queries.GetAutopilotStatus, project_id=str(project))
        session = "new" if args.new_session or previous["state"] == "idle" else "continued"
        if args.new_session and not args.reason.strip():
            raise error_for(ErrorCode.SCHEMA_INVALID, "--new-session requires --reason")
        payload.update(
            new_session=args.new_session,
            clear_emergency=args.clear_emergency,
            limits={
                key: val
                for key, val in (
                    ("max_runs", args.max_runs),
                    ("max_wall_seconds", args.max_wall),
                    ("max_auto_decisions", args.max_auto_decisions),
                )
                if val is not None
            },
        )
    if verb == "stop":
        if not ctx.confirm(f"Stop autopilot for {project}?"):
            raise error_for(ErrorCode.SCHEMA_INVALID, "stop requires --yes or confirmation")
        payload["emergency"] = args.emergency
    operation = {
        "start": commands.StartAutopilot,
        "pause": commands.PauseAutopilot,
        "drain": commands.DrainAutopilot,
        "stop": commands.StopAutopilot,
    }[verb]
    result = dispatch(ctx, operation, **payload)
    if verb == "start":
        return render(
            ctx,
            result,
            command="execution.start_autopilot",
            human=lambda _: f"{result['state']}; session: {session}",
        )
    return show(ctx, "execution." + verb + "_autopilot", result)


def register(sub: SubParsers) -> None:
    verbs = sub.add_parser("autopilot", help="control the approved queue campaign").add_subparsers(
        dest="verb", required=True
    )
    for verb in ("enable", "disable", "start", "pause", "drain", "stop", "status", "explain", "follow"):
        command = verbs.add_parser(verb, help=_HELP[verb])
        command.add_argument("--project")
        command.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        command.add_argument("--yes", action="store_true", default=argparse.SUPPRESS)
        if verb in ("enable", "disable", "start", "pause", "drain", "stop"):
            command.add_argument("--reason", required=verb == "stop", default="")
        if verb == "pause":
            command.add_argument(
                "--stop-after", metavar="STEP_ID", help="pause the run when its current step ends"
            )
        if verb == "follow":
            command.add_argument("--cursor-file", type=Path, help="persist the last consumed workspace event")
            command.add_argument("--seconds", type=_seconds, help="return after this many seconds")
            command.add_argument(
                "--lock",
                nargs="?",
                const="",
                metavar="PATH",
                help="hold an exclusive lock (default: CURSOR.lock)",
            )
        if verb == "start":
            command.add_argument("--new-session", action="store_true")
            command.add_argument("--clear-emergency", action="store_true")
            command.add_argument("--max-runs", type=int)
            command.add_argument("--max-wall", type=_duration)
            command.add_argument("--max-auto-decisions", type=int)
        if verb == "stop":
            command.add_argument("--emergency", action="store_true")
        command.set_defaults(run=_run)


GROUP = CommandGroup("autopilot", "control the approved queue campaign", register, module="execution")
