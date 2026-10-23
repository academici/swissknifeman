"""The provider session of the executor: whether a route keeps one, the arguments that resume it, what the run
remembers of it and whether an attempt sends the delta prompt to a session that already holds the task."""
from __future__ import annotations

from typing import Optional

from orch.conductor import prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain.route import label

# What the run keeps of the executor session; all of it is forgotten with the session.
SESSION_FIELDS = ("executor_session", "executor_session_route", "executor_session_item", "executor_session_task_digest",
                  "executor_session_answers")


def session_mode(item: Item) -> str:
    return (item.options.get("session") or {}).get("executor", "handoff")


def shared_session(self, item: Item, role: str, route: dict) -> bool:
    """The executor of this run keeps a provider session (``session.executor``): across its pieces (``shared``) or across
    the correction rounds of one piece (``handoff``)."""
    return role == "executor" and (route.get("provider") == "claude-code" or bool(route.get("resume_argv"))) \
        and self._session_mode(item) in ("shared", "handoff")


def resume_args(self, item: Item, role: str, route: dict) -> list:
    """``--resume SESSION`` of the shared executor session (``[SESSION]`` for a route whose catalog entry has a
    ``resume_argv``: that command line is built from the session by ``role_argv``). A piece whose route names another model or effort than the
    one that built the session still resumes it (the provider continues the same transcript under the new model; the
    cache of the old one is lost): the change is announced once per change as ``SESSION_ROUTE_CHANGED``."""
    state = getattr(self, "state", None) or {}
    session = state.get("executor_session")
    if not (session and self._shared_session(item, role, route)):
        return []
    if self._session_mode(item) == "handoff" and state.get("executor_session_item") != item.ref:
        return []  # a new piece starts fresh; the handoff of the earlier pieces is in its prompt
    before, now = state.get("executor_session_route"), label(route)
    if before and before != now and state.get("executor_session_route_said") != now:
        state["executor_session_route_said"] = now
        self.progress.emit("info", item=item.ref, reason_code="SESSION_ROUTE_CHANGED",
                           message=f"the shared executor session was built by {before}; {item.ref} resumes it as {now}")
    return [session] if route.get("resume_argv") else ["--resume", session]


def keep_session(self, item: Item, role: str, route: dict, run, task_digest: Optional[str] = None,
                 delta: bool = False) -> None:
    """Remember the session of an executor that finished, so the next executor of the run resumes it; forget a
    session that failed (a fresh one starts). ``task_digest`` is that of the full prompt the attempt sent: it is kept
    with the session, so that a later round sends the delta prompt only to a session that holds the same task; an attempt
    that sent the delta (``delta``) changes nothing in it."""
    if not self._shared_session(item, role, route):
        return
    with self.store.mutating():
        if run.error or not run.session:
            for name in SESSION_FIELDS:
                self.state.pop(name, None)
        else:
            self.state["executor_session"] = run.session
            self.state["executor_session_route"] = label(route)
            self.state["executor_session_item"] = item.ref
            if not delta:
                if task_digest:
                    self.state["executor_session_task_digest"] = task_digest
                else:
                    self.state.pop("executor_session_task_digest", None)
        self._save()


def delta_mode(self, item: Item, role: str, route: dict, blocks: list, resumed: Optional[list]) -> tuple:
    """``(delta, task_digest, resuming)`` of an attempt of ``role`` on ``route``: ``resuming`` when its command line
    continues a provider session; ``delta`` when the delta prompt (``resumed``) is sent, which is only the case if all
    three hold: the attempt resumes the session, the session got the full prompt of this very piece
    (``executor_session_item``), and the task of that prompt is the task of this one (``executor_session_task_digest`` is
    the ``task_digest`` of the blocks now: a rebuilt input, other skills, stubs or rules make the prompt a full one)."""
    if role != "executor":
        return False, None, False
    digest = prompts.task_digest(self.role_ports.routed_blocks(role, route, blocks))
    resuming = bool(self._resume_args(item, role, route))
    state = getattr(self, "state", None) or {}
    delta = bool(resumed) and resuming and state.get("executor_session_item") == item.ref \
        and state.get("executor_session_task_digest") == digest
    return delta, digest, resuming
