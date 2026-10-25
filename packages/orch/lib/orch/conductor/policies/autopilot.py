"""The rules of the autopilot (D9, I14), pure: no IO, no clock, no signal. ``effective_policy`` merges ``[orch.autopilot]``
over the layers so that a project can never widen what the machine allows; ``classify_outcome`` turns the end of one conductor
run into the next action of the controller or an ``AUTOPILOT_*`` stop; ``choose_next`` picks the next work from the waiting runs
and the readiness of the work source. The controller that acts on them is ``application/autopilot.py``.
"""
from __future__ import annotations

import re
from typing import Optional

# Exit 0: the session ended as asked or as planned; every other code needs the owner (exit 1).
FINE = ("AUTOPILOT_NO_WORK", "AUTOPILOT_DRAINED", "AUTOPILOT_STOPPED", "AUTOPILOT_MAX_RUNS", "AUTOPILOT_MAX_WALL")
CODES = FINE + ("AUTOPILOT_NOT_ALLOWED", "AUTOPILOT_DISABLED", "AUTOPILOT_BUSY", "AUTOPILOT_NOT_READY", "AUTOPILOT_OWNER_NEEDED",
                "AUTOPILOT_BUDGET", "AUTOPILOT_QUOTA", "AUTOPILOT_REPEATED_BLOCKER", "AUTOPILOT_NO_PROGRESS",
                "AUTOPILOT_DECISIONS_EXCEEDED", "AUTOPILOT_RECOVERY_EXHAUSTED", "AUTOPILOT_CHECKOUT_LOST",
                "AUTOPILOT_STATE_INVALID", "AUTOPILOT_RUN_STOPPED", "AUTOPILOT_INTERRUPTED")
DEFAULTS = {"allowed": False, "enabled": False, "require_readiness": True, "max_runs": 20, "max_wall_s": 43200,
            "max_no_progress_runs": 2, "max_auto_decisions": 10, "quota_wait_max_s": 21600, "poll_s": 30, "max_recoveries": 1}
AUTHORITY = ("defaults", "machine")  # the layers that set what the machine allows
LIMITS = ("max_runs", "max_wall_s", "max_no_progress_runs", "max_auto_decisions", "quota_wait_max_s", "max_recoveries")
FLAGS = {"max_runs": "--max-runs", "max_wall_s": "--max-wall-s", "run_tokens_hard_max": "--run-tokens-hard-max",
         "poll_s": "--poll-s"}
# One-time failures of a run: resumed (max_recoveries per run), never repeated past it.
TRANSIENT = frozenset({"TIMEOUT", "ROLE_FAILED", "ROLE_OUTPUT_EMPTY", "ROLE_OUTPUT_INVALID", "MODEL_UNAVAILABLE",
                       "GROUP_REVIEW_FAILED", "QUESTIONS_LOCKED", "CONDUCTOR_CRASHED"})
BLOCKERS = frozenset({"ITEM_BLOCKED", "CHECKS_RED", "REVIEW_LIMIT"})
CHECKOUT = frozenset({"RUN_BUSY", "WORKTREE_BUSY"})
STATE = frozenset({"STATE_CORRUPT", "STATE_INVALID", "RUN_INVALID"})
DONE_KINDS = ("terminal", "archive")  # a next step of a plan that has no work left
READY = ("ready", "ready_with_advisories")
MAX_WAITING_RUNS = 3
PROTECTED = re.compile(r"^WRITE_PROTECTED_PATH:\s*(\S+)\s*->\s*(\S+)")
RETRY = re.compile(r"--retry (\S+)")


def exit_code(code: str) -> int:
    return 0 if code in FINE else 1


def _authority(rows: list) -> dict:
    found = [row for row in rows if row["layer"] in AUTHORITY]
    return found[-1] if found else rows[0]


