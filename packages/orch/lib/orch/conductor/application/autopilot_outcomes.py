"""Outcome accounting and follow-up decisions of the autopilot controller."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from aicore.util import timefmt
from orch.conductor import progress, records, runs
from orch.conductor.application import run_service
from orch.conductor.application.autopilot_status import blocked_pieces, escalations, plan_folders
from orch.conductor.infrastructure import clock as clock_mod
from orch.conductor.infrastructure.files import STATE_FILE
from orch.conductor.policies import autopilot as rules

EXITS = {"finished": 0, "waiting": 4}
HISTORY_MAX = 50


class RunOutcomes:
    """Accounting shared by normal completion, recovery and phase waiting."""
    root: Path
    project: Path
    doc: dict
    policy: dict
    clock: Any
    phase: Optional[str]
    wait_blocked: bool
    dirty: Callable
    say: Callable[[str], None]

    if TYPE_CHECKING:
        def _save(self) -> None: ...
        def _finish(self, code: str, message: str) -> int: ...
        def _history(self, run_id: str, **fields) -> dict: ...
        def _phase_hold(self, code: str, message: str, run_id: Optional[str] = None,
                        readiness: Optional[dict] = None, items: Optional[list] = None) -> Optional[int]: ...
        def _launch(self, kind: str, run_id: str, *, items: Optional[list] = None,
                    retry: Optional[list] = None) -> Optional[int]: ...

    def _past(self, run_id: str) -> dict:
        return {"counters": self.doc["counters"], "last_blockers": self.doc["last_blockers"],
                "recoveries": self.doc["recoveries"].get(run_id, 0), "waiting_runs": len(self.doc["waiting_runs"])}

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
        history = self._past(run_id)
        if self.phase and self.wait_blocked and exit_code == 0 and view.get("blocked"):
            # Phase waiting handles repeated blockers itself, but still needs the finished run's progress accounting.
            history = {**history, "last_blockers": []}
        action = rules.classify_outcome(exit_code, view, history, self.policy)
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
