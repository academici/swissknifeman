"""Stop orphaned role groups and reconcile interrupted steps without discarding work."""
from __future__ import annotations

import os
import signal
import time

from orch.conductor import checks, process, prompts
from orch.conductor.domain.stop import Stop
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure import clock, work_source
from orch.conductor.infrastructure.files import read_json, safe


def dirty_paths(project, limit: int = 500) -> list:
    """Sorted porcelain paths, including both names of renames and all untracked files."""
    try:
        entries = checks.git(project, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    except RuntimeError:
        try:
            checks.git(project, "rev-parse", "--git-dir")
        except RuntimeError:
            return []  # a step can also be journalled outside a git repository
        raise
    found, index = set(), 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        found.add(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            if index < len(entries) and entries[index]:
                found.add(entries[index])
                index += 1
    return sorted(found)[:limit]


def reconcile_interrupted(run) -> None:
    """L10 recovery under ownership, after orphaned writers have stopped.

    Removing a started record authorizes a repeat, never a successful result.
    Notes survive a second crash before the executor reports.
    """
    repeated = {"brief", "prepare", "scout", "research", "review", "triage", "advice", "research-save"}
    try:
        state_saved_ns = (run.directory / "state.json").stat().st_mtime_ns
    except OSError:
        state_saved_ns = None
    for ref, item in run.state.get("items", {}).items():
        steps = item.get("steps", {})
        if item.get("outcome") in ("done", "done_with_deviations", "blocked", "abandoned"):
            unfinished = [key for key, step in steps.items() if step.get("status") in ("started", "stopped")]
            for key in unfinished:
                del steps[key]
            if unfinished:
                run._save()
            continue  # a closed item has no work to repeat, including unknown steps
        for key, step in list(steps.items()):
            if step.get("status") != "started":
                continue
            prefix = key.split(".", 1)[0]
            message = "repeated"
            if key in ("close", "register", "commit"):
                recovering = Item(ref, item.get("orch_run", ""), item, run.directory / safe(ref),
                                  {"attempt_id": step.get("attempt")})
                receipt = work_source.read_receipt(recovering, key, project=run.project)
                closes, message = work_source.receipt_closes(key, receipt, recovering, state_saved_ns=state_saved_ns)
                if closes:
                    result = work_source.receipt_result(key, receipt)
                    verdict = ("closer ran" if key == "close" else
                               f"{result['outcome']} gate {result['gate']}" if key == "register" else
                               " ".join(str(result[k]) for k in ("outcome", "sha", "message") if result.get(k)))
                    steps[key] = {"status": "done", "result": result, "verdict": verdict,
                                  "role": step.get("role", "deterministic"), "route": step.get("route"),
                                  "duration_s": 0, "ended": clock.utc_now()}
                    run._save()
                    run.progress.emit("info", item=ref, stage=key, reason_code="STAGE_INTERRUPTED", message=message)
                    continue
            elif prefix == "executor":
                paths = dirty_paths(run.project, 200)
                item.setdefault("interrupted_note", {})[key] = prompts.interrupted_correction(step.get("base_head"), paths)
                message = "repeated with interruption note"
            elif prefix == "checks":
                paths = dirty_paths(run.project)
                if paths != step.get("dirty_before"):
                    message = "repeated after tree change"
                    run.progress.emit("info", item=ref, stage=key, reason_code="CHECK_CHANGED_TREE",
                                      message="the tree differs from dirty_before; the interrupted checks are repeated")
            elif prefix not in repeated:
                run.progress.emit("info", item=ref, stage=key, reason_code="STAGE_INTERRUPTED", message="no recovery rule")
                raise Stop("STAGE_RECOVERY_UNKNOWN", f"{ref} {key}: no recovery rule; settle the item or retry it")
            del steps[key]
            run._save()
            run.progress.emit("info", item=ref, stage=key, reason_code="STAGE_INTERRUPTED", message=message)


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
