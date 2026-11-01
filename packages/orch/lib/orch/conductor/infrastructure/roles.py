"""A role as a process and an agent run: its prompt and manifest, the call of the provider and its repeats, and the
beacons of a long or silent run. The launch plan, the session, the usage ledger, the result and the tree a role works
in are their own modules; what the role needs from the layers above comes in :class:`RolePorts`."""
from __future__ import annotations

import contextlib
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
from orch.conductor.infrastructure import beacon_events, clock, detach, launch_budget, launch_plan, results, sessions
from orch.conductor.policies import authority as authority_rules
from orch.conductor.infrastructure.files import write_json
from orch.conductor.infrastructure.heartbeat import observe_tick
from orch.conductor.infrastructure.launch_plan import claude_transcripts, strip_guard, transcript_folder_name  # noqa: F401 — re-export for callers
from orch.conductor.infrastructure.sessions import keep_session, resume_args  # noqa: F401 — re-export for callers
from orch.conductor.infrastructure.usage import add_tokens  # noqa: F401 — re-export for callers
from orch.conductor.progress import human_duration

# roles whose result notes the tools denied without a prompt: a writer's stage report (open_issues), the reviewer's
# findings (residual_risk, read by the triager)
DENIAL_NOTE_ROLES = ("executor", "bounded-implementer", "reviewer")


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
    launch_facts: Optional[Callable] = None  # application.route_service.launch_facts
    knows: Optional[Callable] = None  # application.route_service.knows (ISOLATION_PARTIAL once per run)
    note_isolation: Optional[Callable] = None  # application.route_service.note_plan
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
    (handle["directory"] / "tmp").mkdir(mode=0o700, exist_ok=True)
    self._local.agent = handle
    handle["event_base"] = {"run_id": item.orch_run, "work_id": item.input_doc.get("input_id") or item.ref,
                            "item": item.ref, "agent_run_id": handle["id"], "role": role, "step": key,
                            "attempt": attempt, "route": self._event_route(item, role, route),
                            "prompt_sha256": prompt_sha256,
                            "config_digest": settings_mod.config_digest(self.settings),
                            "options_digest": opts.digest(item.options) if item.options else None}
    handle["event_started"] = self._agent_event("orch.agent.started", handle, {"session": session} if session else None)
    return handle


def launch(self, item: Item, handle: dict, role: str, route: dict, prompt: str, *, attempt: int, raw: Path,
           timeout_s: int, decision: Optional[dict] = None, clean_env: bool = False, **run_kwargs):
    """The one start of a provider process in the conductor (the attempts and fallbacks of a role, the report-fixer, the
    batch roles): the authority envelope of this attempt's route (``launch_plan.authority``, which refuses a role
    ``instructions.isolation = require`` does not admit) is written to ``agents/<id>/authority/a<attempt>.json`` of the
    agent run in ``handle``, kept as the authority of the role in the piece (``AUTHORITY_CHANGED`` when it differs from
    its last launch), and the command line and the environment are built from it; ``clean_env`` drops the launch
    authority of the conductor from the environment (``detach.subprocess_env``). The record is written before the
    process: a crash between the two leaves the record of a launch that did not happen, never a launch without one. The
    command the attempt really runs (a catalog ``resume_argv`` when it continues a session) must have the authority of
    the record: else ``AUTHORITY_RESUME_MISMATCH`` before anything is written."""
    envelope = self._authority(item, role, route)
    resume = sessions.resume_args(self, item, role, route, decision) if role == "executor" else []  # only it resumes
    refused = launch_plan.resume_problem(self, item, role, route, resume, envelope)
    if refused:
        raise Stop("AUTHORITY_RESUME_MISMATCH", refused)
    if launch_budget.latest(item):
        with self.store.mutating():
            launch_budget.record_launch(self, item, handle, role, route, attempt, envelope)
    else:
        agents.write_authority(handle, attempt, envelope)
    note_authority(self, item, role, route, envelope)
    env = self._role_env(item, role, route)
    run = process.run_role(self._role_argv(item, role, route, decision, envelope=envelope, resume=resume), prompt,
                            transport=route["transport"], cwd=self.project, timeout_s=timeout_s, raw_path=raw,
                            env=detach.subprocess_env(env) if clean_env else env, agent_directory=handle["directory"],
                             guard=envelope["guard"],
                            **run_kwargs)
    results.observe_denials(handle, run.env_denials)
    return run


def note_authority(self, item: Item, role: str, route: dict, envelope: dict) -> None:
    """``item.state.authority[role]``: the digest of the last launch of ``role`` in the piece, saved under the lock of
    the run store (I2). A digest that differs from the one before is the info ``AUTHORITY_CHANGED`` with the keys that
    changed (known while the conductor keeps the earlier envelope in memory)."""
    known = self.__dict__.setdefault("_authority_seen", {})
    store = getattr(self, "store", None)
    with store.mutating() if store is not None else contextlib.nullcontext():
        kept = item.state.setdefault("authority", {})
        before = kept.get(role)
        if before == envelope["digest"]:
            known[(item.ref, role)] = envelope
            return
        kept[role] = envelope["digest"]
        if store is not None:
            self._save()
    earlier = known.get((item.ref, role))
    known[(item.ref, role)] = envelope
    if before is None or getattr(self, "progress", None) is None:
        return
    keys = authority_rules.changed_keys(earlier, envelope) if earlier and earlier["digest"] == before else []
    self.progress.emit("info", item=item.ref, role=role, route=label(route), reason_code="AUTHORITY_CHANGED",
                       message=f"{item.ref} {role}: authority {short(before)} -> {short(envelope['digest'])} "
                               f"({', '.join(keys) if keys else 'keys not known: the earlier envelope is on disk only'})")


