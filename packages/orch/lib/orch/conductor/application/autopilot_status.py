"""The files of the autopilot of a project and the verbs that only read them or ask the controller: ``status``, ``request``
(``pause``, ``resume``, ``drain``, ``stop``) and ``explain``, with the helpers the controller shares (``application/autopilot.py``).

``<runs root>/autopilot.json`` (records/v1 ``autopilot-state``) is written only by the controller that holds ``autopilot.lock``;
``autopilot.request.json`` (records/v1 ``autopilot-request``) only by ``request``.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from typing import Callable, Optional

from aicore.util import timefmt
from aicore.util.lock import probe_free

from orch.conductor import process, records
from orch.conductor.application import run_service, supervisor
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock as clock_mod, work_source
from orch.conductor.infrastructure.files import STATE_FILE, runs_root, safe
from orch.conductor.infrastructure.lease import RunLease
from orch.conductor.policies import autopilot as rules

STATE_DOC = "autopilot.json"
REQUEST_DOC = "autopilot.request.json"
LOCK_FILE = "autopilot.lock"
OPTIONS_DOC = "autopilot-options.json"
DETACHED = "detached"
IDENTITY = ("pid", "start_ticks", "boot_id")  # a child is signalled only while all three still match


def epoch(stamp: Optional[str]) -> float:
    found = timefmt.epoch(stamp) if isinstance(stamp, str) else None
    return found if found is not None else 0.0


def source_readiness(project: Path, plan: str, config_file: Optional[Path] = None) -> dict:
    """The work-source ``readiness`` answer of ``plan`` (P8.7 ``source_readiness``; never raises)."""
    owner = SimpleNamespace(project=Path(project), project_resolution=None, config_file=config_file, env=dict(os.environ))
    owner._orch = functools.partial(work_source.run_orch, owner)
    return work_source.source_readiness(owner, plan)


def plan_folders(project: Path, state: dict) -> tuple:
    """The folders of the plan inside the checkout that the work source itself named: the ``artifacts_dir`` of a brief of the
    run is ``<plan folder>/artifacts/<ref>`` when the plan lies in the checkout (the planner bridge names none for a plan in a
    workspace, and a file input none at all). A folder that is not of that form or leaves the checkout is not taken: an
    unknown plan folder excludes nothing."""
    root = Path(project).resolve()
    found = []
    for ref, piece in sorted((state.get("items") or {}).items()):
        named = ((((piece or {}).get("steps") or {}).get("brief") or {}).get("result") or {}).get("artifacts_dir")
        suffix = f"/artifacts/{ref}"
        if not isinstance(named, str) or not named.endswith(suffix) or Path(named).is_absolute():
            continue
        folder = named[:-len(suffix)].strip("/")
        try:
            inside = (root / folder).resolve().relative_to(root).as_posix()
        except ValueError:
            continue
        if folder and inside == folder and outside_plan(folder, ()):  # not the fallback under .swissknifeman
            found.append(folder)
    return tuple(dict.fromkeys(found))


def outside_plan(path: str, folders) -> bool:
    """``path`` (relative to the checkout) lies outside ``.swissknifeman/`` and the known folders of the plan (``folders``,
    from ``plan_folders``), compared by whole folders: ``src/<plan>/x`` or ``plans/<plan>/x`` of an unknown plan folder is a
    product file."""
    excluded = (".swissknifeman", *folders)
    return not any(path == folder or path.startswith(folder + "/") for folder in excluded)


def tracked_changes(project: Path, folders=()) -> bool:
    """Tracked changes in the checkout outside ``.swissknifeman/`` and the known folders of the plan (``git status
    --porcelain --untracked-files=no``); a git that does not answer counts as changes (the safe side)."""
    try:
        done = subprocess.run(["git", "-C", str(project), "status", "--porcelain", "--untracked-files=no"],
                              capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return True
    if done.returncode != 0:
        return True
    paths = [part.strip('"') for line in done.stdout.splitlines() if line.strip() for part in line[3:].split(" -> ")]
    return any(outside_plan(path, folders) for path in paths)  # both sides of a rename


def child_problem(directory: Path, current: dict) -> Optional[str]:
    """Why the child of ``current`` may not be signalled (``None``: it is the process the controller started or adopted). The
    saved ``(pid, start_ticks, boot_id)`` must all be known and match ``/proc`` and the boot of the machine, and a held lease
    must name exactly that process: a pid alone, or a pid with its ticks from another boot, is no authority (I13)."""
    pid, ticks, boot = (current.get(key) for key in IDENTITY)
    if type(pid) is not int or pid <= 1 or type(ticks) is not int or not boot:
        return "the identity of the child (pid, start_ticks, boot_id) is not known"
    if pid == os.getpid():
        return "the saved child is the controller itself"
    if boot != process.boot_id():
        return f"pid {pid} was started in another boot of the machine"
    if process.start_ticks(pid) != ticks:
        return f"pid {pid} is not the child any more (start_ticks differ or it is gone)"
    if RunLease.held(directory) is True:
        owner = RunLease.owner(directory)
        if tuple(owner.get(key) for key in IDENTITY) != (pid, ticks, boot):
            return f"the run is held by pid {owner.get('pid')} (start_ticks {owner.get('start_ticks')}), not by the child pid {pid}"
        return supervisor.identity_problem(owner)
    return None


def escalations(piece: dict) -> list:
    """The escalation texts of the last executor round of a blocked piece that reported ``blocked``."""
    steps = piece.get("steps") or {}
    rounds = sorted((key for key in steps if key.startswith("executor.")), key=lambda key: steps[key].get("ended") or "")
    for key in reversed(rounds):
        report = ((steps[key].get("result") or {}).get("report") or {})
        if report.get("status") == "blocked":
            return [issue.get("text", "") for issue in report.get("open_issues") or [] if issue.get("kind") == "escalation"]
    return []


def alive(root: Path) -> bool:
    """A controller holds ``autopilot.lock`` of the runs root ``root``."""
    lock = Path(root) / LOCK_FILE
    return lock.exists() and probe_free(lock) is False


def still_waiting(root: Path, row: dict) -> bool:
    """A run of ``waiting_runs`` still waits: a piece of its state waits, or a conductor holds it, or its state cannot be read
    (kept: the owner decides). A run continued and finished by hand no longer waits."""
    directory = Path(root) / row["run_id"]
    try:
        state = records.read(directory / STATE_FILE, "state")
    except Stop:
        return True
    return state is not None and (bool(run_service.waiting_pieces(state)) or RunLease.held(directory) is True)


def answered_run(root: Path, waiting: list) -> Optional[str]:
    """The first waiting run whose waiting pieces have all their blocking questions answered (``open`` with a resolution,
    ``answered`` or ``applied``) and whose lease nobody holds."""
    for row in waiting:
        directory = Path(root) / row["run_id"]
        try:
            state = records.read(directory / STATE_FILE, "state") or {}
        except Stop:
            continue
        pieces = run_service.waiting_pieces(state)
        if not pieces or RunLease.held(directory) is True:
            continue
        if all(not run_service.unanswered(directory / safe(piece["item"]), piece) for piece in pieces):
            return row["run_id"]
    return None


def status(project: Path) -> dict:
    """``orch conduct autopilot status --json``: conductor/v1 ``autopilot-status``. ``dead`` is a session that did not stop
    and whose controller no longer holds the lock."""
    root = runs_root(Path(project))
    state = records.read(root / STATE_DOC, "autopilot-state")
    try:
        request = records.read(root / REQUEST_DOC, "autopilot-request")
    except Stop:
        request = None
    live = alive(root)
    found = "none" if state is None else state["mode"] if live or state["mode"] == "stopped" else "dead"
    return {"$schema": "urn:swissknifeman:orch:conductor:autopilot-status:v1", "status": found, "alive": live,
            "state": state, "request": request}


def request(project: Path, action: str, by: str) -> dict:
    """Write ``autopilot.request.json`` for the live controller (``AUTOPILOT_NOT_RUNNING`` without one)."""
    root = runs_root(Path(project))
    if not alive(root):
        raise Stop("AUTOPILOT_NOT_RUNNING", f"no autopilot controller holds {root / LOCK_FILE}; nothing to {action}")
    doc = {"$schema": records.TAGS["autopilot-request"][1], "action": action, "at": clock_mod.utc_now(), "by": by or "unknown"}
    records.write(root / REQUEST_DOC, doc, "autopilot-request")
    return doc


def explain(project: Path, plan: Optional[str], settings, *, flags: Optional[dict] = None,
            readiness: Optional[Callable] = None, config_file: Optional[Path] = None) -> dict:
    """``orch conduct autopilot explain``: the effective policy with the source of each value, the readiness of the source and
    the next action a controller would take now (conductor/v1 ``autopilot-explain``). Starts nothing, writes nothing."""
    root = runs_root(Path(project))
    state = records.read(root / STATE_DOC, "autopilot-state") or {}
    plan = plan or state.get("plan")
    if not plan:
        raise Stop("PLAN_REQUIRED", "no autopilot session names a plan: give --plan")
    policy, sources = rules.effective_policy(getattr(settings, "autopilot", None) or {}, flags or {})
    same = state.get("plan") == plan
    waiting = list(state.get("waiting_runs") or []) if same else []
    found = None
    if not policy["allowed"]:
        choice = {"action": "stop", "code": "AUTOPILOT_NOT_ALLOWED", "message": "the machine does not allow the autopilot"}
    elif not policy["enabled"]:
        choice = {"action": "stop", "code": "AUTOPILOT_DISABLED", "message": "the project does not enable the autopilot"}
    elif same and state.get("current"):
        choice = {"action": "watch", "run_id": state["current"]["run_id"],
                  "message": f"the session drives {state['current']['kind']} {state['current']['run_id']}"}
    else:
        answered = answered_run(root, waiting)
        found = None if answered else (readiness or functools.partial(source_readiness, project, plan, config_file))()
        choice = rules.choose_next(answered, len(waiting), found, policy)
        choice.setdefault("message", {"continue": f"continue the answered run {answered}",
                                      "run": f"start a run of {', '.join(choice.get('items') or [])}",
                                      "wait_answers": "wait for answers to the waiting runs"}.get(choice["action"], ""))
    return {"$schema": "urn:swissknifeman:orch:conductor:autopilot-explain:v1", "plan": plan, "policy": policy,
            "sources": sources, "readiness": found, "next": choice, "mode": state.get("mode") if same else None}
