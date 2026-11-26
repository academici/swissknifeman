"""The boundary of a step: the run clock, the disk guard, the ``started`` record before work, the ``done`` or ``stopped``
record after it and the stage event. Every stage runs its work through ``step``; a closed step is replayed, not run."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable, Optional

from orch import events
from orch.conductor import checks as checks_mod, options as opts
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, disk, tree
from orch.conductor.progress import human_duration


def active_s(self) -> float:
    """Active run time: the closed segments of earlier processes plus the one now running (a resume a day later
    does not count the day)."""
    segment = getattr(self, "_segment", None)
    return float(self.state.get("active_s", 0)) + (0.0 if segment is None else clock.mono() - segment)


def run_clock(self, item: Item, stop: bool = True) -> None:
    """RUN_SLOW every ``limits.run_warn_s`` of active run time (a beacon and one plan note per threshold, never a
    stop); ``limits.run_timeout_s`` > 0 stops the run with RUN_TIMEOUT (``stop`` false: from a thread of checks,
    where the next step boundary stops it). Called by role ticks, check ticks and step boundaries."""
    limits = (item.options or {}).get("limits") or {}
    warn, cap = limits.get("run_warn_s", 0), limits.get("run_timeout_s", 0)
    if not (warn or cap):
        return
    active = self._active_s()
    text, stage = None, self._stage_key()
    with self.store.mutating():  # a check thread and the main loop both get here (I2)
        if warn and int(active // warn) > self.state.get("run_warned", 0):
            self.state["run_warned"] = int(active // warn)
            items = self.state.get("items", {})
            closed = sum(1 for row in items.values() if row.get("outcome") in ("done", "done_with_deviations", "blocked"))
            asked = len(self.run_doc.get("items") or [])
            text = (f"run active {human_duration(active)}; {closed} piece(s) closed"
                    + (f", {max(asked - closed, 0)} left" if asked else "")
                    + f"; now {item.ref} {stage or '-'}")
            self._plan_note(item, text)
    if text is not None:  # progress and the bus after the lock
        fresh = stream_age(item, stage)
        self.progress.emit("info", item=item.ref, reason_code="RUN_SLOW",
                           message=text + (f"; its stream grew {int(fresh)}s ago" if fresh is not None else ""))
        self._beacon_event("orch.run.warning", item, {"reason_code": "RUN_SLOW", "step": stage})
    if stop and cap and active >= cap:
        raise Stop("RUN_TIMEOUT", f"the run was active {human_duration(active)}, past limits.run_timeout_s {cap}; "
                                  "raise it or set 0, then resume")


def stream_age(item: Item, stage: Optional[str]) -> Optional[float]:
    """Seconds since the newest stream of ``stage`` (``executor.1``, ``executor.1-fix1``, ...) last grew; ``None``
    when the stage has none yet (a deterministic stage, or a role not started). RUN_SLOW says only how long the run is
    active, so the age tells a slow role that streams from a silent one (the P7.2 false alarm)."""
    directory = getattr(item, "directory", None)
    if not stage or directory is None:
        return None
    try:
        times = [path.stat().st_mtime for path in (Path(directory) / "streams").glob(f"{stage}*")
                 if path.suffix in (".jsonl", ".txt")]
    except OSError:
        return None
    return max(0.0, time.time() - max(times)) if times else None


def disk_guard(self, item: Optional[Item] = None, stage: Optional[str] = None) -> None:
    """Stop with DISK_LOW (resumable: free the space, then resume) when the project or the temporary directory has less
    than ``limits.disk_min_gb`` free; the limit of the piece when there is one, else the configuration's."""
    limits = (item.options or {}).get("limits") if item is not None and item.options else None
    if limits is None:
        limits = {**opts.DEFAULT_LIMITS, **{k: v for k, v in (self.conductor.get("limits") or {}).items() if v is not None}}
    found = disk.shortage(self.project, limits.get("disk_min_gb", 0))
    if found:
        self.progress.emit("info", item=item.ref if item else None, stage=stage, reason_code="DISK_LOW", message=found)
        self._beacon_event("orch.run.warning", item, {"reason_code": "DISK_LOW", "step": stage})
        raise Stop("DISK_LOW", f"{found}; free the space, then resume")