def effective_policy(layers: dict, flags: Optional[dict] = None) -> tuple:
    """``(policy, sources)`` of ``[orch.autopilot]``. ``layers`` is ``{key: [{layer, value}, ...]}`` lowest first (the
    ``Settings.autopilot`` of ``settings.layer_history``), ``flags`` the numbers of ``start`` (``max_runs``, ``max_wall_s``,
    ``run_tokens_hard_max``, ``poll_s``; ``None`` or absent: not given).

    ``allowed`` is the machine's (a value of another layer is ignored); ``enabled`` is the value of the highest layer (a project
    enables its own autopilot); ``require_readiness`` is on when the machine or any other layer turns it on; every limit is the
    lowest of the machine value and the values of the other layers and the flags; ``poll_s`` is the value of the highest layer,
    lowered by its flag (a float there: the tests look every 0.2 s; a configuration value stays an integer, as the digest of
    the configuration of a run allows no float).
    ``sources`` names the layer (or ``flag:--max-runs``) each value comes from."""
    flags = flags or {}
    policy: dict = {}
    sources: dict = {}

    def rows(key: str) -> list:
        return list(layers.get(key) or []) or [{"layer": "defaults", "value": DEFAULTS[key]}]

    chosen = _authority(rows("allowed"))
    policy["allowed"], sources["allowed"] = bool(chosen["value"]), chosen["layer"]
    chosen = rows("enabled")[-1]
    policy["enabled"], sources["enabled"] = bool(chosen["value"]), chosen["layer"]
    base = _authority(rows("require_readiness"))
    turned = next((row for row in rows("require_readiness") if row["layer"] not in AUTHORITY and row["value"] is True), None)
    chosen = base if base["value"] or turned is None else turned
    policy["require_readiness"], sources["require_readiness"] = bool(chosen["value"]), chosen["layer"]
    for key in LIMITS:
        base = _authority(rows(key))
        value, source = base["value"], base["layer"]
        for row in rows(key):
            if row["layer"] not in AUTHORITY and row["value"] is not None and row["value"] < value:
                value, source = row["value"], row["layer"]
        if flags.get(key) is not None and flags[key] < value:
            value, source = flags[key], f"flag:{FLAGS[key]}"
        policy[key], sources[key] = int(value), source
    chosen = rows("poll_s")[-1]
    policy["poll_s"], sources["poll_s"] = float(chosen["value"]), chosen["layer"]
    if flags.get("poll_s") is not None and flags["poll_s"] < policy["poll_s"]:
        policy["poll_s"], sources["poll_s"] = float(flags["poll_s"]), f"flag:{FLAGS['poll_s']}"
    cap = flags.get("run_tokens_hard_max")
    policy["run_tokens_hard_max"] = int(cap or 0)
    sources["run_tokens_hard_max"] = f"flag:{FLAGS['run_tokens_hard_max']}" if cap else "none"
    return policy, sources


def _stop(code: str, message: str) -> dict:
    return {"action": "stop", "code": code, "message": message}


def protected_pairs(escalations: list) -> list:
    """``[(path, staged)]`` when every escalation is ``WRITE_PROTECTED_PATH: <path> -> <staged path>``, else ``[]``."""
    found = [PROTECTED.match(text or "") for text in escalations]
    pairs = [(match.group(1), match.group(2)) for match in found if match is not None]
    return pairs if found and len(pairs) == len(found) else []


