"""Server-scoped run polling with a synchronized GetRun cursor and explicit history (PARITY-12)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from skm.entrypoints.cli._run_io import ask, operations
from skm.entrypoints.cli.context import CliContext
from skm.entrypoints.cli.output import render, render_waiting
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.outcomes import Waiting

GetRun = operations("execution").GetRun
GetRunHistory = operations("execution").GetRunHistory
GetRunTimeline = operations("execution").GetRunTimeline
ListTasks = operations("execution").ListTasks


class RunView(Protocol):
    @property
    def run_id(self) -> UUID: ...
    @property
    def status(self) -> str: ...
    @property
    def finished_at(self) -> datetime | None: ...


_TERMINAL = frozenset({"succeeded", "failed", "cancelled"})


def _finish(ctx: CliContext, view: RunView) -> int | None:
    if view.status == "waiting":
        return render_waiting(
            ctx,
            Waiting(
                ErrorCode.WAITING_FOR_ANSWER, f"Run {view.run_id} waiting; skm inbox list --run {view.run_id}"
            ),
            command="execution.get_run",
        )
    if view.status not in _TERMINAL:
        return None
    text = f"run {view.run_id} finished: {view.status} at {view.finished_at}"
    render(
        ctx,
        view,
        human=lambda _, line=text: line,
        command="execution.get_run",
        essential=lambda _, line=text: line,
    )
    return 0 if view.status == "succeeded" else 6


def _short(urn: str) -> str:
    return "".join(part.title() for part in urn.split(":")[-2].split("-"))


def _snapshot(ctx: CliContext, rid: UUID, *, history: bool) -> tuple[RunView, int | None]:
    # Embedded events() has no stream selector. GetRunHistory/GetRunTimeline filter stream_kind=run,
    # stream_id=rid in the repository. Match their workspace watermark to GetRun.events_cursor before
    # translating that snapshot into a run stream sequence; do not mix workspace and stream counters.
    while True:
        raw, meta = ctx.client.ask_with_meta(GetRun(rid))
        view = cast("RunView", raw)
        if not history and (view.status in _TERMINAL or view.status == "waiting"):
            return view, None
        if meta.events_cursor is None:
            raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "get_run returned no events_cursor")
        head, head_meta = ctx.client.ask_with_meta(GetRunHistory(rid, limit=1))
        if head_meta.events_cursor == meta.events_cursor:
            return view, cast("Any", head).through_seq
        # A concurrent commit moved the watermark. Refresh the read handshake only, never a command.


def _page(
    ctx: CliContext,
    rid: UUID,
    after: int,
    *,
    through: int | None,
    keys: dict[str, str],
    types: Sequence[str] | None,
    history: bool,
) -> int:
    while True:
        page = ask(ctx, GetRunTimeline, run_id=str(rid), after_seq=after, limit=100)
        for item in page.items:
            seq = int(item["seq"])
            if through is not None and seq > through:
                return through
            after = seq
            urn = str(item["event_type"])
            if types and urn not in types and _short(urn) not in types:
                continue
            task = keys.get(str(item.get("task_id")), "-")
            # Render the authorized timeline projection, not raw workspace event payloads.
            text = (
                f"{'history ' if history else ''}{str(item['at'])[11:19]}  "
                f"{_short(urn)}  {task}  {item.get('summary', '')}"
            )
            render(
                ctx,
                {"history": history, "event": item},
                human=lambda _, line=text: line,
                command="run.follow",
                essential=lambda _, line=text: line,
            )
            ctx.stdout.flush()
        if page.next_after is None or (through is not None and after >= through):
            return after


def follow(ctx: CliContext, rid: UUID, *, types: Sequence[str] | None = None, history: bool = False) -> int:
    view, head = _snapshot(ctx, rid, history=history)
    if head is None:
        return cast("int", _finish(ctx, view))
    tasks = ask(ctx, ListTasks, run_id=str(rid))
    keys = {str(item["task_id"]): str(item["display_key"]) for item in tasks.tasks}
    if history:
        _page(ctx, rid, 0, through=head, keys=keys, types=types, history=True)
    if (code := _finish(ctx, view)) is not None:
        return code
    after = head
    while True:
        after = _page(ctx, rid, after, through=None, keys=keys, types=types, history=False)
        view = cast("RunView", ctx.client.ask(GetRun(rid)))
        if view.status in _TERMINAL or view.status == "waiting":
            _page(ctx, rid, after, through=None, keys=keys, types=types, history=False)
            return cast("int", _finish(ctx, view))
        time.sleep(0.5)


__all__ = ["GetRun", "GetRunHistory", "GetRunTimeline", "ListTasks", "RunView", "follow"]
