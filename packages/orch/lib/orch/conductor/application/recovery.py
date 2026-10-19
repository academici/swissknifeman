"""Stop the unfinished role groups of a conductor that lost its lease."""
from __future__ import annotations

import os
import signal
import time

from orch.conductor import process
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import read_json, safe


def kill_orphaned_roles(run) -> None:
    """Called under checkout and run ownership, before retry or any new role can start.

    Missing steps count as unfinished too: older journals wrote only completed steps.
    A pid alone is never authority to signal a process group.
    """
    for path in sorted(run.directory.glob("*/agents/*/process.json")):
        request = read_json(path.with_name("request.json")) or {}
        item = next((ref for ref in run.state.get("items", {}) if safe(ref) == path.parents[2].name), None)
        step = request.get("step")
        steps = run.state.get("items", {}).get(item, {}).get("steps", {})
        if not step or steps.get(step, {}).get("status") == "done":
            continue
        doc = read_json(path) or {}
        pid, pgid, ticks = doc.get("pid"), doc.get("pgid"), doc.get("start_ticks")
        if (type(pid) is not int or pid <= 1 or pgid != pid or type(ticks) is not int
                or process.start_ticks(pid) != ticks):
            continue
        try:
            if os.getpgid(pid) != pgid or pgid == os.getpgrp():
                continue
            if not process._group_alive(pgid):
                continue
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError as error:
            raise Stop("ROLE_FAILED", f"cannot stop orphaned role group {pgid}: {error}") from None
        deadline = time.monotonic() + 10
        while process._group_alive(pgid) and time.monotonic() < deadline:
            time.sleep(0.02)
        if process._group_alive(pgid):
            current = process.start_ticks(pid)
            if current is not None and current != ticks:
                raise Stop("ROLE_FAILED", f"orphaned role pid {pid} changed identity during recovery")
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as error:
                raise Stop("ROLE_FAILED", f"cannot kill orphaned role group {pgid}: {error}") from None
            deadline = time.monotonic() + 10
            while process._group_alive(pgid) and time.monotonic() < deadline:
                time.sleep(0.02)
            if process._group_alive(pgid):
                raise Stop("ROLE_FAILED", f"orphaned role group {pgid} is still alive; no new role was started")
        run.progress.emit("info", item=item, stage=step, reason_code="ROLE_ORPHAN_KILLED",
                          message=f"stopped orphaned role group {pgid}")