def classify_outcome(exit_code: Optional[int], status: dict, history: dict, policy: dict) -> dict:
    """The next action after a conductor run ended: ``{"action": "continue"|"resume"|"wait_quota"|"waiting"|"stop", ...}``.

    ``exit_code`` is what the run ended with (0 finished, 4 waiting, 1 stopped, 130 interrupted). ``status`` is the controller's
    view of the run: ``run_id``, ``items`` (pieces it worked on), ``closed``, ``blocked`` (``[{item, code}]``), ``escalations``
    (``{item: [text]}``), ``waiting`` (``[{item, question_ids}]``), ``stop`` (``{code, message}``), ``group_followups``
    (``[{group, followup, counts}]`` of unresolved Blocker/Major group reviews), ``auto_decisions`` (``QUESTION_ADVISED`` lines of
    this run not counted yet), ``dirty`` (tracked changes outside ``.swissknifeman/`` and the plan) and ``quota_reset_in_s``.
    ``history`` holds ``counters`` (already counting this run's decisions), ``last_blockers``, ``recoveries`` (of this run) and
    ``waiting_runs`` (how many wait now). Every stop carries one action for the owner in its message."""
    run = status.get("run_id") or "the run"
    counters = history.get("counters") or {}
    stop = status.get("stop") or {}
    for entry in status.get("group_followups") or []:
        counts = entry.get("counts") or {}
        return _stop("AUTOPILOT_OWNER_NEEDED",
                     f"the group review {entry['group']} of run {run} found {counts.get('Blocker', 0)} Blocker and "
                     f"{counts.get('Major', 0)} Major finding(s): correct them with orch conduct run --input "
                     f"{entry['followup']} --commit")
    decided = counters.get("auto_decisions", 0)
    if status.get("auto_decisions") and decided >= policy["max_auto_decisions"]:
        return _stop("AUTOPILOT_DECISIONS_EXCEEDED", f"{decided} question(s) were answered by the advisor or panel in this "
                     f"session (max_auto_decisions {policy['max_auto_decisions']}); review the decisions of run {run}")
    if exit_code == 0:
        return _finished(run, status, history, policy)
    if exit_code == 4:
        waiting = status.get("waiting") or []
        named = ", ".join(f"{row['item']} ({', '.join(row.get('question_ids') or [])})" for row in waiting) or "a piece"
        if status.get("dirty"):
            return _stop("AUTOPILOT_OWNER_NEEDED", f"run {run} waits for answers to {named} and the checkout has tracked "
                         f"changes (left as they are): answer with orch conduct answer --run {run}, then orch conduct "
                         f"continue --run {run}")
        if history.get("waiting_runs", 0) + 1 >= MAX_WAITING_RUNS:
            return _stop("AUTOPILOT_OWNER_NEEDED", f"{history.get('waiting_runs', 0) + 1} runs wait for answers (the last: "
                         f"{run}, {named}): answer them with orch conduct answer")
        return {"action": "waiting", "items": [row["item"] for row in waiting]}
    if exit_code == 130:
        return _stop("AUTOPILOT_INTERRUPTED", f"run {run} was interrupted, not by a stop request: orch conduct resume --run {run}")
    if exit_code != 1:
        return _stop("AUTOPILOT_RUN_STOPPED", f"run {run} ended with exit {exit_code}: orch conduct status --run {run}")
    return _stopped(run, stop, status, history, policy)


def _finished(run: str, status: dict, history: dict, policy: dict) -> dict:
    counters = history.get("counters") or {}
    if not status.get("items"):
        return _stop("AUTOPILOT_NO_WORK", f"run {run} took no piece: the work source has no ready piece")
    blocker = (status.get("blocked") or [None])[0]
    if blocker:
        repeated = _repeated(blocker, history)
        if repeated:
            return repeated
    if status.get("closed"):
        return {"action": "continue", "no_progress_streak": 0, "blocker": blocker}
    streak = counters.get("no_progress_streak", 0) + 1
    if streak >= policy["max_no_progress_runs"]:
        return _stop("AUTOPILOT_NO_PROGRESS", f"{streak} run(s) in a row closed no piece (the last: {run}): orch conduct "
                     f"status --run {run}")
    return {"action": "continue", "no_progress_streak": streak, "blocker": blocker}


def _repeated(blocker: dict, history: dict) -> Optional[dict]:
    last = (history.get("last_blockers") or [None])[-1]
    if last and (last.get("item"), last.get("code")) == (blocker["item"], blocker["code"]):
        return _stop("AUTOPILOT_REPEATED_BLOCKER", f"{blocker['item']} is blocked by {blocker['code']} a second time in a row: "
                     "read its escalation, amend the plan, then start the autopilot again")
    return None


