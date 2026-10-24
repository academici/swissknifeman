"""A role as a process and an agent run: its prompt and manifest, the call of the provider and its repeats, and the
beacons of a long or silent run. The launch plan, the session, the usage ledger, the result and the tree a role works
in are their own modules; what the role needs from the layers above comes in :class:`RolePorts`."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Callable, NamedTuple, Optional

from aicore.util.digest import sha256_hex

from orch import events, settings as settings_mod
from orch.conductor import agents, options as opts, process, prompts
from orch.conductor.signals import StallWatch
from orch.conductor.domain.item import Item
from orch.conductor.domain.route import actor, label
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import write_json
from orch.conductor.infrastructure.heartbeat import observe_tick
from orch.conductor.infrastructure.launch_plan import claude_transcripts, strip_guard, transcript_folder_name  # noqa: F401 — re-export for callers
from orch.conductor.infrastructure import sessions
from orch.conductor.infrastructure.sessions import keep_session, resume_args  # noqa: F401 — re-export for callers
from orch.conductor.infrastructure.usage import add_tokens  # noqa: F401 — re-export for callers
from orch.conductor.progress import human_duration

DENIAL_NOTE_ROLES = ("executor", "bounded-implementer")  # roles whose report notes the tools denied without a prompt


class RolePorts(NamedTuple):
    """What a role needs from above the infrastructure, implemented there and passed down (the conductor builds it):
    the functions of infrastructure call these, never a binding of a higher layer through ``self``."""
    start_route: Optional[Callable] = None  # application.retry_service.start_route
    prompt_for_route: Optional[Callable] = None  # application.retry_service.prompt_for_route
    provider_failure: Optional[Callable] = None  # application.retry_service.provider_failure
    routed_blocks: Optional[Callable] = None  # application.retry_service.routed_blocks
    budget: Optional[Callable] = None  # application.budget_service.budget
    unmetered: Optional[Callable] = None  # application.budget_service.unmetered
    admit_budget: Optional[Callable] = None  # application.budget_service.admit
    stage_key: Optional[Callable] = None  # application.budget_service.stage_key
    stage_bucket: Optional[Callable] = None  # application.budget_service.stage_bucket
    remember_stage: Optional[Callable] = None  # application.budget_service.remember_stage
    provider_disabled: Optional[Callable] = None  # application.route_service.provider_disabled
    sandbox_args: Optional[Callable] = None  # application.route_service.sandbox_args
    knows: Optional[Callable] = None  # infrastructure.cli_probe.run_knows
    skills_excluded: Optional[Callable] = None  # stages.context.skills_excluded
    run_clock: Optional[Callable] = None  # the step-boundary run clock (stages.step.run_clock)


def agent_start(self, item: Item, key: str, role: str, route: dict, prompt_file: Path, attempt: int,
                causation: Optional[str] = None, prompt_sha256: Optional[str] = None,
                session: Optional[dict] = None) -> dict:
    """A new agent run (``agents``): its folder and ``request.json``. It becomes the agent of this thread, so that the
    usage of the process is counted to it and a role started inside it (the report-fixer) names it as its parent.
    ``session`` (``data.session`` of ``orch.agent.started``) says whether the executor attempt resumes a session and why."""
    number = self.store.next_agent(self.state)
    parent = getattr(self._local, "agent", None)
    handle = agents.start(item.directory, agents.agent_id(self.run_id, number), role=role, route=actor(route),
                          step=key, attempt=attempt, prompt=self._relative(prompt_file),
                          parent=parent["id"] if parent else None, started_at=clock.utc_now(), causation=causation)
    handle.update(began=time.monotonic(), previous=parent, last_exit=None, stream=None, lingered=False, trail={})
    self._local.agent = handle
    handle["event_base"] = {"run_id": item.orch_run, "work_id": item.input_doc.get("input_id") or item.ref,
                            "item": item.ref, "agent_run_id": handle["id"], "role": role, "step": key,
                            "attempt": attempt, "route": self._event_route(item, role, route),
                            "prompt_sha256": prompt_sha256,
                            "config_digest": settings_mod.config_digest(self.settings),
                            "options_digest": opts.digest(item.options) if item.options else None}
    handle["event_started"] = self._agent_event("orch.agent.started", handle, {"session": session} if session else None)
    return handle


def event_route(item: Item, role: str, route: dict) -> dict:
    """``{provider, model_class?, model?, effort?}`` of an agent route for its events."""
    model_class = opts.stage_route(item.options, role).get("model_class") or route.get("model_class")
    return {key: value for key, value in (("provider", route.get("provider")), ("model_class", model_class),
                                          ("model", route.get("model")), ("effort", route.get("effort"))) if value}


def agent_event(self, event_type: str, handle: dict, extra: Optional[dict] = None) -> Optional[str]:
    """Journal an ``orch.agent.*`` event of the agent run in ``handle``; the id of the event, ``None`` when none was
    journaled. ``agent.finished`` and ``agent.failed`` are caused by ``agent.started``; the run id correlates them."""
    base = handle["event_base"]
    data = {key: value for key, value in {**base, **(extra or {})}.items() if value is not None}
    return events.emit(event_type, data, subject=f"{base['run_id']}/{base['item']}/{handle['id']}",
                       causationid=handle.get("event_started") if event_type != "orch.agent.started" else None,
                       correlationid=base["run_id"], settings=self.settings, project=self.project,
                       config_file=self.config_file)


def agent_end(self, handle: dict, error: Optional[dict] = None, succeeded: bool = False) -> None:
    """The result of the agent run, whatever its end; the agent of the thread is the parent again. A run that went
    on after a failure of the provider and succeeded has no error: its ``decisions`` tell the repeat."""
    trail = handle["trail"]
    agents.finish(handle, exit_code=handle["last_exit"], error=None if succeeded else trail.get("error") or error,
                  decisions=trail.get("decisions") or [], duration_s=time.monotonic() - handle["began"],
                  stream=handle["stream"], lingered=handle["lingered"])
    failure = None if succeeded else trail.get("error") or error
    tokens = {key: value for key, value in handle["usage"].items() if value}
    extra = {"tokens": handle["usage"] if tokens else None, "duration_ms": round((time.monotonic() - handle["began"]) * 1000)}
    if failure:
        extra["error"] = {"class": failure.get("class") or "unknown",
                          **({"code": failure["code"]} if failure.get("code") else {})}
    self._agent_event("orch.agent.failed" if failure else "orch.agent.finished", handle, extra)
    self._local.agent = handle["previous"]


def run_role(self, item: Item, key: str, role: str, blocks: list, kind: Optional[str],
             extra: Optional[Callable[[dict], list]] = None, cancel=None, causation: Optional[str] = None,
             resumed: Optional[list] = None) -> tuple:
    """``(result, meta)`` of a role as an agent run: the body is :meth:`_role_body`; the run gets its folder under
    ``agents/`` and its result however the role ends, and ``meta`` names it (``agent``). The prompt is the ``blocks``
    rendered; ``prompts/<key>.manifest.json`` (``prompt-manifest/v1``) says what each block is and where it came from.
    ``resumed`` is the delta prompt of the same round (blocks): it is sent instead of ``blocks`` when the attempt continues
    a session that already holds the task (``_delta_mode``); the full prompt is the fallback of every other attempt."""
    prompt = prompts.render(blocks)
    if role == "executor" and not item.state.get("executor_started"):
        item.state["executor_started"] = True  # from here on the piece has work in the tree, whatever the round ends with
        self._save()
    prompt_file = item.directory / "prompts" / f"{key}.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    limits = {name: int(item.options.get("limits", {}).get(option, opts.DEFAULT_LIMITS[option]))
              for name, option in prompts.BUDGET_LIMITS.items()}
    write_json(prompt_file.with_name(f"{key}.manifest.json"),
               prompts.manifest(blocks, step=key, role=role, route=item.routes[role],
                                excluded=self.role_ports.skills_excluded(item, role), limits=limits))
    for _name, block, _tokens, _limit in prompts.over_budget(blocks, limits):  # a beacon: the prompt is not cut
        self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="BUDGET_OVER",
                           message=f"block {block.kind} {block.origin} {prompts.estimate_tokens(block.text)}")
    attempt = item.state.get("retries_by_stage", {}).get(key, 0) + 1
    # The route the role starts on (a provider gated since the routes were chosen moves to its fallback) and the prompt
    # rebuilt for it come first: orch.agent.started names the route and the digest of the prompt really sent.
    route = self.role_ports.start_route(item, key, role, item.routes[role], cancel)
    delta, digest, _resuming, decision = self._delta_mode(item, key, role, route, blocks, resumed)
    _first, prompt = self.role_ports.prompt_for_route(item, key, role, route, blocks, prompt, prompt,
                                                      resumed=resumed if delta else None, digest=digest)
    handle = self._agent_start(item, key, role, route, prompt_file, attempt, causation,
                               prompt_sha256=sha256_hex(prompt.encode("utf-8")), session=sessions.event_data(decision))
    try:
        doc, meta = self._role_body(item, key, role, prompt, kind, extra, cancel, handle, blocks, resumed)
    except Stop as stop:
        self._agent_end(handle, {"code": stop.code, "message": stop.message})
        raise
    except BaseException as error:  # an interrupt or a crash still leaves the record of the run
        self._agent_end(handle, {"code": type(error).__name__, "message": str(error)[:300] or type(error).__name__})
        raise
    self._agent_end(handle, succeeded=True)
    return doc, {**meta, "agent": handle["id"]}


def denied(denials: list) -> str:
    """``Bash×2, Grep``: the tools of the refused calls with their counts, most refused first."""
    counts: dict = {}
    for entry in denials:
        counts[entry["tool_name"]] = counts.get(entry["tool_name"], 0) + 1
    return ", ".join(name if number == 1 else f"{name}×{number}"
                     for name, number in sorted(counts.items(), key=lambda row: (-row[1], row[0])))


def role_body(self, item: Item, key: str, role: str, prompt: str, kind: Optional[str],
              extra: Optional[Callable[[dict], list]], cancel, handle: dict, blocks: list,
              resumed: Optional[list] = None) -> tuple:
    """``(result, meta)`` of a role: its closed document (or text when ``kind`` is None).

    A result outside its contract is first healed by rule (``heal``), then repaired by the report-fixer role from
    the role's own answer (``limits.repairs``), and only then is the whole role repeated (``limits.retries`` per
    step): a repeat costs a whole run of the role, a repair seconds. A role that failed at the provider (it exited
    with an error, or its stream ended in one) is not told its answer was rejected: ``retry.decide`` chooses between
    a repeat, a wait for the reset, another route and a stop (``_provider_failure``).

    Each attempt decides again whether it sends the delta prompt (``resumed``) or the whole one (``_delta_mode``): an
    attempt that continued a session and lost it (an error, no session) leaves the next attempt the whole prompt in a fresh
    session (``SESSION_RESUME_FAILED``)."""
    route = item.routes[role]
    (item.directory / "prompts").mkdir(parents=True, exist_ok=True)
    (item.directory / "prompts" / f"{key}.md").write_text(prompts.render(blocks), encoding="utf-8")  # the full prompt
    attempt = 0
    first_prompt = prompt
    trail = handle["trail"] = {"decisions": [], "error": None, "api_retries": 0, "denials": []}
    base = self._tree_mark() if self._writes(role) else None  # the tree this step started from
    route = self.role_ports.start_route(item, key, role, route, cancel)
    while True:
        self.role_ports.admit_budget(item, "attempt")  # before every provider call: a repeat, a fallback, a wait (I10)
        delta, digest, resuming, decision = self._delta_mode(item, key, role, route, blocks, resumed)
        self._announce_session(item, key, role, route, decision)
        first_prompt, prompt = self.role_ports.prompt_for_route(item, key, role, route, blocks, first_prompt, prompt,
                                                                resumed=resumed if delta else None, digest=digest)
        attempt += 1
        suffix = "" if attempt == 1 else f"-a{attempt}"
        raw = item.directory / "streams" / f"{key}{suffix}.{'txt' if route['transport'] == 'text' else 'jsonl'}"
        run = process.run_role(self._role_argv(item, role, route, decision), prompt, transport=route["transport"], cwd=self.project,
                               timeout_s=route["timeout_s"], raw_path=raw, env=self._role_env(item, role, route),
                               idle_timeout_s=route.get("idle_timeout_s", 0), cancel=cancel,
                               on_tick=self._beacons(item, key, role, raw), provider=route["provider"],
                               agent_directory=handle["directory"])
        self._tokens(item, run.usage, usage_complete=run.usage_complete, attempt=self._relative(raw))
        self._keep_session(item, role, route, run, task_digest=digest, delta=delta, decision=decision)
        if resuming and (run.error or not run.session):  # the next attempt starts a fresh session with the whole prompt
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=label(route),
                               reason_code="SESSION_RESUME_FAILED",
                               message=f"the session of {item.ref} could not be continued on {route['provider']} "
                                       f"({run.error or 'no session returned'}); the next attempt starts a fresh session "
                                       "with the whole prompt")
        trail["api_retries"] += run.api_retries
        handle.update(last_exit=run.exit, stream=self._relative(raw), lingered=handle["lingered"] or run.lingered)
        if run.denials:  # a tool call refused without a prompt: the role could not do what it meant to
            trail["denials"] += run.denials
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=label(route),
                               reason_code="RESULT_SILENT_DENIAL", agent=handle["id"],
                               message=f"{self._denied(run.denials)} denied without a prompt")
        if run.lingered:
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=label(route),
                               reason_code="ROLE_LINGERED",
                               message=f"the answer was complete; the process was still alive {process.RESULT_GRACE_S} s later "
                                       "(a background task of the provider) and was stopped")
        if run.error == "CANCELLED":
            raise Stop("REVIEW_CANCELLED", f"{role} on {label(route)} was cancelled: the checks are red")
        if run.error in ("PROVIDER_UNAVAILABLE", "TRANSPORT_UNSUPPORTED"):
            raise Stop(run.error, f"{role} on {route['provider']}: {run.detail}")
        problem = f"{run.error}: {run.detail}" if run.error else None
        doc, healed, repaired, from_text = None, [], None, False
        if problem is None and kind:
            doc, healed, issues, original = self._closed(run.text, kind, extra)
            if issues:
                doc, healed, issues, repaired, from_text = self._repair(item, key, kind, extra, run.text, issues, doc,
                                                                        healed, original)
            if issues:
                problem = f"ROLE_OUTPUT_INVALID: {'; '.join(issues[:3])}"
        meta = {"session": run.session, "model": run.model, "stream": self._relative(raw), "attempts": attempt,
                "exit": run.exit, "usage": run.usage,
                **({"healed": healed} if healed else {}), **({"repaired_by": repaired} if repaired else {}),
                **({"repaired_from_text": True} if repaired and from_text else {}),
                **({"error": trail["error"]} if trail["error"] else {}),
                **({"api_retries": trail["api_retries"]} if trail["api_retries"] else {}),
                **({"decisions": trail["decisions"]} if trail["decisions"] else {})}
        if problem is None:
            if healed:
                self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="RESULT_HEALED",
                                   message="; ".join(healed))
            if trail["denials"] and kind == "stage-report" and role in DENIAL_NOTE_ROLES:
                doc = dict(doc, open_issues=list(doc.get("open_issues") or []) + [
                    {"text": f"tools denied without a prompt: {self._denied(trail['denials'])}"[:900], "kind": "note",
                     "impact": "the role could not use them",
                     "next": "widen allowedTools in the launch catalog or change the plan"}])
            return (doc if kind else run.text), meta
        item.state["retries_used"] = item.state.get("retries_used", 0) + 1  # the total of the piece, for the report
        by_stage = item.state.setdefault("retries_by_stage", {})
        by_stage[key] = by_stage.get(key, 0) + 1
        self._save()
        self.role_ports.budget(item)
        if run.error:  # the role itself failed: a provider failure is decided, not judged as an answer
            route, prompt = self.role_ports.provider_failure(item, key, role, route, run, by_stage[key], base,
                                                             first_prompt, trail, cancel)
            continue
        if by_stage[key] > item.options["limits"]["retries"]:  # a stage has its own repeats: a slow executor must not cost the review its only one
            raise Stop(problem.split(":", 1)[0], f"{role} on {label(route)}: {problem}")
        self.progress.emit("info", item=item.ref, stage=key, role=role, route=label(route),
                           message=f"attempt {attempt} failed ({problem}); repeating")
        prompt = (f"{first_prompt}\n\n# Your previous answer was rejected\n\n{problem}\n\n"
                  "Do the work again as needed and end with one corrected block that fits the contract exactly.\n")


def beacons(self, item: Item, key: str, role: str, raw: Path) -> Callable:
    """The tick of a running role: a STAGE_SLOW beacon every ``stage_warn_s`` and a STAGE_IDLE one every
    ``stage_idle_warn_s`` of silence, each saying what the role runs now, a STALL_SUSPECTED one for a repeated command or a
    stream without tool steps, and a heartbeat of the run. Nothing is stopped."""
    limits = item.options["limits"]
    route = item.routes.get(role) or {}
    stall = StallWatch(limits.get("stall_repeat_n", 0), limits.get("stall_window_s", 0),
                       steps=bool(process.markers_of(route.get("transport", ""), route.get("provider"))))
    warn, idle_warn = limits.get("stage_warn_s", 0), limits.get("stage_idle_warn_s", 0)
    marks = {"slow": warn, "idle": idle_warn}
    current = getattr(self._local, "agent", None)
    agent = current["id"] if current else None

    def tick(elapsed: float, idle: float, pid: int, info: process.TickInfo) -> None:
        self.role_ports.run_clock(item)
        for reason in observe_tick(self, stall, elapsed, info, item=item.ref, step=key, role=role):
            self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STALL_SUSPECTED", agent=agent,
                               message=f"{reason}; {process.activity(pid, raw)}")
        if warn and elapsed >= marks["slow"]:
            marks["slow"] += warn
            self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STAGE_SLOW", agent=agent,
                               message=f"running {human_duration(elapsed)}; {process.activity(pid, raw)}")
        if idle_warn:
            if idle < idle_warn:
                marks["idle"] = idle_warn
            elif idle >= marks["idle"]:
                marks["idle"] += idle_warn
                self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STAGE_IDLE", agent=agent,
                                   message=f"no output for {human_duration(idle)} (running {human_duration(elapsed)}); "
                                           f"{process.activity(pid, raw)}")
    return tick


def relative(self, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(self.project).as_posix()
    except ValueError:
        return str(path)
