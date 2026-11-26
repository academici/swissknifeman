"""The controller side of the startup fence of the autopilot (P8.8): a mixin of ``autopilot.Controller``.

The launch intent ``current = {run_id, launch_id, state: launching, since}`` of ``autopilot.json`` is written, adopted and
cancelled only under ``<runs root>/autopilot-launch.lock``. A child takes the same lock before its checkout lock and run lease
(``detach.startup_fence``), starts only while the intent names its run and launch id, and writes its started acknowledgement
before it lets the lock go. So under the lock the controller sees either the acknowledgement of a launch or a launch that has
not passed its fence yet, and a launch it cancels can never start afterwards. The lock is never held while a child or an
acknowledgement is awaited.
"""
from __future__ import annotations

from pathlib import Path
import secrets
from typing import TYPE_CHECKING, Any, Callable, Optional

from orch.conductor import process, records
from orch.conductor.application import run_service
from orch.conductor.application.autopilot_status import IDENTITY
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock as clock_mod, detach
from orch.conductor.infrastructure.files import STATE_FILE, RunStore
from orch.conductor.infrastructure.lease import RunLease


class LaunchFence:
    """``_write_intent``, ``_intent`` and ``_intent_end`` of the controller (``self.doc``, ``self.launcher``, ``_save``,
    ``_history``, ``_finish`` and ``_start`` are the controller's)."""

    root: Path
    project: Path
    doc: dict
    policy: dict
    launcher: Any
    clock: Any
    say: Callable[[str], None]

    if TYPE_CHECKING:  # the controller's
        def _save(self) -> None: ...
        def _finish(self, code: str, message: str) -> int: ...
        def _history(self, run_id: str, **fields) -> dict: ...
        def _start(self, current: dict) -> Optional[int]: ...

    def _write_intent(self, current: dict) -> Optional[int]:
        """Make ``current`` the launch intent, on disk before its child exists; the stop code when the lock stays busy."""
        lock = detach.launch_lock(self.root, detach.LAUNCH_LOCK_WAIT_S)
        if lock is None:
            return self._finish("AUTOPILOT_CHECKOUT_LOST", f"{self.root / detach.LAUNCH_LOCK} stayed busy for "
                                f"{detach.LAUNCH_LOCK_WAIT_S} s: no {current['kind']} of {current['run_id']} was started")
        try:
            self.doc["current"] = current
            self._history(current["run_id"], kind=current["kind"], status="running", ended_at=None)
            self._save()
        finally:
            lock.release()
        return None

    def _intent(self, current: dict, directory: Path, young: bool) -> Optional[str]:
        """Under the launch lock: adopt the child that acknowledged this launch id (``None``), or the valid new run it created
        (``invalid``: a partial one, kept as it is). An existing run proves nothing about this launch (P8.3). Young (or the
        child still alive): ``launching``. Else cancel the intent: ``gone`` (a new run: history ``never_started``); ``lost``
        while another process holds an existing run; an existing run with a free lease keeps its id and resumable state and
        the cancelled intent is replaced in the same save by the intent of its next attempt (``relaunch``: a new launch id; a
        ``continue`` that may have begun is ``resume --retry`` of the pieces saved in its intent), so a crash or a stop before
        that attempt is spawned loses nothing."""
        lock = detach.launch_lock(self.root, detach.LAUNCH_LOCK_WAIT_S)
        if lock is None:
            return "launching"  # a child is inside its fence: look again
        try:
            ack, new = self.launcher.ack_of(current), current["kind"] == "run"
            if ack is None and new and directory.exists():  # a fenced child creates it under this lock, then acknowledges
                try:
                    RunStore(self.project, current["run_id"]).load()
                except Stop:
                    return "invalid"
                ack = RunLease.owner(directory) if RunLease.held(directory) is True else {}
            if ack is not None:  # the child made it: adopt it with its whole identity (unknown parts stay unknown)
                current.update(state="running", **{key: ack[key] for key in IDENTITY if ack.get(key) is not None})
                self._save()
                self.say(f"adopted {current['kind']} {current['run_id']}")
                return None
            if young:
                return "launching"
            if not new and RunLease.held(directory) is not False:
                return "lost"  # held without the acknowledgement of this launch: no second child
            # from now on a child of this launch id is refused (AUTOPILOT_LAUNCH_CANCELLED)
            again = None if new else next_attempt(current, self.clock.now())
            self.doc["current"] = again
            if again is None:
                self._history(current["run_id"], status="never_started", ended_at=clock_mod.utc_stamp(self.clock.now()))
            else:
                self._history(current["run_id"], kind=again["kind"], status="running", ended_at=None)
            self._save()
            return "gone" if new else "relaunch"
        finally:
            lock.release()

    def _intent_end(self, current: dict, look: str) -> Optional[int]:
        """``lost`` and ``invalid`` stop the session, the run kept; ``relaunch`` starts the saved next attempt of the run
        (counted as a run): at ``max_runs`` the session stops and the attempt stays ``current`` for the next start."""
        run_id, launch_id = current["run_id"], current["launch_id"]
        if look != "relaunch":
            code, what = {"lost": ("AUTOPILOT_CHECKOUT_LOST", "another process holds"),
                          "invalid": ("AUTOPILOT_STATE_INVALID", "a partial record is left of")}[look]
            return self._finish(code, f"{what} run {run_id} without the acknowledgement of launch {launch_id}; it is kept "
                                "as it is: repair or release it, then start again")
        again = self.doc["current"]
        if self.doc["counters"]["runs"] >= self.policy["max_runs"]:
            return self._finish("AUTOPILOT_MAX_RUNS", f"launch {launch_id} of run {run_id} was never acknowledged and "
                                f"{self.doc['counters']['runs']} run(s) were started (max_runs {self.policy['max_runs']}); its "
                                f"{again['kind']} waits as launch {again['launch_id']} for the next start")
        self.doc["counters"]["runs"] += 1
        self.say(f"{current['kind']} {run_id}: launch {launch_id} was never acknowledged and is cancelled; "
                 f"{again['kind']} again as launch {again['launch_id']}")
        return self._start(again)


def next_attempt(current: dict, now: float) -> dict:
    """The intent of the next attempt of an existing run whose launch was cancelled: a new launch id, the same run, and for a
    ``continue`` whose pieces were saved ``resume --retry`` of them (taking a piece back again is idempotent, so a continue
    that began before it died is gone on with, not refused ``NOT_WAITING``)."""
    kind = "resume" if current["kind"] == "continue" and current.get("retry") else current["kind"]
    return {"run_id": current["run_id"], "launch_id": secrets.token_hex(8), "state": "launching", "kind": kind,
            "since": clock_mod.utc_stamp(now), "boot_id": process.boot_id(),
            **({"retry": list(current["retry"])} if current.get("retry") else {})}


def retry_targets(root: Path, run_id: str) -> list:
    """The waiting pieces a ``continue`` of ``run_id`` takes back, saved in its intent before its child changes them."""
    try:
        state = records.read(Path(root) / run_id / STATE_FILE, "state") or {}
    except Stop:
        return []
    return [row["item"] for row in run_service.waiting_pieces(state)]