def _stopped(run: str, stop: dict, status: dict, history: dict, policy: dict) -> dict:
    code, message = stop.get("code") or "UNKNOWN", stop.get("message") or ""
    if code == "PROVIDER_QUOTA":
        reset = status.get("quota_reset_in_s")
        if reset is not None and reset <= policy["quota_wait_max_s"]:
            return {"action": "wait_quota", "wait_s": max(0, int(reset) + 1)}
        when = "unknown" if reset is None else f"in {int(reset)} s"
        return _stop("AUTOPILOT_QUOTA", f"run {run} stopped on a provider quota whose reset is {when} (quota_wait_max_s "
                     f"{policy['quota_wait_max_s']}): orch conduct resume --run {run} after the reset")
    if code.startswith("TOKEN_BUDGET"):
        return _stop("AUTOPILOT_BUDGET", f"run {run} stopped with {code}: raise the limit with orch conduct resume --run {run} "
                     "--raise-limit KEY=N")
    if code in TRANSIENT or code == "QUESTION_ANSWERED_NOT_RETRIED":
        if history.get("recoveries", 0) >= policy["max_recoveries"]:
            return _stop("AUTOPILOT_RECOVERY_EXHAUSTED", f"run {run} stopped with {code} after {history.get('recoveries', 0)} "
                         f"resume(s) (max_recoveries {policy['max_recoveries']}): orch conduct status --run {run}")
        retry = list(dict.fromkeys(RETRY.findall(message))) if code == "QUESTION_ANSWERED_NOT_RETRIED" else []
        return {"action": "resume", "retry": retry, "reason": code}
    blocker = (status.get("blocked") or [None])[0]
    if code == "ITEM_BLOCKED" and blocker:
        pairs = protected_pairs((status.get("escalations") or {}).get(blocker["item"]) or [])
        if pairs:
            placed = "; ".join(f"{path} <- {staged}" for path, staged in pairs)
            return _stop("AUTOPILOT_OWNER_NEEDED", f"{blocker['item']} needs protected files placed by the owner ({placed}), "
                         f"then orch conduct resume --run {run} --retry {blocker['item']}")
    if code in BLOCKERS:
        if status.get("dirty"):
            return _stop("AUTOPILOT_OWNER_NEEDED", f"run {run} stopped with {code} and left tracked changes in the checkout: "
                         f"settle or retry the piece (orch conduct status --run {run})")
        blocker = blocker or {"item": stop.get("item") or "-", "code": code}
        return _repeated(blocker, history) or {"action": "continue", "blocker": blocker}
    if code in CHECKOUT:
        return _stop("AUTOPILOT_CHECKOUT_LOST", f"run {run}: {code}: another conductor holds the run or the checkout; wait for it "
                     "or stop it, then start the autopilot again")
    if code in STATE:
        return _stop("AUTOPILOT_STATE_INVALID", f"run {run} stopped with {code}: repair or release the run (orch conduct status "
                     f"--run {run})")
    return _stop("AUTOPILOT_RUN_STOPPED", f"run {run} stopped with {code}: {message}"[:400])


def next_code(kind: Optional[str]) -> str:
    return "NEXT_" + re.sub(r"[^A-Z0-9]+", "_", str(kind).upper()).strip("_")


def choose_next(answered: Optional[str], waiting_runs: int, readiness: Optional[dict], policy: dict) -> dict:
    """What to start when no run is current: ``{"action": "continue", "run_id"}`` for a waiting run whose questions are all
    answered (readiness is not asked then), ``{"action": "run", "items", "phase"}`` for the next lane of the source,
    ``{"action": "wait_answers"}`` while runs wait for answers and nothing else can start, else a stop (``AUTOPILOT_NO_WORK``,
    ``AUTOPILOT_NOT_READY``). With ``require_readiness`` exactly the phase of the next lane must be ready; other phases
    (finished, unrelated) do not matter."""
    if answered:
        return {"action": "continue", "run_id": answered}
    readiness = readiness or {}
    if readiness.get("outcome") != "ok":
        if waiting_runs:
            return {"action": "wait_answers"}
        return _stop("AUTOPILOT_NOT_READY", f"{readiness.get('reason_code') or 'READINESS_UNKNOWN'}: the work source tells no "
                     f"readiness ({readiness.get('message') or 'no answer'})")
    following = readiness.get("next") or {}
    kind = following.get("kind")
    if kind == "run-items" and following.get("items"):
        if policy.get("require_readiness"):
            phase = following.get("phase")
            if not phase:
                return _stop("AUTOPILOT_NOT_READY", "READINESS_PHASE_UNKNOWN: the next lane names no phase to check: "
                             + ", ".join(following["items"]))
            found = next((row for row in readiness.get("phases") or [] if row.get("id") == phase), None)
            state = (found or {}).get("status", "missing")
            if state not in READY:
                return _stop("AUTOPILOT_NOT_READY", f"READINESS_{state.upper()}: phase {phase} of the next lane "
                             f"({', '.join(following['items'])}) is {state}: audit it (plan-audit), then start again")
        return {"action": "run", "items": list(following["items"]), "phase": following.get("phase")}
    if waiting_runs:
        return {"action": "wait_answers"}
    if kind in DONE_KINDS:
        return _stop("AUTOPILOT_NO_WORK", f"the plan has no work left ({kind})")
    return _stop("AUTOPILOT_NOT_READY", f"{next_code(kind)}: {following.get('message') or 'the next step is not a lane of pieces'}")
