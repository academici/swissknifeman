"""The supervisor: ``orch conduct supervise`` and ``orch conduct reap`` (D8, I1, I13).

The lease proves that a run is owned, the heartbeat that its owner moves (``health.classify``); this module acts on the
classes, within the policy ``[orch.supervisor] recover`` (``notify`` < ``stop-only`` < ``resume``, default ``notify``):

- ``suspected_stall`` and an overdue question: say so, never signal;
- ``hung`` (a stale heartbeat while the lease is held): snapshot, then stop the conductor by its identity (``stop_conductor``:
  SIGINT, SIGTERM, SIGKILL to the one pid, never to a group);
- ``orphaned`` (nobody holds the lease): ``reap`` stops the role groups the dead conductor left and closes their agent records
  (``recovery.kill_orphaned_roles``), and with ``resume`` a detached ``conduct resume`` takes the run on from its receipts,
  within the breaker (``max_recoveries`` per ``window_s``) and never after a stop in ``NO_AUTO_RESUME``.

Everything that changes a run happens under the checkout lock and the run lease, taken without waiting: a run a live owner holds
is left alone (``busy``). One supervisor per project (``<runs root>/supervisor.lock``). Each action is a line of
``<run>/supervisor.jsonl``, an ``info`` line ``SUPERVISOR_*`` of the journal and an ``orch.conductor.health`` event.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Callable, Optional

from aicore.util import timefmt
from aicore.util.lock import FileLock

from orch import events, settings as settings_mod
from orch.conductor import agents, process, progress, questions, records, runs
from orch.conductor.application import recovery, run_service
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, heartbeat as heartbeat_mod
from orch.conductor.infrastructure.files import RUN_FILE, STATE_FILE, RunStore, runs_root
from orch.conductor.infrastructure.lease import RunLease

ORCH_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "orch.py"
LOCK_FILE = "supervisor.lock"
STATE_DOC = "supervisor-state.json"
ACTIONS_FILE = "supervisor.jsonl"
DIRECTORY = "supervisor"
# The last stop of a run in one of these needs the owner (a decision, a credential, a repair): no resume by a machine.
NO_AUTO_RESUME = frozenset({"STAGE_RECOVERY_UNKNOWN", "TOKEN_BUDGET", "STATE_CORRUPT", "OPTIONS_INVALID", "OPTIONS_UNTRUSTED",
                            "SANDBOX_UNAVAILABLE", "PROVIDER_AUTH", "PROVIDER_AUTHZ"})
INFO_CODES = {"notify": "SUPERVISOR_NOTIFIED", "identity_mismatch": "SUPERVISOR_NOTIFIED", "stop": "SUPERVISOR_STOPPED",
              "reap": "SUPERVISOR_REAPED", "resume": "SUPERVISOR_RESUMED", "given_up": "SUPERVISOR_GAVE_UP"}
NOTIFY_ACTIONS = ("notify", "stop", "given_up", "identity_mismatch")
TAIL_LINES = 50
PROCESS_LIMIT = 200
REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")
CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_CHILDREN: list = []  # the detached resumes this process started: polled so that none stays a zombie


class SupervisorBusy(Exception):
    """Another supervisor of the project holds ``supervisor.lock``."""


@dataclass(frozen=True)
class Policy:
    """The effective supervisor policy: ``recover`` and ``max_recoveries`` are already the lowest of the machine and the
    invocation values (``settings.supervisor``, then the flags of the command)."""
    recover: str = "notify"
    interval_s: int = 60
    hung_after_s: int = 300
    grace_s: int = 60
    max_recoveries: int = 2
    window_s: int = 3600
    notify_send: bool = False
    settings: object = None  # the orch settings, for the events
    config_file: Optional[Path] = None

    @classmethod
    def build(cls, settings, *, recover: Optional[str] = None, max_recoveries: Optional[int] = None,
              interval_s: Optional[int] = None, notify_send: bool = False, config_file: Optional[Path] = None) -> "Policy":
        """The policy of ``settings`` (``[orch.supervisor]``) with the flags of the invocation: a flag can only lower."""
        found = dict(getattr(settings, "supervisor", None) or {})
        base = cls()
        limit = found.get("max_recoveries", base.max_recoveries)
        return cls(recover=settings_mod.effective_recover(found.get("recover", base.recover), recover),
                   interval_s=int(interval_s or found.get("interval_s", base.interval_s)),
                   hung_after_s=int(found.get("hung_after_s", base.hung_after_s)),
                   grace_s=int(found.get("grace_s", base.grace_s)),
                   max_recoveries=int(limit if max_recoveries is None else min(limit, max_recoveries)),
                   window_s=int(found.get("window_s", base.window_s)),
                   notify_send=bool(notify_send or found.get("notify_send", base.notify_send)),
                   settings=settings, config_file=Path(config_file) if config_file else None)

    def allows(self, level: str) -> bool:
        return settings_mod.RECOVER_ORDER.index(self.recover) >= settings_mod.RECOVER_ORDER.index(level)


# ---------------------------------------------------------------------------------------------------- records


def _append(path: Path, doc: dict) -> None:
    """One line at the end of a JSON-lines file, flushed to disk; a torn last line gets its newline first."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(path, "a+b") as handle:
        if handle.seek(0, os.SEEK_END):
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                handle.write(b"\n")
        handle.write((json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())


def _notify_send(run_id: str, health: str, detail: str) -> None:
    command = shutil.which("notify-send")
    if command is None:
        return
    try:
        subprocess.run([command, f"SKM run {run_id}: {health}", detail[:300]], timeout=5, check=False,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass  # a missing desktop is not a failure


def _record(project: Path, directory: Path, policy: Policy, *, health: str, reason_code: Optional[str], action: str,
            detail: str, previous: Optional[str], at: str, silent_s: Optional[int] = None, **extra) -> dict:
    """Write one action to the three places it is told: ``supervisor.jsonl``, the journal of the run and the event."""
    run_id = directory.name
    detail = runs.display(detail, 400)
    doc = {"$schema": records.TAGS["supervisor-action"][1], "at": at, "run_id": run_id, "health": health,
           "reason_code": reason_code, "action": action, "detail": detail,
           **{key: value for key, value in extra.items() if value is not None}}
    records.check(doc, "supervisor-action", directory / ACTIONS_FILE, hint=records.WRITER_HINT)
    _append(directory / ACTIONS_FILE, doc)
    code = INFO_CODES.get(action)
    if code:  # snapshot and busy leave the journal alone: the first has a file of its own, the second changed nothing
        progress.Progress(run_id, directory, "quiet").emit("info", reason_code=code, message=f"{health}: {detail}")
    beat, _ = heartbeat_mod.read(directory)
    beat = beat or {}
    data = {"conductor_run_id": run_id, "health": health, "action": action}
    if previous:
        data["previous"] = previous
    if reason_code and CODE.match(reason_code):
        data["reason_code"] = reason_code
    if silent_s is not None:
        data["silent_s"] = max(0, int(silent_s))
    for key in ("item", "step"):
        if isinstance(beat.get(key), str) and REF.match(beat[key]):
            data[key] = beat[key]
    events.emit("orch.conductor.health", data, subject=run_id, correlationid=run_id, settings=policy.settings,
                project=project, config_file=policy.config_file)
    if policy.notify_send and action in NOTIFY_ACTIONS:
        _notify_send(run_id, health, detail)
    return doc


def load_state(root: Path) -> dict:
    """``supervisor-state.json`` of the runs root, an empty one when there is none. A damaged file is a stop, not an empty
    memory: the breaker must not forget what it did."""
    found = records.read(Path(root) / STATE_DOC, "supervisor-state")
    return found if found is not None else {"$schema": records.TAGS["supervisor-state"][1], "runs": {}}


def save_state(root: Path, doc: dict) -> None:
    kept = {run: entry for run, entry in doc["runs"].items() if entry.get("recoveries") or entry.get("given_up") or entry.get("last")}
    records.write(Path(root) / STATE_DOC, {**doc, "runs": kept}, "supervisor-state")


def _blank() -> dict:
    return {"recoveries": [], "given_up": None, "resumes_at_give_up": None, "last": None}


# ---------------------------------------------------------------------------------------------------- evidence


def _processes(directory: Path, owner_pid: Optional[int]) -> list:
    """The conductor with its descendants and every process of the role groups of ``process.json``, from ``/proc``."""
    groups = set()
    for path in directory.glob("*/agents/*/process.json"):
        try:
            doc = records.read(path, "process") or {}
        except (OSError, Stop):
            continue
        if type(doc.get("pgid")) is int:
            groups.add(doc["pgid"])
    table = {}
    ticks = os.sysconf("SC_CLK_TCK")
    try:
        names = [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return []
    for name in names:
        try:
            fields = Path(f"/proc/{name}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            args = Path(f"/proc/{name}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            table[int(name)] = {"pid": int(name), "ppid": int(fields[1]), "pgid": int(fields[2]), "stat": fields[0],
                                "cpu_s": round((int(fields[11]) + int(fields[12])) / ticks, 2), "args": args}
        except (OSError, IndexError, ValueError):
            continue
    wanted = set()
    if owner_pid in table:
        wanted.add(owner_pid)
        changed = True
        while changed:
            changed = False
            for pid, row in table.items():
                if pid not in wanted and row["ppid"] in wanted:
                    wanted.add(pid)
                    changed = True
    wanted |= {pid for pid, row in table.items() if row["pgid"] in groups and pid > 1}
    rows = [table[pid] for pid in sorted(wanted)][:PROCESS_LIMIT]
    return [{**row, "args": runs.display(row["args"], 200)} for row in rows]


def _status_document(directory: Path) -> dict:
    """What ``orch conduct status --json`` prints for the run (the same pieces, redacted)."""
    lines = progress.read_lines(directory)
    found = runs.effective_status(directory, progress.summarize(lines))
    found["run"] = directory.name
    found["state"] = state = records.read(directory / STATE_FILE, "state") or {}
    here = (found["current"] or {}).get("item") or (found["items"][-1]["item"] if found["items"] else None)
    listed = agents.read(directory / runs.safe(here)) if here else []
    details = runs.status_details(directory, found)
    details["waiting"] = run_service.waiting_pieces(state)
    return runs.display({key: value for key, value in found.items() if key != "state"}
                        | {"tokens": state.get("tokens"), "stop": state.get("stop"), "last_stop": state.get("last_stop"),
                           "agents": listed, **details})


def snapshot(run_dir: Path, health: Optional[dict] = None, now: Optional[float] = None) -> Path:
    """Write ``<run>/supervisor/snapshot-<UTC>.json`` (records/v1 ``supervisor-snapshot``) and return its path: the health,
    the status, the heartbeat and lease documents, the last lines of the journal and the processes. Read-only on the run;
    the content goes through ``runs.display`` (redaction)."""
    directory = Path(run_dir)
    clock_now = time.time() if now is None else now
    lines = progress.read_lines(directory)
    beat, _ = heartbeat_mod.read(directory)
    owner = RunLease.owner(directory)
    if health is None:
        found = runs.effective_status(directory, progress.summarize(lines))
        health = runs.health_of(directory, found, records.read(directory / STATE_FILE, "state") or {}, lines, clock_now)
    doc = runs.display({"$schema": records.TAGS["supervisor-snapshot"][1], "at": clock.utc_stamp(clock_now),
                        "run_id": directory.name, "health": health, "status": _status_document(directory),
                        "heartbeat": beat, "lease": owner or None, "progress_tail": lines[-TAIL_LINES:],
                        "processes": _processes(directory, owner.get("pid") if isinstance(owner.get("pid"), int) else None)})
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(clock_now))
    folder = directory / DIRECTORY
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path, number = folder / f"snapshot-{stamp}.json", 1
    while path.exists():
        number += 1
        path = folder / f"snapshot-{stamp}-{number}.json"
    return records.write(path, doc, "supervisor-snapshot")


# ---------------------------------------------------------------------------------------------------- stopping


def identity_problem(owner: dict) -> Optional[str]:
    """Why the process the lease names may not be signalled (``None``: it is the process that took the lease). A pid alone is
    no authority: the pid, its start time and the boot of the machine must all match ``/proc`` (I13)."""
    pid, ticks, boot = owner.get("pid"), owner.get("start_ticks"), owner.get("boot_id")
    if type(pid) is not int or pid <= 1:
        return "the lease names no usable pid"
    if pid == os.getpid():
        return "the lease names the supervisor itself"
    if type(ticks) is not int or not boot:
        return f"the lease of pid {pid} has no start_ticks or boot_id (a conductor older than the identity fields)"
    if owner.get("host") and owner["host"] != socket.gethostname():
        return f"the lease of pid {pid} is from host {owner['host']}"
    if boot != process.boot_id():
        return f"the lease of pid {pid} is from another boot of the machine"
    current = process.start_ticks(pid)
    if current is None:
        return f"pid {pid} does not exist, though the lease is held"
    if current != ticks:
        return f"pid {pid} is another process now (start_ticks {current}, the lease says {ticks})"
    return None


def _wait_free(directory: Path, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if RunLease.held(directory) is False:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def stop_conductor(run_dir: Path, policy: Policy, *, before_signal: Optional[Callable[[], None]] = None) -> dict:
    """Stop the hung conductor of ``run_dir``: SIGINT, wait up to ``grace_s`` for the lease to be freed, SIGTERM, ``grace_s``,
    SIGKILL. The signals go to the one pid the lease names (``os.kill``, never a group: a conductor started from a terminal
    shares the group of the shell; the role groups are ``reap``'s), and only while (pid, start_ticks, boot_id) still match
    ``/proc``. ``before_signal`` runs once, after the identity check and before the first signal (the snapshot).

    ``{outcome, detail, pid?, signal?}``: ``outcome`` is ``stopped``, ``free`` (nobody holds the lease), ``identity_mismatch``
    (nothing was sent) or ``failed`` (the lease is still held after SIGKILL, or the signal was refused)."""
    directory = Path(run_dir)
    held = RunLease.held(directory)
    if held is not True:
        return {"outcome": "free", "detail": "nobody holds the lease"}
    owner = RunLease.owner(directory)
    why = identity_problem(owner)
    pid = owner.get("pid") if type(owner.get("pid")) is int else None
    if why:
        return {"outcome": "identity_mismatch", "detail": f"no signal sent: {why}", **({"pid": pid} if pid else {})}
    if before_signal is not None:
        before_signal()
    last = None
    for number, name in ((signal.SIGINT, "SIGINT"), (signal.SIGTERM, "SIGTERM"), (signal.SIGKILL, "SIGKILL")):
        if RunLease.held(directory) is False:
            break
        why = identity_problem(owner)
        if why:
            if RunLease.held(directory) is False:
                break
            return {"outcome": "identity_mismatch", "detail": f"no further signal sent: {why}", "pid": pid,
                    **({"signal": last} if last else {})}
        try:
            os.kill(pid, number)  # the pid only: killpg would take the shell of a terminal with it
        except ProcessLookupError:
            pass
        except PermissionError as error:
            return {"outcome": "failed", "detail": f"{name} to pid {pid} was refused: {error}", "pid": pid,
                    **({"signal": last} if last else {})}
        last = name
        if _wait_free(directory, policy.grace_s):
            break
    else:
        return {"outcome": "failed", "detail": f"the lease is still held {policy.grace_s} s after SIGKILL to pid {pid}",
                "pid": pid, "signal": last}
    return {"outcome": "stopped", "pid": pid, "signal": last,
            "detail": f"conductor pid {pid} freed the lease after {last}" if last else f"conductor pid {pid} freed the lease"}


# ---------------------------------------------------------------------------------------------------- recovery


def reap(project: Path, run_id: str, *, settings=None, config_file: Optional[Path] = None) -> dict:
    """Stop the role groups an orphaned run left behind and close their agent records as orphaned: exactly
    ``recovery.kill_orphaned_roles``, run under the checkout lock and the run lease like a resume (a lease a live conductor
    holds is ``RUN_BUSY``, a checkout another run drives ``WORKTREE_BUSY``: nothing is touched). The journal, the state and the
    steps stay as they are; the heartbeat is not written. ``{killed, closed}``, plus ``skipped`` when the journal does not say
    the run was running (then there is nothing a dead conductor could have left)."""
    store = RunStore(Path(project), run_id)
    with store.ownership("reap", checkout=True):
        run_doc, state = store.load()
        lines = progress.read_lines(store.directory)
        if run_doc.get("lease") is not True or progress.summarize(lines)["status"] != "running":
            return {"killed": 0, "closed": 0, "skipped": "the journal does not say the run was running"}
        context = SimpleNamespace(directory=store.directory, state=state, run_id=run_id, project=Path(project),
                                  settings=settings, config_file=config_file,
                                  progress=progress.Progress(run_id, store.directory, "quiet"))
        return recovery.kill_orphaned_roles(context)


def resume_detached(project: Path, run_id: str, *, config_file: Optional[Path] = None) -> dict:
    """Start ``orch conduct resume --run RUN`` as a process of its own (its own session, no terminal, its output in
    ``<run>/supervisor/resume-<n>.log``, ``SKM_ORCH_LAUNCHER=supervisor``). The resume takes the locks itself and continues from
    the receipts of the steps (I4). ``{pid, log}``."""
    folder = runs_root(Path(project)) / run_id / DIRECTORY
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    number = len(list(folder.glob("resume-*.log"))) + 1
    log = folder / f"resume-{number}.log"
    argv = [sys.executable, str(ORCH_SCRIPT), *(["--config", str(config_file)] if config_file else []), "--project", str(project),
            "conduct", "resume", "--run", run_id, "--quiet"]
    with open(log, "ab") as out:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True,
                                 env={**os.environ, "SKM_ORCH_LAUNCHER": "supervisor"}, close_fds=True)
    _CHILDREN.append(child)
    return {"pid": child.pid, "log": str(log)}


def _poll_children() -> None:
    _CHILDREN[:] = [child for child in _CHILDREN if child.poll() is None]


# ---------------------------------------------------------------------------------------------------- one pass


def _lock(root: Path) -> FileLock:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = FileLock(root / LOCK_FILE)
    if not lock.acquire():
        raise SupervisorBusy(str(root / LOCK_FILE))
    return lock


def last_stop_code(state: dict, summary: dict) -> Optional[str]:
    """The code of the last stop of a run: the stop in its state, else the one a resume put into ``last_stop``, else the
    reason of the journal."""
    return (state.get("stop") or {}).get("code") or (state.get("last_stop") or {}).get("code") or summary.get("reason_code")


class _Pass:
    """One look at every run of a project, with the memory of the supervisor loaded and saved around it."""

    def __init__(self, project: Path, policy: Policy, now: float, spawn: Callable):
        self.project, self.policy, self.now, self.spawn = Path(project), policy, now, spawn
        self.root = runs_root(self.project)
        self.memory = load_state(self.root)
        self.dirty = False
        self.actions: list = []

    @property
    def at(self) -> str:
        return clock.utc_stamp(self.now)

    def entry(self, run_id: str) -> dict:
        return self.memory["runs"].setdefault(run_id, _blank())

    def health(self, directory: Path, lines: Optional[list] = None) -> dict:
        lines = progress.read_lines(directory) if lines is None else lines
        found = runs.effective_status(directory, progress.summarize(lines))
        state = records.read(directory / STATE_FILE, "state") or {}
        return dict(runs.health_of(directory, found, state, lines, self.now, self.policy.hung_after_s),
                    _summary=found, _state=state)

    def act(self, directory: Path, health: dict, action: str, detail: str, *, resumes: int, dedupe: bool = False, **extra):
        """Record an action unless ``dedupe`` and the supervisor already said this about the run in this episode (same class,
        same action, no resume since). Returns the action document, or ``None`` when it was left out."""
        entry = self.entry(directory.name)
        last = entry.get("last") or {}
        if dedupe and (last.get("health"), last.get("action"), last.get("resumes")) == (health["health"], action, resumes):
            return None
        doc = _record(self.project, directory, self.policy, health=health["health"], reason_code=health.get("reason_code"),
                      action=action, detail=detail, previous=last.get("health"), at=self.at,
                      silent_s=health.get("silent_s"), **extra)
        if action not in ("snapshot", "stop"):  # these two lead to another action of the same episode
            entry["last"] = {"health": health["health"], "action": action, "at": self.at, "resumes": resumes}
        self.dirty = True
        self.actions.append(doc)
        return doc

    def run(self, directory: Path) -> None:
        run_id = directory.name
        lines = progress.read_lines(directory)
        health = self.health(directory, lines)
        resumes = sum(1 for line in lines if line.get("event") == "run.resume")
        entry = self.memory["runs"].get(run_id)
        if entry and entry.get("given_up") and resumes > (entry.get("resumes_at_give_up") or 0):
            # a run.resume the supervisor did not start (it starts none for a run it gave up): the owner took the run back
            entry.update(given_up=None, resumes_at_give_up=None, recoveries=[])
            self.dirty = True
        if entry and entry.get("given_up"):
            return
        name = health["health"]
        if name == "suspected_stall":
            self.act(directory, health, "notify", health["detail"], resumes=resumes, dedupe=True)
        elif name == "waiting_owner":
            overdue = [row for row in questions.listing(directory, self.now, invalid=[]) if row["overdue"]]
            if overdue:
                self.act(directory, health, "notify", f"{len(overdue)} question(s) wait for an answer past limits.question_warn_s: "
                         + ", ".join(f"{row['item']}:{row['id']}" for row in overdue[:5]), resumes=resumes, dedupe=True)
        elif name == "hung":
            self.hung(directory, health, resumes)
        elif name == "orphaned":
            self.orphaned(directory, health, resumes)
        elif entry and (entry.get("last") or {}).get("health") != name:
            entry["last"] = {"health": name, "action": None, "at": self.at, "resumes": resumes}  # the trouble is over
            self.dirty = True

    def hung(self, directory: Path, health: dict, resumes: int) -> None:
        if not self.policy.allows("stop-only"):
            self.act(directory, health, "notify", f"{health['detail']}; recover is notify, so the conductor is not stopped",
                     resumes=resumes, dedupe=True)
            return

        def evidence() -> None:
            path = snapshot(directory, {key: value for key, value in health.items() if not key.startswith("_")}, self.now)
            self.act(directory, health, "snapshot", f"snapshot {path.relative_to(directory)}", resumes=resumes)

        result = stop_conductor(directory, self.policy, before_signal=evidence)
        if result["outcome"] == "identity_mismatch":
            self.act(directory, health, "identity_mismatch", result["detail"], resumes=resumes, dedupe=True,
                     pid=result.get("pid"))
        elif result["outcome"] in ("stopped", "free"):  # free: the conductor died while the pass was on its way
            if result["outcome"] == "stopped":
                self.act(directory, health, "stop", result["detail"], resumes=resumes, pid=result.get("pid"),
                         signal=result.get("signal"))
            after = self.health(directory)
            if after["health"] == "orphaned":  # the same pass goes on: reap, and resume when the policy says so
                self.orphaned(directory, after, resumes)
        elif result["outcome"] == "failed":
            self.act(directory, health, "notify", result["detail"], resumes=resumes, dedupe=True, pid=result.get("pid"))

    def orphaned(self, directory: Path, health: dict, resumes: int) -> None:
        run_id = directory.name
        if not self.policy.allows("stop-only"):
            self.act(directory, health, "notify", "the conductor is gone and recover is notify: "
                     f"orch conduct reap --run {run_id}, then orch conduct resume --run {run_id}", resumes=resumes, dedupe=True)
            return
        try:
            done = reap(self.project, run_id, settings=self.policy.settings, config_file=self.policy.config_file)
        except Stop as stop:
            if stop.code in ("RUN_BUSY", "WORKTREE_BUSY"):
                self.act(directory, health, "busy", f"{stop.code}: {stop.message}", resumes=resumes, dedupe=True)
            else:
                self.act(directory, health, "notify", f"reap stopped with {stop.code}: {stop.message}", resumes=resumes, dedupe=True)
            return
        self.act(directory, health, "reap", f"stopped {done['killed']} orphaned role group(s), closed {done['closed']} agent record(s)"
                 + (f" ({done['skipped']})" if done.get("skipped") else ""), resumes=resumes,
                 dedupe=not (done["killed"] or done["closed"]))
        if not self.policy.allows("resume"):
            return
        code = last_stop_code(health["_state"], health["_summary"])
        if code in NO_AUTO_RESUME:
            self.act(directory, health, "notify", f"not resumed: the last stop was {code}, which needs the owner",
                     resumes=resumes, dedupe=True)
            return
        entry = self.entry(run_id)
        recent = [stamp for stamp in entry["recoveries"] if self.now - (timefmt.epoch(stamp) or 0) <= self.policy.window_s]
        if recent != entry["recoveries"]:
            entry["recoveries"] = recent
            self.dirty = True
        if len(recent) >= self.policy.max_recoveries:
            entry["given_up"], entry["resumes_at_give_up"] = self.at, resumes
            self.act(directory, health, "given_up", f"{len(recent)} recovery(ies) within {self.policy.window_s} s (max "
                     f"{self.policy.max_recoveries}); resume by hand: orch conduct resume --run {run_id}", resumes=resumes)
            return
        started = self.spawn(self.project, run_id, config_file=self.policy.config_file)
        entry["recoveries"].append(self.at)
        self.act(directory, health, "resume", f"started a detached resume (pid {started['pid']}, log {Path(started['log']).name})",
                 resumes=resumes, pid=started["pid"])

    def finish(self) -> list:
        if self.dirty:
            save_state(self.root, self.memory)
        return self.actions


def _pass(project: Path, policy: Policy, only: Optional[str], now: float, spawn: Callable) -> list:
    _poll_children()
    current = _Pass(project, policy, now, spawn)
    try:
        directories = sorted(path for path in current.root.glob("cnd-*") if (path / RUN_FILE).is_file())
    except OSError:
        directories = []
    for directory in directories:
        if only and directory.name != only:
            continue
        try:
            current.run(directory)
        except (Stop, OSError) as error:  # one run that cannot be read is said, and the others still get their look
            code = getattr(error, "code", "RUN_UNREADABLE")
            current.act(directory, {"health": "unknown", "reason_code": code if CODE.match(str(code)) else None},
                        "notify", f"{code}: {getattr(error, 'message', error)}", resumes=0, dedupe=True)
    return current.finish()


def supervise_once(project: Path, policy: Policy, *, run: Optional[str] = None, now: Optional[float] = None,
                   spawn: Optional[Callable] = None, lock: Optional[FileLock] = None) -> list:
    """One pass over the runs of ``project`` (``run``: only that one): the list of the actions taken, each a records/v1
    ``supervisor-action``. ``SupervisorBusy`` when another supervisor holds the project (``lock``: the caller holds it)."""
    own = lock is None
    held = _lock(runs_root(Path(project))) if own else lock
    try:
        return _pass(project, policy, run, time.time() if now is None else now, spawn or resume_detached)
    finally:
        if own:
            held.release()


def supervise(project: Path, policy: Policy, *, run: Optional[str] = None, stop: Callable[[], bool],
              wait: Callable[[float], None], report: Callable[[list], None]) -> None:
    """The loop of ``supervise`` without ``--once``: one pass every ``interval_s`` until ``stop()`` is true; the project's
    ``supervisor.lock`` is held for the whole loop. ``SupervisorBusy`` when another supervisor holds it."""
    lock = _lock(runs_root(Path(project)))
    try:
        while not stop():
            report(supervise_once(project, policy, run=run, lock=lock))
            wait(policy.interval_s)
    finally:
        lock.release()


def reap_recorded(project: Path, run_id: str, policy: Policy) -> dict:
    """``orch conduct reap --run R``: ``reap`` and, when it did something or the run was orphaned, the line in
    ``supervisor.jsonl``, the journal and the event. Raises ``Stop`` (``RUN_BUSY``, ``RUN_UNKNOWN``) as ``reap`` does."""
    directory = runs_root(Path(project)) / run_id
    if not (directory / RUN_FILE).is_file():
        raise Stop("RUN_UNKNOWN", f"no conductor run {run_id} in {directory.parent}")
    lines = progress.read_lines(directory)
    health = runs.health_of(directory, runs.effective_status(directory, progress.summarize(lines)),
                            records.read(directory / STATE_FILE, "state") or {}, lines, time.time(), policy.hung_after_s)
    done = reap(project, run_id, settings=policy.settings, config_file=policy.config_file)
    _record(Path(project), directory, policy, health=health["health"], reason_code=health.get("reason_code"), action="reap",
            detail=f"stopped {done['killed']} orphaned role group(s), closed {done['closed']} agent record(s)"
                   + (f" ({done['skipped']})" if done.get("skipped") else ""),
            previous=None, at=clock.utc_now(), silent_s=health.get("silent_s"))
    return done


def text(action: dict) -> str:
    """One line for a terminal."""
    return f"{action['run_id']}: {action['action']} ({action['health']}) — {action['detail']}"
