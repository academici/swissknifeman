"""The health of a run: what it is doing and whether it still moves, from its journal, its state, its heartbeat and the
probe of its lease. One pure function (:func:`classify`): no IO, no clock (``now`` comes in), no write, no event, no signal.
``orch conduct status`` and ``orch conduct runs`` read it; what to do about a class (the supervisor of P8.2) is not decided
here. A wait with a deadline that has not passed is checked before the age of the heartbeat: a call of the work source may
take ten minutes without a line, and a run that waits for its owner or for a provider limit is not stuck.

Classes: ``running``, ``waiting_provider``, ``waiting_tool``, ``waiting_owner``, ``waiting_budget_reset``,
``suspected_stall``, ``hung``, ``orphaned``, ``stopped``, ``finished``, ``unknown``. Only ``hung`` may be acted on.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from aicore.util import timefmt

CLASSES = ("running", "waiting_provider", "waiting_tool", "waiting_owner", "waiting_budget_reset", "suspected_stall", "hung",
           "orphaned", "stopped", "finished", "unknown")
INVALID = "invalid"  # key of a heartbeat the reader could not use: {"invalid": "<why>"}
IDENTITY = ("pid", "start_ticks", "boot_id")


@dataclass(frozen=True)
class Thresholds:
    """``hung_after_s``: age of the heartbeat of a run that waits for nothing; ``stall_window_s`` and ``stall_repeat_n``: the
    limits of the piece (0 switches the rule off); ``wait_grace_s``: how far past its deadline a wait may run unremarked."""
    hung_after_s: int = 300
    stall_window_s: int = 1800
    stall_repeat_n: int = 5
    wait_grace_s: int = 60


def _epoch(value) -> Optional[float]:
    return timefmt.epoch(value) if isinstance(value, str) else None


def _waits_for_owner(summary: dict, state: dict) -> bool:
    """A piece waits for an answer (P7.5): the run ended ``waiting``, or its state says so, or a piece of a run that is not
    driven now waits."""
    if summary.get("status") == "waiting" or state.get("status") == "waiting":
        return True
    if summary.get("status") in ("running", "orphaned"):
        return False  # a conductor that still drives other pieces is judged by its heartbeat
    return any(isinstance(row, dict) and row.get("waiting") for row in (state.get("items") or {}).values())


def _mismatch(heartbeat: dict, lease: dict) -> Optional[str]:
    owner = lease.get("owner") or {}
    for key in IDENTITY:
        if owner.get(key) is not None and heartbeat.get(key) is not None and owner[key] != heartbeat[key]:
            return f"heartbeat {key} {heartbeat[key]} is not the lease owner's {owner[key]}"
    return None


def classify(summary: dict, state: dict, heartbeat: Optional[dict], lease: dict, now: float,
             thresholds: Optional[Thresholds] = None) -> dict:
    """``{health, since, silent_s, reason_code, detail, heartbeat_age_s, waiting}`` of a run.

    ``summary`` is ``progress.summarize`` of the journal (``status`` may already be ``orphaned``; ``reset_until`` is the epoch
    time a quota is lifted, when the journal says), ``state`` the run state, ``heartbeat`` the document of
    ``heartbeat.json`` (``None``: there is none; ``{"invalid": why}``: it could not be used) and ``lease``
    ``{held: True|False|None, owner: {...}|None, flag: run.json lease}``. The first rule that fits decides."""
    state, lease, thresholds = state or {}, lease or {}, thresholds or Thresholds()
    status = summary.get("status")
    usable = heartbeat if isinstance(heartbeat, dict) and INVALID not in heartbeat else None
    reference = (usable or {}).get("last_progress_at") or (usable or {}).get("at") or summary.get("last_ts")
    at = _epoch((usable or {}).get("at"))
    age = None if at is None else max(0, int(now - at))
    waiting = (usable or {}).get("waiting") if isinstance((usable or {}).get("waiting"), dict) else None
    since = reference if isinstance(reference, str) else None
    referenced = _epoch(reference)
    silent = None if referenced is None else max(0, int(now - referenced))

    def result(health: str, code: Optional[str] = None, detail: str = "", **more) -> dict:
        live = health not in ("finished", "stopped", "orphaned", "unknown", "waiting_owner", "waiting_budget_reset")
        return {"health": health, "since": since if live else None, "silent_s": silent if live else None,
                "reason_code": code, "detail": detail, "heartbeat_age_s": age, "waiting": waiting, **more}

    if status == "finished":
        return result("finished")
    reset = summary.get("reset_until")
    if status == "stopped" and (state.get("stop") or {}).get("code") == "PROVIDER_QUOTA" \
            and isinstance(reset, (int, float)) and reset > now:
        return result("waiting_budget_reset", "PROVIDER_QUOTA", f"the provider limit is lifted in {int(reset - now)} s")
    if _waits_for_owner(summary, state):
        return result("waiting_owner", "WAITING_DECISION", "a piece waits for the answer to a question")
    if status in ("stopped", "interrupted"):
        return result("stopped", summary.get("reason_code") or (state.get("stop") or {}).get("code"))
    if status == "orphaned" or (status == "running" and lease.get("flag") is True and lease.get("held") is False):
        return result("orphaned", "RUN_ORPHANED", "no conductor holds the lease of the run")
    if status != "running":
        return result("unknown", "STATUS_UNKNOWN", f"the journal says {status or 'nothing'}")
    if lease.get("flag") is True and lease.get("held") is None:
        return result("unknown", "LEASE_UNKNOWN", "the lease of the run cannot be probed from here")
    if isinstance(heartbeat, dict) and INVALID in heartbeat:
        return result("unknown", "HEARTBEAT_INVALID", str(heartbeat[INVALID]))
    if usable is None:
        return result("running", "HEARTBEAT_MISSING", "the run has no heartbeat.json (it began before heartbeats, or just now)")
    other = _mismatch(usable, lease) if lease.get("held") else None
    if other:
        return result("suspected_stall", "HEARTBEAT_OWNER_MISMATCH", other)
    if waiting and waiting.get("kind") == "question":
        return result("waiting_owner", "QUESTION_WAITING", "the conductor waits for the answer to a question")
    deadline = _epoch(waiting.get("deadline")) if waiting else None
    if waiting and deadline is not None:
        what = f"{waiting.get('kind')}: {waiting.get('reason_code')}"
        if now <= deadline:
            if waiting.get("kind") == "provider":
                return result("waiting_provider", "PROVIDER_WAIT", f"waiting for the provider, {int(deadline - now)} s to the deadline")
            return result("waiting_tool", waiting.get("reason_code"), f"{what}, {int(deadline - now)} s to the deadline")
        if now - deadline > thresholds.hung_after_s:
            return result("hung", "HEARTBEAT_STALE", f"{what} is {int(now - deadline)} s past its deadline")
        if now > deadline + thresholds.wait_grace_s:
            return result("suspected_stall", "WAIT_DEADLINE_PASSED", f"{what} is {int(now - deadline)} s past its deadline")
        return result("waiting_tool", waiting.get("reason_code"), f"{what} is just past its deadline")
    if age is not None and age > thresholds.hung_after_s:
        return result("hung", "HEARTBEAT_STALE", f"the heartbeat is {age} s old")
    progress, cpu = _epoch(usable.get("last_progress_at")), _epoch(usable.get("last_cpu_at"))
    if usable.get("role") and usable.get("step") and progress is not None and thresholds.stall_window_s \
            and now - progress > thresholds.stall_window_s:
        repeated = (usable.get("repeat") or {}).get("count", 0)
        cold = cpu is None or now - cpu > thresholds.stall_window_s
        if cold or (thresholds.stall_repeat_n and repeated >= thresholds.stall_repeat_n):
            return result("suspected_stall", "STALL_SUSPECTED", f"no tool step for {int(now - progress)} s"
                          + (f"; the same command {repeated} times" if repeated >= thresholds.stall_repeat_n > 0 else ""))
    return result("running")
