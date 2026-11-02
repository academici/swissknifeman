"""The autopilot controller: ``orch conduct autopilot start`` (D9, I1, I13, I14, I15).

A deterministic queue controller, never a model: it asks the work source which lane comes next (op ``readiness``), checks that
exactly the phase of that lane is ready, starts ``conduct run --plan P --items <lane>`` as a detached child, waits for it, and
classifies how it ended (``policies/autopilot.classify_outcome``): go on, continue a run whose questions were answered, resume a
run after a crash, a hang, a one-time failure or a quota reset, or stop with an ``AUTOPILOT_*`` code. The policy is
``[orch.autopilot]`` (``allowed`` only by the machine). One controller per checkout holds ``<runs root>/autopilot.lock``;
its state is ``autopilot.json`` (records/v1 ``autopilot-state``), written atomically after every change, the launch intent of a
child before the child exists. Requests (``pause``, ``resume``, ``drain``, ``stop``) arrive in ``autopilot.request.json``.

Recovery uses only the supervisor library (``stop_conductor``, ``reap``) and an ordinary ``conduct resume``; a child starts
only through ``detach.spawn`` and takes the checkout lock and the run lease itself, so a second conductor on the checkout is
refused (``RUN_BUSY``/``WORKTREE_BUSY`` -> ``AUTOPILOT_CHECKOUT_LOST``). Before them the child passes the startup fence
(``autopilot_fence``): a launch intent the controller cancelled never starts (``AUTOPILOT_LAUNCH_CANCELLED``).
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time
from typing import Callable, Optional

from aicore.util import timefmt
from aicore.util.lock import FileLock

from orch import events
from orch.conductor import options as opts, process, progress, records, runs
from orch.conductor.application import autopilot_status as files, run_service, supervisor
from orch.conductor.application.autopilot_fence import LaunchFence, retry_targets
from orch.conductor.application.autopilot_launcher import ProcessLauncher
from orch.conductor.application.autopilot_status import (DETACHED, IDENTITY, LOCK_FILE, OPTIONS_DOC, REQUEST_DOC, STATE_DOC,
                                                         answered_run, blocked_pieces, child_problem, escalations, source_readiness,
                                                         plan_folders, still_waiting, tracked_changes)
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock as clock_mod, detach
from orch.conductor.infrastructure.files import RUN_FILE, STATE_FILE, runs_root, write_json
from orch.conductor.infrastructure.lease import RunLease
from orch.conductor.policies import autopilot as rules

LAUNCH_GRACE_S = 30  # a launch without an acknowledgement, a lease or a run folder after this long never started
SETTLED = ("ended", "orphaned", "gone", "relaunch")  # no conductor of the current run is alive
HISTORY_MAX = 50
CRASH_ENV = "SKM_AUTOPILOT_CRASH_AT"  # fault injection of the tests: after_spawn
LIMIT_KEYS = ("max_runs", "max_wall_s", "run_tokens_hard_max", "max_no_progress_runs", "max_auto_decisions",
              "quota_wait_max_s", "max_recoveries", "poll_s")
COUNTERS = ("runs", "items_closed", "no_progress_streak", "auto_decisions", "recoveries", "quota_waits")
EXITS = {"finished": 0, "waiting": 4}


class Clock:
    """Wall time and the pause between two looks; the tests replace both."""

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class Controller(LaunchFence):
    """One session of the autopilot of ``plan`` in ``project``. ``launcher``, ``readiness``, ``dirty``, ``recover`` and
    ``clock`` are the seams the tests replace (no child conductor, controlled time)."""

    def __init__(self, project: Path, plan: str, settings, *, flags: Optional[dict] = None, config_file: Optional[Path] = None,
                 clock=None, launcher=None, readiness: Optional[Callable] = None, dirty: Optional[Callable] = None,
                 recover: Optional[Callable] = None, say: Optional[Callable] = None, label: Optional[str] = None,
                 note: str = "", phase: Optional[str] = None, wait_blocked: bool = False):
        self.project, self.plan, self.settings = Path(project), plan, settings
        self.config_file = Path(config_file).resolve() if config_file else None  # children run in the project folder
        config_file = self.config_file
        self.root = runs_root(self.project)
        self.policy, self.sources = rules.effective_policy(getattr(settings, "autopilot", None) or {}, flags or {})
        self.clock = clock or Clock()
        self.launcher = launcher or ProcessLauncher(self.project, plan, config_file)
        self.readiness = readiness or functools.partial(source_readiness, self.project, plan, config_file)
        self.dirty = dirty or functools.partial(tracked_changes, self.project)  # called with the known plan folders
        self.recover_run = recover or self._recover_run
        self.say = say or (lambda text: print(f"[autopilot] {text}", file=sys.stderr, flush=True))
        self.label, self.note = label, note
        self.phase = phase
        self.wait_blocked = wait_blocked
        self._phase_ready = None
        self._phase_wait_resolved = False
        self.doc: dict = {}  # autopilot.json of the session, once ``start`` holds the lock
        self.grace_s = supervisor.Policy.build(settings).grace_s  # how long a child gets to end after SIGINT

    # ------------------------------------------------------------------------------------------------ session

    def start(self) -> int:
        """Run the session to its stop; the exit code of the stop (0 or 1)."""
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = FileLock(self.root / LOCK_FILE)
        if not lock.acquire():
            return self._refuse("AUTOPILOT_BUSY", f"another autopilot controller holds {self.root / LOCK_FILE}; "
                                "orch conduct autopilot status")
        try:
            try:
                prior = records.read(self.root / STATE_DOC, "autopilot-state")
            except Stop as error:  # the file is evidence: it is not overwritten
                return self._refuse("AUTOPILOT_STATE_INVALID", f"{error.code}: {error.message}; move "
                                    f"{self.root / STATE_DOC} aside, then start again")
            if prior and prior.get("plan") == self.plan:
                saved = prior.get("phase")
                prior["waiting_runs"] = [row for row in prior.get("waiting_runs") or [] if still_waiting(self.root, row)]
                pending = prior.get("stop") is None or prior.get("current") or prior.get("waiting_runs") or prior.get("quota_wait") or prior.get("phase_wait")
                if pending and self.phase and self.phase != saved:
                    return self._refuse("AUTOPILOT_PHASE_CONFLICT", "the existing session has unfinished work under a different phase boundary")
                if saved and (pending or not self.phase):
                    self.phase = saved
                if pending and prior.get("wait_blocked"):
                    self.wait_blocked = True
            self.doc = self._session(prior)
            self._save()
            if self.label:
                detach.acknowledge(self.label)
            try:
                return self._loop()
            except Stop as error:  # a record of a run the session drives cannot be read: say so, keep it and current
                return self._finish("AUTOPILOT_STATE_INVALID", f"{error.code}: {error.message}; the records are kept as they "
                                    "are: repair or release the run, then start again")
        except KeyboardInterrupt:
            return self._finish("AUTOPILOT_INTERRUPTED", "the controller was interrupted; the current run goes on: orch conduct "
                                "autopilot start adopts it")
        finally:
            lock.release()

    def _session(self, prior: Optional[dict]) -> dict:
        now = self.clock.now()
        stamp = clock_mod.utc_stamp(now)
        me = {"pid": os.getpid(), "start_ticks": process.start_ticks(os.getpid()), "boot_id": process.boot_id()}
        limits = {key: self.policy[key] for key in LIMIT_KEYS}
        prior = prior or {}
        same = prior.get("plan") == self.plan
        if same and prior.get("stop") is None:  # a restart after a crash: the session, its counters and deadline go on
            return {"recoveries": {}, "quota_wait": None, **prior, **me, "project": str(self.project), "updated_at": stamp,
                    "limits": limits, **({"wait_blocked": True} if self.wait_blocked else {})}
        return {"$schema": records.TAGS["autopilot-state"][1], "plan": self.plan, "project": str(self.project), **me,
                **({"phase": self.phase} if self.phase else {}),
                **({"wait_blocked": True} if self.wait_blocked else {}),
                **({"phase_wait": prior["phase_wait"]} if same and prior.get("phase_wait") else {}),
                "started_at": stamp, "updated_at": stamp, "deadline_at": clock_mod.utc_stamp(now + self.policy["max_wall_s"]),
                "mode": "running", "limits": limits, "counters": dict.fromkeys(COUNTERS, 0), "recoveries": {},
                "current": prior.get("current") if same else None,
                "quota_wait": prior.get("quota_wait") if same and self.phase else None,
                "waiting_runs": list(prior.get("waiting_runs") or []) if same else [],
                "history": list(prior.get("history") or [])[-HISTORY_MAX:] if same else [], "last_blockers": [], "stop": None}

    def _save(self) -> None:
        self.doc["updated_at"] = clock_mod.utc_stamp(self.clock.now())
        records.write(self.root / STATE_DOC, self.doc, "autopilot-state")

    def _event(self, code: str, message: str) -> None:
        counters = self.doc.get("counters") or {}
        events.emit("orch.autopilot.stopped", {"plan": self.plan, "code": code, "runs": counters.get("runs", 0),
                                               "items_closed": counters.get("items_closed", 0), "message": message[:500]},
                    subject=self.plan, correlationid=self.plan, settings=self.settings, project=self.project,
                    config_file=self.config_file)

    def _refuse(self, code: str, message: str) -> int:
        """A stop that must not touch ``autopilot.json`` (another controller owns it, or it cannot be read)."""
        detach.refuse(code, message)
        self._event(code, message)
        print(f"{code}: {message}", file=sys.stderr, flush=True)
        return rules.exit_code(code)

    def _finish(self, code: str, message: str) -> int:
        message = runs.display(message, 500)
        self.doc.update(mode="stopped", stop={"code": code, "message": message, "at": clock_mod.utc_stamp(self.clock.now())})
        self._save()
        self._event(code, message)
        print(f"{code}: {message}", file=sys.stderr, flush=True)
        return rules.exit_code(code)

    def _wait(self) -> None:
        self.clock.sleep(self.policy["poll_s"])

    @staticmethod
    def _snapshot(readiness: dict) -> str:
        return hashlib.sha256(json.dumps(readiness, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def _phase_hold(self, code: str, message: str, run_id: Optional[str] = None, readiness: Optional[dict] = None,
                    items: Optional[list] = None) -> Optional[int]:
        if not self.wait_blocked:
            return self._finish(code, message)
        readiness = readiness if readiness is not None else self.readiness()
        hold = self.doc.get("phase_wait")
        if hold:
            if items and run_id:
                rows = hold.setdefault("blockers", [])
                row = next((row for row in rows if row["run_id"] == run_id), None)
                if row:
                    row["items"] = list(dict.fromkeys(row["items"] + items))
                else:
                    rows.append({"run_id": run_id, "items": items})
        else:
            self.doc["phase_wait"] = {"code": code, "message": message, "snapshot": self._snapshot(readiness),
                                      **({"run_id": run_id} if run_id else {}), **({"items": items} if items else {})}
        if readiness.get("outcome") != "ok":
            return self._finish("AUTOPILOT_NOT_READY", f"{readiness.get('reason_code') or 'READINESS_UNKNOWN'}: {readiness.get('message') or 'the work source tells no readiness'}")
        self._save()
        self._wait()
        return None

    def _poll_phase_wait(self) -> Optional[int]:
        hold = self.doc["phase_wait"]
        readiness = self.readiness()
        if readiness.get("outcome") != "ok":
            return self._finish("AUTOPILOT_NOT_READY", f"{readiness.get('reason_code') or 'READINESS_UNKNOWN'}: {readiness.get('message') or 'the work source tells no readiness'}")
        kept = [row for row in self.doc["waiting_runs"] if still_waiting(self.root, row)]
        if kept != self.doc["waiting_runs"]:
            self.doc["waiting_runs"] = kept
            self._save()
        answered = answered_run(self.root, kept)
        check = rules.check_phase_readiness(readiness, self.phase)
        resolved = self._snapshot(readiness) != hold["snapshot"]
        remaining, completed, known, tracked = set(), set(), False, set()
        rows = ([hold] if hold.get("items") else []) + [row for row in hold.get("blockers", []) if row.get("items")]
        if rows:
            known = True
            for row in rows:
                run_id = row.get("run_id")
                tracked.update(row["items"])
                if not run_id or RunLease.held(self.root / run_id) is not False:
                    known = False
                    continue
                view, _ = self.view(run_id)
                blocked = {row["item"] for row in view.get("blocked") or []}
                known = known and (view.get("status") in ("finished", "stopped", "waiting")
                                   and set(row["items"]).issubset(view.get("items") or []))
                remaining.update(blocked.intersection(row["items"]))
                completed.update(view.get("closed") or [])
            resolved = known and not remaining
        elif hold.get("code") == "AUTOPILOT_PHASE_WAITING" and hold.get("run_id") and not still_waiting(self.root, hold):
            view, _ = self.view(hold["run_id"])
            remaining = {row["item"] for row in view.get("blocked") or []}
            completed = set(view.get("closed") or [])
            known, resolved = True, not remaining
        if answered:
            view, _ = self.view(answered)
            if not view.get("blocked") and not check:
                if rows:
                    self._phase_ready = readiness
                else:
                    self.doc["phase_wait"] = None
                    self._save()
                return None
        elif (resolved or known) and not self.doc["waiting_runs"]:
            choice = rules.choose_phase_next(readiness, self.phase, self.policy)
            lane = set(choice.get("items") or [])
            if (choice["action"] == "run" and not check and not lane.intersection(remaining | completed)
                    and (resolved or lane.intersection(tracked - remaining - completed))):
                self._phase_ready = readiness
                self._phase_wait_resolved = resolved
                return None
            if resolved and choice.get("code") in ("AUTOPILOT_PHASE_BOUNDARY", "AUTOPILOT_PHASE_COMPLETE"):
                self.doc["phase_wait"] = None
                return self._finish(choice["code"], choice["message"])
        self._wait()
        return None

    # ------------------------------------------------------------------------------------------------ the loop

    def _loop(self) -> int:
        if not self.policy["allowed"]:
            return self._finish("AUTOPILOT_NOT_ALLOWED", "this machine does not allow the autopilot ([orch.autopilot] allowed "
                                f"in the machine configuration){'; ' + self.note if self.note else ''}")
        if not self.policy["enabled"]:
            return self._finish("AUTOPILOT_DISABLED", "the autopilot is not enabled for this project: [orch.autopilot] "
                                "enabled = true in the project configuration")
        if self.doc["current"]:
            self.say(f"adopting run {self.doc['current']['run_id']} ({self.doc['current']['state']})")
        while True:
            found = self._step()
            if found is not None:
                return found

    def _step(self) -> Optional[int]:
        if self._take_request() == "stop":
            return self._halt("AUTOPILOT_STOPPED", "stopped by request")
        if self.clock.now() >= files.epoch(self.doc["deadline_at"]):
            return self._halt("AUTOPILOT_MAX_WALL", f"the deadline {self.doc['deadline_at']} (max_wall_s "
                              f"{self.doc['limits']['max_wall_s']}) has passed")
        if self.doc["current"]:
            return self._watch(self.doc["current"])
        waiting = self.doc.get("quota_wait")
        if self.doc["mode"] == "draining":  # before any next child, the resume after a quota included
            return self._finish("AUTOPILOT_DRAINED", "drained: no run is current and no new one was started"
                                + (f"; run {waiting['run_id']} waits for the quota reset: orch conduct resume --run "
                                   f"{waiting['run_id']} after {waiting['until']}" if waiting else ""))
        if self.doc["mode"] == "paused":  # a quota wait stays and resumes only after a resume request
            self._phase_ready = None
            self._wait()
            return None
        if waiting:
            if self.clock.now() < files.epoch(waiting["until"]):
                self._wait()
                return None
            self.doc["counters"]["quota_waits"] += 1
            return self._launch("resume", waiting["run_id"])
        if self.doc["counters"]["runs"] >= self.policy["max_runs"]:
            return self._finish("AUTOPILOT_MAX_RUNS", f"{self.doc['counters']['runs']} run(s) started (max_runs "
                                f"{self.policy['max_runs']})")
        if self.doc.get("phase_wait") and self._phase_ready is None:
            return self._poll_phase_wait()
        kept = [row for row in self.doc["waiting_runs"] if still_waiting(self.root, row)]
        if kept != self.doc["waiting_runs"]:  # continued and ended by hand: it waits for nothing any more
            self.doc["waiting_runs"] = kept
            self._save()
        answered = answered_run(self.root, self.doc["waiting_runs"])
        readiness = None if answered else (self._phase_ready or self.readiness())
        self._phase_ready = None
        if self.phase and not answered:
            choice = rules.choose_phase_next(readiness, self.phase, self.policy, len(self.doc["waiting_runs"]))
        else:
            choice = rules.choose_next(answered, len(self.doc["waiting_runs"]), readiness, self.policy)
        if choice["action"] == "continue":
            self.doc["counters"]["runs"] += 1
            return self._launch("continue", choice["run_id"], retry=retry_targets(self.root, choice["run_id"]))
        if choice["action"] == "run":
            self._write_options()
            self.doc["counters"]["runs"] += 1
            if self._phase_wait_resolved:
                self.doc.pop("phase_wait", None)
            elif self.doc.get("phase_wait"):
                hold = self.doc["phase_wait"]
                for row in [hold] + hold.get("blockers", []):
                    if row.get("items"):
                        row["items"] = [item for item in row["items"] if item not in choice["items"]]
            self._phase_wait_resolved = False
            return self._launch("run", clock_mod.new_run_id(), items=choice["items"])
        if choice["action"] == "wait_answers":
            self._wait()
            return None
        if self.phase and choice.get("code") == "AUTOPILOT_PHASE_WAITING":
            return self._phase_hold(choice["code"], choice["message"], readiness=readiness)
        return self._finish(choice["code"], choice["message"])

    def _take_request(self) -> Optional[str]:
        """Read and remove ``autopilot.request.json`` (taken by a rename, so a request written meanwhile is not lost)."""
        path = self.root / REQUEST_DOC
        taken = path.with_name(f"{REQUEST_DOC}.{os.getpid()}.taken")
        try:
            os.replace(path, taken)
        except FileNotFoundError:
            return None
        try:
            request = records.read(taken, "autopilot-request")
        except Stop as error:
            self.say(f"request ignored: {error.code}: {error.message}")
            return None
        finally:
            taken.unlink(missing_ok=True)
        if request is None:  # replaced between the rename and the read: nothing to do
            return None
        action = request["action"]
        if action in ("pause", "resume"):
            self._phase_ready = None
        if action != "stop":
            self.doc["mode"] = {"pause": "paused", "resume": "running", "drain": "draining"}[action]
            self._save()
        self.say(f"request {action} by {request['by']}")
        return action

    def _write_options(self) -> None:
        """``autopilot-options.json`` for every new run: paths outside the write set block the piece (D14) and the run cap of
        ``--run-tokens-hard-max`` from the trusted invocation layer."""
        doc: dict = {"scope": {"outside": "block"}}
        if self.policy["run_tokens_hard_max"]:
            doc["limits"] = {"run_tokens_hard_max": self.policy["run_tokens_hard_max"]}
        found = opts.layer_problems(doc)
        if found:
            raise Stop("RECORD_INVALID", f"autopilot-options: {'; '.join(found[:3])}; {records.WRITER_HINT}")
        write_json(self.root / OPTIONS_DOC, doc)

    # ------------------------------------------------------------------------------------------------ children

    def _history(self, run_id: str, **fields) -> dict:
        rows = self.doc["history"]
        entry = next((row for row in rows if row["run_id"] == run_id), None)
        if entry is None:
            entry = {"run_id": run_id, "started_at": clock_mod.utc_stamp(self.clock.now()), "ended_at": None, "exit": None,
                     "status": "running", "reason_code": None, "items_closed": []}
            rows.append(entry)
            del rows[:-HISTORY_MAX]
        entry.update(fields)
        return entry

    def _launch(self, kind: str, run_id: str, *, items: Optional[list] = None, retry: Optional[list] = None) -> Optional[int]:
        """Write the launch intent, start the child and wait for its acknowledgement (never for the run)."""
        current: dict = {"run_id": run_id, "launch_id": secrets.token_hex(8), "state": "launching", "kind": kind,
                         "since": clock_mod.utc_stamp(self.clock.now()), "boot_id": process.boot_id()}
        current.update({key: list(value) for key, value in (("items", items), ("retry", retry)) if value})
        stopped = self._write_intent(current)  # under the launch lock (autopilot_fence)
        return stopped if stopped is not None else self._start(current)

    def _start(self, current: dict) -> Optional[int]:
        """Start the child of the saved intent ``current`` and wait for its acknowledgement (never for the run)."""
        kind, run_id = current["kind"], current["run_id"]
        if self.phase and kind in ("continue", "resume"):
            view, _ = self.view(run_id)
            if view.get("blocked"):
                blocker = view["blocked"][0]
                if self.wait_blocked:
                    self.doc["current"] = None
                return self._phase_hold("AUTOPILOT_PHASE_BLOCKED", f"phase {self.phase}: {blocker['item']} blocked ({blocker['code']})", run_id,
                                        items=[row["item"] for row in view["blocked"]])
            check = rules.check_phase_readiness(self.readiness(), self.phase)
            if check:
                return self._finish(check["code"], check["message"])
        if kind == "continue":
            self.doc["waiting_runs"] = [row for row in self.doc["waiting_runs"] if row["run_id"] != run_id]
        if kind == "resume" and (self.doc.get("quota_wait") or {}).get("run_id") == run_id:
            self.doc["quota_wait"] = None
        self._save()
        try:
            child = self.launcher.start(current)
        except (OSError, Stop) as error:
            return self._refused(current, Stop(getattr(error, "code", "DETACH_FAILED"), getattr(error, "message", str(error))))
        if os.environ.get(CRASH_ENV) in ("after_spawn", f"after_spawn:{kind}"):
            os._exit(9)
        try:
            self.launcher.acknowledged(current, child)
        except Stop as refusal:
            if refusal.code != "DETACH_FAILED":  # a refused acknowledgement: the child took nothing
                return self._refused(current, refusal)
            current.update(pid=child["pid"], start_ticks=child["start_ticks"], log=child["log"])
            # no acknowledgement in time, or the child exited: decided under the launch lock (an ack written meanwhile adopts)
            look = self._intent(current, self.root / run_id, self.launcher.alive(child))
            if look in ("lost", "invalid"):
                return self._intent_end(current, look)
            if look in ("gone", "relaunch"):  # classified; the next attempt of an existing run stays current
                return self._refused(current, refusal)
            if look == "launching":
                self._save()  # still launching: the next look adopts the run or gives the launch up
                self.say(f"{kind} {run_id}: {refusal.message}")
            return None
        current.update(state="running", pid=child["pid"], start_ticks=child["start_ticks"], log=child["log"])
        self._save()
        self.say(f"{kind} {run_id} started (pid {child['pid']})" + (f": {', '.join(current['items'])}" if current.get("items") else ""))
        return None

    def _refused(self, current: dict, refusal: Stop) -> Optional[int]:
        """The child refused to start (or could not be started): classified like a run that stopped with that code."""
        run_id = current["run_id"]
        if self.doc["current"] is current:  # the next attempt of an existing run that the fence saved instead stays
            self.doc["current"] = None
        if current["kind"] == "run":
            self._history(run_id, status="never_started", reason_code=refusal.code,
                          ended_at=clock_mod.utc_stamp(self.clock.now()))
        self.say(f"{current['kind']} {run_id} refused: {refusal.code}: {refusal.message}")
        view = {"run_id": run_id, "items": [], "stop": {"code": refusal.code, "message": refusal.message}}
        action = rules.classify_outcome(1, view, self._past(run_id), self.policy)
        if current["kind"] == "run" and action["action"] != "stop":  # nothing to resume or go on with: no run exists
            action = {"action": "stop", "code": "AUTOPILOT_RUN_STOPPED",
                      "message": f"run {run_id} refused to start: {refusal.code}: {refusal.message}"[:400]}
        return self._apply(run_id, action)

    def _past(self, run_id: str) -> dict:
        return {"counters": self.doc["counters"], "last_blockers": self.doc["last_blockers"],
                "recoveries": self.doc["recoveries"].get(run_id, 0), "waiting_runs": len(self.doc["waiting_runs"])}

    def _look(self, current: dict) -> str:
        """``launching``, ``running``, ``hung``, ``orphaned``, ``ended``, ``gone`` (a new run that never started) or, of a
        launch intent, ``cancelled``, ``lost`` or ``invalid`` (``_intent``)."""
        directory = self.root / current["run_id"]
        young = self.clock.now() - files.epoch(current["since"]) <= LAUNCH_GRACE_S
        if current["state"] == "launching":
            found = self._intent(current, directory, young)
            if found:
                return found
        exists = (directory / RUN_FILE).is_file()
        if not exists:
            return "gone"
        lines = progress.read_lines(directory)
        found = runs.effective_status(directory, progress.summarize(lines))
        held = RunLease.held(directory) is True
        if found["status"] == "orphaned":
            return "orphaned"
        if found["status"] == "running" and held:
            hung_after = supervisor.Policy.build(self.settings).hung_after_s
            state = records.read(directory / STATE_FILE, "state") or {}
            health = runs.health_of(directory, found, state, lines, self.clock.now(), hung_after)
            return "hung" if health["health"] == "hung" else "running"
        if held or (found["status"] == "unknown" and young):
            return "running"  # the run ends (its lease goes with the process) or has just begun
        return "ended"

    def _watch(self, current: dict) -> Optional[int]:
        look = self._look(current)
        if look in ("launching", "running"):
            self._wait()
            return None
        if look in ("lost", "invalid", "relaunch"):
            return self._intent_end(current, look)
        if look == "gone":
            self._history(current["run_id"], status="never_started", ended_at=clock_mod.utc_stamp(self.clock.now()))
            self.doc["current"] = None
            self._save()
            self.say(f"run {current['run_id']} never started ({LAUNCH_GRACE_S} s without a run, a lease or an acknowledgement)")
            return None
        if look in ("hung", "orphaned"):
            return self._recover(current, look)
        return self._ended(current)

    def _recover(self, current: dict, look: str) -> Optional[int]:
        run_id = current["run_id"]
        used = self.doc["recoveries"].get(run_id, 0)
        if used >= self.policy["max_recoveries"]:
            return self._finish("AUTOPILOT_RECOVERY_EXHAUSTED", f"run {run_id} is {look} after {used} resume(s) (max_recoveries "
                                f"{self.policy['max_recoveries']}): orch conduct reap --run {run_id}, then orch conduct "
                                f"resume --run {run_id}")
        problem = self.recover_run(current, look)
        if problem == "busy":
            self._wait()  # another conductor took the run: wait for it
            return None
        if problem:
            return self._finish("AUTOPILOT_CHECKOUT_LOST", f"run {run_id} is {look} and could not be recovered: {problem}")
        self.doc["recoveries"][run_id] = used + 1
        self.doc["counters"]["recoveries"] += 1
        self.say(f"run {run_id} was {look}: reaped, resuming ({used + 1}/{self.policy['max_recoveries']})")
        return self._launch("resume", run_id)

    def _recover_run(self, current: dict, look: str) -> Optional[str]:
        """Stop a hung child by its identity, reap the role processes it left: the supervisor library only. ``None`` when the
        run is free for a resume, ``busy`` when another conductor holds it, else the problem."""
        directory = self.root / current["run_id"]
        policy = supervisor.Policy.build(self.settings, config_file=self.config_file)
        if look == "hung":  # a signal only to the saved child: never to an identity the supervisor could only half confirm
            problem = child_problem(directory, current)
            if problem:
                return f"no signal sent: {problem}"
            expected = {key: current.get(key) for key in IDENTITY}
            result = supervisor.stop_conductor(directory, policy, expected=expected)
            if result["outcome"] in ("identity_mismatch", "failed"):
                return result["detail"]
        try:
            supervisor.reap(self.project, current["run_id"], settings=self.settings, config_file=self.config_file)
        except Stop as stop:
            return "busy" if stop.code in ("RUN_BUSY", "WORKTREE_BUSY") else f"{stop.code}: {stop.message}"
        return None

    def _halt(self, code: str, message: str) -> int:
        """Stop the current child (SIGINT: it stops its roles and ends ``INTERRUPTED``, resumable), and only when no conductor
        of the run is alive any more stop the session with ``code``. A child that cannot be stopped stays ``current`` and the
        session stops with ``AUTOPILOT_CHECKOUT_LOST``: the owner must see that it still runs."""
        current = self.doc["current"]
        if current:
            done, note = self._stop_child(current)
            if not done:
                return self._finish("AUTOPILOT_CHECKOUT_LOST", f"{code} was due ({message}), but run {current['run_id']} "
                                    f"could not be stopped: {note}; "
                                    "it stays the current run of the session (orch conduct autopilot status)")
            message += note
            if self.doc["current"] is current:  # else the next attempt the fence saved instead of a cancelled launch
                self.doc["current"] = None
        return self._finish(code, message)

    def _stop_child(self, current: dict) -> tuple:
        """``(stopped, note)``: SIGINT by identity, ``grace_s`` to end, then the supervisor library (SIGINT, SIGTERM, SIGKILL to
        the identified pid, then reap of its role groups). ``stopped`` only when the run is confirmed settled."""
        run_id = current["run_id"]
        look, how, problem = self._look(current), "had already ended", None
        if look not in SETTLED:
            problem = self.launcher.interrupt(self.root / run_id, current)
            if problem is None:
                how = "was interrupted"
                deadline = self.clock.now() + self.grace_s
                look = self._look(current)
                while look not in SETTLED and self.clock.now() < deadline:
                    self.clock.sleep(min(self.policy["poll_s"], 1.0))
                    look = self._look(current)
            if look not in SETTLED:
                why = self.recover_run(current, "hung")
                if why:
                    return False, "; ".join(filter(None, (problem, "another conductor holds the run" if why == "busy" else why)))
                look = self._look(current)
                how = "did not answer SIGINT and was stopped by its identity, its roles reaped"
            if look not in SETTLED:
                return False, f"it is still {look}"
        elif look == "orphaned":
            why = self.recover_run(current, "orphaned")  # the roles a dead conductor left
            if why:
                return False, "another conductor holds the run" if why == "busy" else why
        if look == "gone":
            self._history(run_id, status="never_started", ended_at=clock_mod.utc_stamp(self.clock.now()))
            return True, f"; run {run_id} never started"
        if look == "relaunch":
            return True, f"; run {run_id} keeps its {self.doc['current']['kind']} as current for the next start"
        view, exit_code = self.view(run_id)
        self._record_end(run_id, view, exit_code)
        if self.phase and exit_code == 4:
            self._apply(run_id, {"action": "waiting", "items": [row["item"] for row in view.get("waiting") or []]})
        return True, f"; run {run_id} {how} (orch conduct resume --run {run_id})"

    # ------------------------------------------------------------------------------------------------ outcomes

    def view(self, run_id: str) -> tuple:
        """``(status view, exit code)`` of an ended run for ``classify_outcome``, from its journal and state."""
        directory = self.root / run_id
        lines = progress.read_lines(directory)
        summary = progress.summarize(lines)
        state = records.read(directory / STATE_FILE, "state") or {}
        stop = dict(state.get("stop") or ({"code": summary["reason_code"]} if summary["reason_code"] else {}))
        status = summary["status"]
        if status in EXITS:
            exit_code = EXITS[status]
        else:
            stop.setdefault("code", "CONDUCTOR_CRASHED")  # it ended without run.end: the conductor died
            exit_code = 130 if stop["code"] == "INTERRUPTED" else 1
        pieces = state.get("items") or {}
        closed = [ref for ref, piece in pieces.items() if piece.get("outcome") in ("done", "done_with_deviations")]
        blocked = blocked_pieces(state, stop, summary)
        followups = [{"group": number, "followup": kept["followup"], "counts": kept.get("counts") or {}}
                     for number, kept in sorted((state.get("group_reviews") or {}).items())
                     if kept.get("followup") and not kept.get("resolved")
                     and (kept.get("counts") or {}).get("Blocker", 0) + (kept.get("counts") or {}).get("Major", 0)]
        reset = None
        if stop.get("code") == "PROVIDER_QUOTA":
            stamps = runs.STAMP.findall(stop.get("message") or "")
            until = timefmt.epoch(stamps[-1]) if stamps else runs.reset_until(lines)
            reset = None if until is None else until - self.clock.now()
        view = {"run_id": run_id, "items": list(pieces), "closed": closed, "blocked": blocked,
                "escalations": {ref: escalations(piece) for ref, piece in pieces.items() if piece.get("outcome") == "blocked"},
                "waiting": run_service.waiting_pieces(state), "stop": stop, "group_followups": followups,
                "auto_decisions": sum(1 for line in lines if line.get("reason_code") == "QUESTION_ADVISED"),
                "dirty": self.dirty(plan_folders(self.project, state)) if exit_code in (1, 4) else False, "quota_reset_in_s": reset, "status": status}
        return view, exit_code

    def _record_end(self, run_id: str, view: dict, exit_code: int) -> dict:
        """The end of a run in ``history`` and the counters; ``view["auto_decisions"]`` becomes this end's new decisions."""
        entry = next((row for row in self.doc["history"] if row["run_id"] == run_id), None) or self._history(run_id)
        new_closed = [ref for ref in view.get("closed", []) if ref not in entry["items_closed"]]
        decisions = view.get("auto_decisions", 0) - entry.get("auto_decisions", 0)
        status = "interrupted" if exit_code == 130 else view.get("status") if view.get("status") in EXITS else "stopped"
        self._history(run_id, ended_at=clock_mod.utc_stamp(self.clock.now()), exit=exit_code, status=status,
                      reason_code=(view.get("stop") or {}).get("code"), items_closed=entry["items_closed"] + new_closed,
                      auto_decisions=view.get("auto_decisions", 0))
        self.doc["counters"]["items_closed"] += len(new_closed)
        self.doc["counters"]["auto_decisions"] += max(0, decisions)
        view["auto_decisions"] = max(0, decisions)
        return entry

    def _ended(self, current: dict) -> Optional[int]:
        run_id = current["run_id"]
        view, exit_code = self.view(run_id)
        self._record_end(run_id, view, exit_code)
        self.doc["current"] = None
        action = rules.classify_outcome(exit_code, view, self._past(run_id), self.policy)
        if self.phase and exit_code == 4:
            waiting = {"action": "waiting", "items": [row["item"] for row in view.get("waiting") or []]}
            self._apply(run_id, waiting)
        if self.phase and view.get("blocked"):
            if self.wait_blocked and action.get("code") in ("AUTOPILOT_BUDGET", "AUTOPILOT_DECISIONS_EXCEEDED", "AUTOPILOT_NO_PROGRESS",
                                                              "AUTOPILOT_OWNER_NEEDED", "AUTOPILOT_CHECKOUT_LOST",
                                                              "AUTOPILOT_STATE_INVALID", "AUTOPILOT_RUN_STOPPED"):
                return self._apply(run_id, action)
            if self.wait_blocked and action["action"] == "continue":
                self._apply(run_id, action)
            blocker = view["blocked"][0]
            return self._phase_hold("AUTOPILOT_PHASE_BLOCKED", f"phase {self.phase}: {blocker['item']} blocked ({blocker['code']})", run_id,
                                    items=[row["item"] for row in view["blocked"]])
        if self.phase and exit_code == 4:
            if action["action"] == "stop":
                return self._apply(run_id, action)
            return self._phase_hold("AUTOPILOT_PHASE_WAITING", f"phase {self.phase}: run {run_id} waits for answers", run_id)
        self.say(f"run {run_id} ended {view['status']} (exit {exit_code}): {action['action']}"
                 + (f" {action['code']}" if action.get("code") else ""))
        return self._apply(run_id, action)

    def _apply(self, run_id: str, action: dict) -> Optional[int]:
        kind = action["action"]
        if kind == "stop":
            return self._finish(action["code"], action["message"])
        now = self.clock.now()
        if kind == "continue":
            self.doc["counters"]["no_progress_streak"] = action.get("no_progress_streak",
                                                                    self.doc["counters"]["no_progress_streak"])
            if action.get("blocker"):
                self.doc["last_blockers"] = (self.doc["last_blockers"] + [
                    {**action["blocker"], "at": clock_mod.utc_stamp(now)}])[-HISTORY_MAX:]
        elif kind == "waiting":
            self.doc["waiting_runs"] = [row for row in self.doc["waiting_runs"] if row["run_id"] != run_id] + [
                {"run_id": run_id, "items": action.get("items") or [], "since": clock_mod.utc_stamp(now)}]
        elif kind == "wait_quota":
            self.doc["quota_wait"] = {"run_id": run_id, "until": clock_mod.utc_stamp(int(now + action["wait_s"]) + (now + action["wait_s"] > int(now + action["wait_s"])))}
            self.say(f"run {run_id} waits for the provider quota until {self.doc['quota_wait']['until']}")
        elif kind == "resume":
            self.doc["recoveries"][run_id] = self.doc["recoveries"].get(run_id, 0) + 1
            self.doc["counters"]["recoveries"] += 1
            self._save()
            return self._launch("resume", run_id, retry=action.get("retry"))
        self._save()
        return None