def short(digest: str) -> str:
    """The first 12 hex digits of a ``sha256:`` digest."""
    return digest.split(":", 1)[-1][:12]


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
                  stream=handle["stream"], lingered=handle["lingered"], isolation=handle.get("isolation"))
    for role, step, counts in results.denial_beacons(handle):
        self.progress.emit("info", item=handle.get("event_base", {}).get("item"), role=role,
                           stage=step, reason_code="RESULT_ENV_DENIAL",
                           message=f"{role} {step}: " + ", ".join(
                               f"{kind}×{number}" for kind, number in sorted(counts.items())))
    failure = None if succeeded else trail.get("error") or error
    tokens = {key: value for key, value in handle["usage"].items() if value}
    extra = {"tokens": handle["usage"] if tokens else None, "duration_ms": round((time.monotonic() - handle["began"]) * 1000),
             "authority_digests": [entry["digest"] for entry in handle.get("authority") or []] or None}
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
    """``Bash×2 (python3, cat+heredoc), Read (lib/x.py)``: the tools of the refused calls with their counts, most refused
    first, and the safe hints of the calls (what was run or read) when the stream gave them."""
    counts: dict = {}
    hints: dict = {}
    for entry in denials:
        counts[entry["tool_name"]] = counts.get(entry["tool_name"], 0) + 1
        hint = entry.get("hint")
        if hint and hint not in hints.setdefault(entry["tool_name"], []):
            hints[entry["tool_name"]].append(hint)

    def shown(name: str, number: int) -> str:
        said = name if number == 1 else f"{name}×{number}"
        return f"{said} ({', '.join(hints[name][:3])})" if hints.get(name) else said
    return ", ".join(shown(name, number) for name, number in sorted(counts.items(), key=lambda row: (-row[1], row[0])))


def expected_denial(role: str, denials: list) -> bool:
    """A role whose manifest gives it a read-only shell is meant to be refused what is not a plain read: when every
    refused call is Bash, the denial is the design working, not a role that could not do its job."""
    return launch_plan.shell(role) == "read_only" and all(entry["tool_name"] == "Bash" for entry in denials)


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
        # the launch refuses a role that instructions.isolation = require does not admit (ISOLATION_UNAVAILABLE)
        run = self._launch(item, handle, role, route, prompt, attempt=attempt, raw=raw, timeout_s=route["timeout_s"],
                           decision=decision, clean_env=True, idle_timeout_s=route.get("idle_timeout_s", 0),
                           cancel=cancel, on_tick=self._beacons(item, key, role, raw), provider=route["provider"])
        self._tokens(item, run.usage, usage_complete=run.usage_complete, attempt=self._relative(raw))
        results.observe_isolation(self, item, key, role, route, run.init, handle)
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
                               message=f"{self._denied(run.denials)} denied without a prompt"
                                       + ("; expected for a read-only shell" if expected_denial(role, run.denials) else ""))
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
            if trail["denials"] and kind == "review-findings" and role in DENIAL_NOTE_ROLES:
                # the triager reads the whole findings document: it learns that what the reviewer meant to run was not run
                note = (f"not verified by running: {self._denied(trail['denials'])} denied without a prompt; "
                        "reproductions the reviewer meant to run are static, reproduce them before judging")[:900]
                findings: dict = dict(doc or {})
                risk = str(findings.get("residual_risk") or "")
                findings["residual_risk"] = "; ".join(part for part in (risk, note) if part)
                doc = findings
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
    """Tick of a role: STAGE_SLOW/STAGE_IDLE at their warning intervals, STALL_SUSPECTED on stalls; heartbeat, never stop."""
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
                               message=f"{reason}; {process.activity(pid, raw, idle, info)}")
            beacon_events.beacon_event(self, "orch.run.warning", item, {"reason_code": "STALL_SUSPECTED", "step": key})
        if warn and elapsed >= marks["slow"]:
            marks["slow"] += warn
            self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STAGE_SLOW", agent=agent,
                               message=f"running {human_duration(elapsed)}; {process.activity(pid, raw, idle, info)}")
            beacon_events.beacon_event(self, "orch.run.warning", item, {"reason_code": "STAGE_SLOW", "step": key})
        if idle_warn:
            if idle < idle_warn:
                marks["idle"] = idle_warn
            elif idle >= marks["idle"]:
                marks["idle"] += idle_warn
                self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STAGE_IDLE", agent=agent,
                                   message=f"no output for {human_duration(idle)} (running {human_duration(elapsed)}); "
                                           f"{process.activity(pid, raw, None, info)}")
                beacon_events.beacon_event(self, "orch.run.warning", item, {"reason_code": "STAGE_IDLE", "step": key})
    return tick


def relative(self, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(self.project).as_posix()
    except ValueError:
        return str(path)
