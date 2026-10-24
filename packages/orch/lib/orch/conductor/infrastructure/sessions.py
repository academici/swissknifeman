"""The provider session of the executor: a slot per piece (``executor_sessions``) with the fingerprint of the identity
that built the session, the decision to resume it or start a fresh one (and why), the arguments that resume it, what the
run remembers of it and whether an attempt sends the delta prompt to a session that already holds the task."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import json
import os
import re
import subprocess
from typing import Optional

from aicore.util.digest import digest_json, sha256_tagged

from orch import bindings, launch
from orch.conductor import prompts, stubs as stubs_mod
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.route import label
from orch.conductor.infrastructure import clock

# The keys of the single session slot of a run before the slots (``executor_sessions``): a state that still has them is
# migrated into a slot when the run is resumed (``migrate_state``). They stay optional (deprecated) in the state schema.
SESSION_FIELDS = ("executor_session", "executor_session_route", "executor_session_item", "executor_session_task_digest",
                  "executor_session_answers")

SHARED_KEY = "*"  # the slot of ``session.executor = shared``: one session for every piece of the run
RESUMABLE = ("supported", "adapted")  # values of ``resume`` in the capability record of a provider that allow a resume
# The fields of the fingerprint after the provider, in the order in which the first difference names the reason.
FINGERPRINT_ORDER = ("project", "worktree", "attempt_id", "instructions_digest", "authority_digest", "isolation_home", "base")
FOLLOWUP_OMITTED = ("item", "attempt_id", "base")  # a follow-up run is another piece, attempt and revision of the same work
VOLATILE_INSTRUCTIONS = ("variant_resolution",)  # filled in lazily by the run itself, not part of its instructions


def session_mode(item: Item) -> str:
    return (item.options.get("session") or {}).get("executor", "handoff")


@lru_cache(maxsize=1)
def _capabilities() -> dict:
    return bindings.load_capabilities()


def resume_capability(provider: str) -> str:
    """``resume`` of the capability record of the provider (``native`` binding): ``supported``, ``adapted``,
    ``unsupported`` or ``unknown`` when there is no record."""
    record = _capabilities().get(("native", provider)) or {}
    return str(record.get("resume") or "unknown")


@lru_cache(maxsize=1)
def _catalog_executors() -> dict:
    return (launch.load_catalog().get("launch") or {}).get("executor") or {}


def resume_buildable(route: dict) -> bool:
    """Whether there is a command line that continues a session on ``route``: the route's own ``resume_argv`` or, for a
    provider whose catalog entry names none, the ``--resume`` flag. A route of a provider that resumes through a
    ``resume_argv`` but was started from a command line of the user (``[orch.conductor.argv]``) has no such command: it
    starts fresh rather than get a flag its CLI does not know."""
    if route.get("resume_argv"):
        return True
    return "resume_argv" not in (_catalog_executors().get(route.get("provider") or "") or {})


def resumable(route: dict) -> bool:
    return resume_capability(route.get("provider") or "") in RESUMABLE and resume_buildable(route)


def shared_session(self, item: Item, role: str, route: dict) -> bool:
    """The executor of this run keeps a provider session (``session.executor``): across its pieces (``shared``) or across
    the correction rounds of one piece (``handoff``). Whether the provider can continue one is its capability record
    (``resume`` supported or adapted), not its name, and whether the route has a command that does it."""
    return role == "executor" and resumable(route) and self._session_mode(item) in ("shared", "handoff")


def slot_key(self, item: Item) -> str:
    return SHARED_KEY if self._session_mode(item) == "shared" else item.ref


def slot_of(self, item: Item) -> Optional[dict]:
    slot = ((getattr(self, "state", None) or {}).get("executor_sessions") or {}).get(slot_key(self, item))
    return slot if isinstance(slot, dict) else None


def identity_inputs(self, item: Item, route: dict) -> dict:
    """``{authority_digest, isolation_home}`` of the fingerprint: the digest of the authority envelope of the role and the
    home directory of the provider's isolation profile. Both are empty until the profiles exist (authority envelope,
    isolation home); the fingerprint and the decision do not change when they are filled in."""
    return {"authority_digest": "", "isolation_home": ""}


@lru_cache(maxsize=32)
def _worktree(project: str) -> str:
    try:
        found = subprocess.run(["git", "-C", project, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                               check=False, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        found = ""
    return os.path.realpath(found or project)


def instructions_digest(self) -> str:
    """Canonical digest of ``<run>/instructions.json`` (the stubs snapshot of the run), without what the run fills in
    itself; empty when the run has none."""
    try:
        raw = (self.directory / stubs_mod.SNAPSHOT_FILE).read_bytes()
    except OSError:
        return ""
    try:
        return digest_json(json.loads(raw), exclude_keys=VOLATILE_INSTRUCTIONS)
    except (ValueError, TypeError):
        return sha256_tagged(raw)


def brief_base(item: Item) -> str:
    brief = (done_steps(item.state.get("steps") or {}).get("brief") or {}).get("result") or {}
    return str(brief.get("base") or "")


def fingerprint(self, item: Item, route: dict) -> dict:
    """The identity an executor session is built under (knowledge p7-design): provider, project, worktree, role,
    attempt, instructions, authority, isolation home and the revision the piece started from. ``shared`` leaves out the
    piece, the attempt and the revision: its session is the run's. The revision is that of the first brief of the piece
    (``session_base``): a later brief of the same piece, after other pieces committed, is not another identity."""
    shared = self._session_mode(item) == "shared"
    found = {"provider": route.get("provider") or "", "project": os.path.realpath(self.project),
             "worktree": _worktree(str(self.project)), "role": "executor",
             "instructions_digest": instructions_digest(self), **identity_inputs(self, item, route)}
    if not shared:
        found.update(item=item.ref, attempt_id=str((item.claim or {}).get("attempt_id") or ""),
                     base=str(item.state.get("session_base") or brief_base(item)))
    return found


def fingerprint_digest(doc: dict) -> str:
    return digest_json(doc)


def identity_digest(doc: dict) -> str:
    """Digest of a fingerprint without what a follow-up run changes (``FOLLOWUP_OMITTED``): the ``fingerprint_digest`` of the
    ``session_ref`` of a group review follow-up, and the one compared with it."""
    return digest_json({key: value for key, value in doc.items() if key not in FOLLOWUP_OMITTED})


def followup_ref(item: Item) -> Optional[dict]:
    """``provenance.session_ref`` of a group review follow-up input, when the piece is one."""
    provenance = (getattr(item, "input_doc", None) or {}).get("provenance") or {}
    found = provenance.get("session_ref") if provenance.get("kind") == "review_followup" else None
    return found if isinstance(found, dict) else None


def _age_s(stamp: str) -> float:
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds()


def session_decision(self, item: Item, route: dict, fp: dict) -> tuple:
    """``("resume", session)`` or ``("fresh", reason)`` for the next executor attempt of ``item`` on ``route`` whose identity
    is ``fp``. The reason is one of ``per_item_mode``, ``provider_unsupported``, ``first_round``, ``provider_error``,
    ``no_session_id``, ``fingerprint_changed:<field>``, ``idle_expired`` and ``followup_mismatch``. A change of the
    authority or of the instructions is never a resume (a session with broader rights must not continue silently); a
    change of model or effort of the same provider is: ``resume_args`` announces it."""
    if self._session_mode(item) not in ("shared", "handoff"):
        return "fresh", "per_item_mode"
    if not resumable(route):
        return "fresh", "provider_unsupported"
    slot = slot_of(self, item)
    if slot is None:
        ref = followup_ref(item)
        if ref is None:
            return "fresh", "first_round"
        if ref.get("session") and ref.get("provider") == fp["provider"] and ref.get("fingerprint_digest") == identity_digest(fp):
            return "resume", str(ref["session"])
        return "fresh", "followup_mismatch"
    if slot.get("error"):
        return "fresh", "provider_error"
    if not slot.get("session"):
        return "fresh", "no_session_id"
    if slot.get("provider") and slot["provider"] != fp["provider"]:
        return "fresh", "fingerprint_changed:provider"
    recorded = slot.get("fingerprint") or {}  # a slot migrated from an older state has none: it resumes as before
    for field in FINGERPRINT_ORDER:
        if recorded and (recorded.get(field) or "") != (fp.get(field) or ""):
            return "fresh", f"fingerprint_changed:{field}"
    idle = int((item.options.get("session") or {}).get("max_idle_s") or 0)
    if idle > 0 and slot.get("last_used_at") and _age_s(slot["last_used_at"]) > idle:
        return "fresh", "idle_expired"
    return "resume", str(slot["session"])


def reuse_of(self, item: Item, key: str, slot: Optional[dict]) -> str:
    """Why a resumed session is continued: ``followup``, ``question`` (the round asked again), ``next_piece`` (the session
    of the previous piece), ``retry`` (the piece taken back by ``resume --retry``) or ``correction``."""
    if slot is None:
        return "followup"
    if re.search(r"-q[0-9]+$", key):
        return "question"
    if slot.get("last_item") not in (None, item.ref):
        return "next_piece"
    retried = item.state.get("retried")
    if retried and str(slot.get("last_used_at") or "") < str(retried):
        return "retry"
    return "correction"


def decide(self, item: Item, key: str, role: str, route: dict) -> Optional[dict]:
    """The decision of one executor attempt: ``{action, value, reuse?, fingerprint}`` (``value`` is the session to resume or
    the reason of a fresh one); ``None`` for a role that keeps no session."""
    if role != "executor":
        return None
    fp = fingerprint(self, item, route)
    action, value = session_decision(self, item, route, fp)
    found = {"action": action, "value": value, "fingerprint": fp}
    if action == "resume":
        found["reuse"] = reuse_of(self, item, key, slot_of(self, item))
    return found


def event_data(decision: Optional[dict]) -> Optional[dict]:
    """``data.session`` of ``orch.agent.started``: whether the attempt resumes a session and why (the reuse or the reason)."""
    if not decision:
        return None
    resumed = decision["action"] == "resume"
    return {"resumed": resumed, "reason": decision["reuse"] if resumed else decision["value"]}


def announce_session(self, item: Item, key: str, role: str, route: dict, decision: Optional[dict]) -> None:
    """The info ``SESSION_RESUMED`` / ``SESSION_FRESH`` of one executor attempt, with the reuse or the reason."""
    if not decision:
        return
    where = dict(item=item.ref, stage=key, role=role, route=label(route))
    if decision["action"] == "resume":
        self.progress.emit("info", reason_code="SESSION_RESUMED", **where,
                           message=f"session {decision['value']} resumed; reuse={decision['reuse']}")
    else:
        self.progress.emit("info", reason_code="SESSION_FRESH", **where,
                           message=f"a fresh session starts; reason={decision['value']}")


def resume_args(self, item: Item, role: str, route: dict, decision: Optional[dict] = None) -> list:
    """``--resume SESSION`` of the executor session of the piece (``[SESSION]`` for a route whose catalog entry has a
    ``resume_argv``: that command line is built from the session by ``role_argv``); nothing when the decision is a fresh
    session. A route that names another model or effort than the one that built the session still resumes it (the
    provider continues the same transcript under the new model; the cache of the old one is lost): the change is
    announced once per change as ``SESSION_ROUTE_CHANGED``."""
    if not self._shared_session(item, role, route):
        return []
    if decision is None:
        if not (getattr(self, "state", None) or {}).get("executor_sessions") and followup_ref(item) is None:
            return []  # nothing was kept by the run: there is no decision to make
        decision = decide(self, item, "", role, route)
    if not decision or decision["action"] != "resume":
        return []
    state = getattr(self, "state", None) or {}
    before, now = (slot_of(self, item) or {}).get("route"), label(route)
    if before and before != now and state.get("executor_session_route_said") != now:
        state["executor_session_route_said"] = now
        self.progress.emit("info", item=item.ref, reason_code="SESSION_ROUTE_CHANGED",
                           message=f"the executor session was built by {before}; {item.ref} resumes it as {now}")
    session = decision["value"]
    return [session] if route.get("resume_argv") else ["--resume", session]


def keep_session(self, item: Item, role: str, route: dict, run, task_digest: Optional[str] = None,
                 delta: bool = False, decision: Optional[dict] = None) -> None:
    """Remember the session of an executor that finished in the slot of its piece, so the next executor resumes it; a
    session that failed or returned no id is dropped from the slot (a fresh one starts, ``provider_error`` or
    ``no_session_id``). ``decision`` is that of the attempt: a resumed session keeps the identity it was built under, a
    fresh one takes the identity of the attempt. ``task_digest`` is that of the full prompt the attempt sent: it is kept
    with the session, so that a later round sends the delta prompt only to a session that holds the same task; an attempt
    that sent the delta (``delta``) changes nothing in it."""
    if not self._shared_session(item, role, route):
        return
    with self.store.mutating():
        slots = self.state.setdefault("executor_sessions", {})
        key, now = slot_key(self, item), clock.utc_now()
        slot = slots.get(key) if isinstance(slots.get(key), dict) else None
        fp = (decision or {}).get("fingerprint") or fingerprint(self, item, route)
        if slot and slot.get("migrated"):  # the copies of a migrated session under the other keys would resume it unchecked
            for other in [name for name, copy in slots.items() if name != key and isinstance(copy, dict)
                          and copy.get("migrated") and copy.get("session") == slot.get("session")]:
                del slots[other]
        if run.error or not run.session:
            slots[key] = {"provider": fp["provider"], "route": label(route), "fingerprint": fp,
                          "fingerprint_digest": fingerprint_digest(fp),
                          "created_at": (slot or {}).get("created_at") or now, "last_used_at": now,
                          "rounds": (slot or {}).get("rounds", 0), "last_item": item.ref,
                          **({"error": str(run.error)} if run.error else {})}
        else:
            if slot and decision and decision["action"] == "resume" and slot.get("session") == decision["value"]:
                slot.update(session=run.session, route=label(route), last_used_at=now, rounds=slot.get("rounds", 0) + 1)
                if not slot.get("fingerprint"):  # migrated: the identity it continues under from now on
                    slot.update(fingerprint=fp, fingerprint_digest=fingerprint_digest(fp), provider=fp["provider"])
                slot.pop("migrated", None)
            else:
                slot = slots[key] = {"session": run.session, "provider": fp["provider"], "route": label(route),
                                     "fingerprint": fp, "fingerprint_digest": fingerprint_digest(fp), "created_at": now,
                                     "last_used_at": now, "rounds": 1}
            slot["last_item"] = item.ref
            if not delta:
                if task_digest:
                    slot["task_digest"] = task_digest
                else:
                    slot.pop("task_digest", None)
            if "base" in fp:
                item.state.setdefault("session_base", fp["base"])
        self._save()


def answers_seen(self, item: Item) -> set:
    """The keys of the answers the session of the piece has already been told."""
    return set((slot_of(self, item) or {}).get("answers") or [])


def note_answers(self, item: Item, keys: list) -> None:
    """The session of the piece has now seen the answers ``keys`` (the full prompt of its last round carried them)."""
    slot = slot_of(self, item)
    if slot is None or not slot.get("session") or not (keys or slot.get("answers")):
        return
    with self.store.mutating():
        slot["answers"] = list(keys)
        self._save()


def delta_mode(self, item: Item, key: str, role: str, route: dict, blocks: list, resumed: Optional[list]) -> tuple:
    """``(delta, task_digest, resuming, decision)`` of an attempt of ``role`` on ``route``: ``resuming`` when its command
    line continues a provider session (the ``decision``); ``delta`` when the delta prompt (``resumed``) is sent, which is
    only the case if all three hold: the attempt resumes the session, the session got the full prompt of this very piece
    (``last_item``), and the task of that prompt is the task of this one (``task_digest`` of the slot is the
    ``task_digest`` of the blocks now: a rebuilt input, other skills, stubs or rules make the prompt a full one)."""
    if role != "executor":
        return False, None, False, None
    digest = prompts.task_digest(self.role_ports.routed_blocks(role, route, blocks))
    decision = decide(self, item, key, role, route)
    resuming = decision is not None and decision["action"] == "resume"
    slot = slot_of(self, item) or {}
    delta = bool(resumed) and resuming and slot.get("last_item") == item.ref and slot.get("task_digest") == digest
    return delta, digest, resuming, decision


def migrate_state(state: dict, now: str) -> bool:
    """Move the keys of the single session slot of an older run (``SESSION_FIELDS``) into ``executor_sessions`` and drop
    them. The slot has no fingerprint, so it resumes as the session did before; the next round that keeps it gives it one.
    It is filed under the piece that built it and under ``*``, so ``handoff`` and ``shared`` both find it. True when the
    state had any of the keys."""
    if not any(name in state for name in SESSION_FIELDS):
        return False
    session, route, ref = state.get("executor_session"), state.get("executor_session_route"), state.get("executor_session_item")
    slot = {"session": session, "provider": str(route or "").split("/", 1)[0], "route": route or "", "fingerprint": {},
            "fingerprint_digest": "", "created_at": now, "last_used_at": now, "rounds": 0, "migrated": True,
            **({"last_item": ref} if ref else {}),
            **({"task_digest": state["executor_session_task_digest"]} if state.get("executor_session_task_digest") else {}),
            **({"answers": list(state["executor_session_answers"])} if state.get("executor_session_answers") else {})}
    if session:
        slots = state.setdefault("executor_sessions", {})
        for key in {ref or SHARED_KEY, SHARED_KEY}:
            slots.setdefault(key, dict(slot))
    for name in SESSION_FIELDS:
        state.pop(name, None)
    return True