def start_step(self, item: Item, key: str, *, role: str = "deterministic", route: Optional[str] = None) -> None:
    """Persist the boundary before work starts, including checks computed beside a review."""
    try:
        base = checks_mod.head(self.project)
    except RuntimeError:
        base = None
    dirty = tree.porcelain_paths(self.project) if key.startswith("checks.") else None
    with self.store.mutating():
        item.state.setdefault("steps", {})[key] = {
            "status": "started", "started_at": clock.utc_now(), "role": role, "route": route,
            "base_head": base, "attempt": item.claim.get("attempt_id"), "dirty_before": dirty}
        self._save()


def step(self, item: Item, key: str, run: Callable[[], Any], *, role: str = "deterministic",
         route: Optional[str] = None, verdict: Optional[Callable[[Any], str]] = None) -> Any:
    with self.store.mutating():
        steps = item.state.setdefault("steps", {})
        known = steps.get(key)
    if known and known.get("status") == "done":
        self.progress.emit("stage.skip", item=item.ref, stage=key, role=role, route=known.get("route"),
                           verdict=known.get("verdict"), message="closed earlier; not repeated")
        return known["result"]
    # Keep the fresh tokens this logical step already counted. Resetting the shared slot here let a resume,
    # and any overlap, admit a call the step had already spent (P3-STAGE-BUDGET-STATE-001).
    self._bind_stage(item, key)
    if item.options:
        self._run_clock(item)
        if role != "deterministic":
            self._admit_budget(item)
    if not known or known.get("status") != "started":
        self._start_step(item, key, role=role, route=route)
    self.progress.emit("stage.start", item=item.ref, stage=key, role=role, route=route)
    begin = time.monotonic()
    try:
        result = run()
    except Stop as stop:
        with self.store.mutating():
            steps[key] = {"status": "stopped", "code": stop.code, "ended": clock.utc_now()}
            self._save()
        self.progress.emit("stage.end", item=item.ref, stage=key, role=role, route=route, verdict="stopped",
                           reason_code=stop.code, duration_s=round(time.monotonic() - begin, 1),
                           message=stop.message)
        self._stage_event(item, key, "refused" if stop.code != "TIMEOUT" else "timeout")
        raise
    tokens = dict(self._stage_bucket())
    said = verdict(result) if verdict else "done"
    with self.store.mutating():
        steps[key] = {"status": "done", "result": result, "verdict": said, "role": role, "route": route,
                      "duration_s": round(time.monotonic() - begin, 1), "ended": clock.utc_now(),
                      **({"tokens": tokens} if tokens and any(tokens.values()) else {})}
        self._save()
    self.progress.emit("stage.end", item=item.ref, stage=key, role=role, route=route, verdict=said,
                       duration_s=steps[key]["duration_s"], tokens=steps[key].get("tokens"),
                       agent=result.get("agent") if isinstance(result, dict) else None)
    self._stage_event(item, key, "completed")
    if item.options:
        self._budget(item)
        self._admit_budget(item)
    return result


def stage_event(self, item: Item, key: str, status: str) -> None:
    kind, _, number = key.partition(".")
    data = {"run_id": item.orch_run, "stage_id": kind, "attempt": int(number) if number.isdigit() else 1,
            "status": status, "attempt_id": item.claim.get("attempt_id"),
            # none before the options are resolved (the brief step)
            "options_digest": opts.digest(item.options) if item.options else None}
    events.emit("orch.run.stage.finished", {key: value for key, value in data.items() if value is not None},
                subject=item.orch_run, settings=self.settings, project=self.project,
                config_file=self.config_file)
