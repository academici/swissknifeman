"""A role as a process and an agent run: its prompt and manifest, the command line and environment of the provider,
the repair of a result outside its contract, the tokens it used and the beacons of a long or silent run."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Callable, Optional

from aicore.util.digest import sha256_hex

from orch import events, settings as settings_mod
from orch.conductor import agents, checks as checks_mod, contract, heal, options as opts, process, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain.report import json_block
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import write_json
from orch.conductor.progress import human_duration
from orch.settings import ORCH_ROOT

DENIAL_NOTE_ROLES = ("executor", "bounded-implementer")  # roles whose report notes the tools denied without a prompt

# The environment that keeps a provider's project instructions (the repository CLAUDE.md, the project memory) out of
# a role process. Claude Code reads both by itself; grok was probed and does not read the repository CLAUDE.md; codex
# would need its own CODEX_HOME (not used by a run so far).
ISOLATION_ENV = {"claude-code": {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}}

# Arguments that start a role with no customizations at all: no CLAUDE.md, project memory, plugins, MCP servers, user
# skills or hooks (a measured start-up context of 6 K instead of 16 K tokens, and none of the developer-session rules).
ISOLATION_ARGS = {"claude-code": ["--safe-mode"]}


def agent_start(self, item: Item, key: str, role: str, route: dict, prompt_file: Path, attempt: int,
                causation: Optional[str] = None, prompt_sha256: Optional[str] = None) -> dict:
    """A new agent run (``agents``): its folder and ``request.json``. It becomes the agent of this thread, so that the
    usage of the process is counted to it and a role started inside it (the report-fixer) names it as its parent."""
    number = self.store.next_agent(self.state)
    parent = getattr(self._local, "agent", None)
    handle = agents.start(item.directory, agents.agent_id(self.run_id, number), role=role, route=self._actor(route),
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
    handle["event_started"] = self._agent_event("orch.agent.started", handle)
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
             extra: Optional[Callable[[dict], list]] = None, cancel=None, causation: Optional[str] = None) -> tuple:
    """``(result, meta)`` of a role as an agent run: the body is :meth:`_role_body`; the run gets its folder under
    ``agents/`` and its result however the role ends, and ``meta`` names it (``agent``). The prompt is the ``blocks``
    rendered; ``prompts/<key>.manifest.json`` (``prompt-manifest/v1``) says what each block is and where it came from."""
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
                                excluded=self._skills_excluded(item, role), limits=limits))
    for _name, block, _tokens, _limit in prompts.over_budget(blocks, limits):  # a beacon: the prompt is not cut
        self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="BUDGET_OVER",
                           message=f"block {block.kind} {block.origin} {prompts.estimate_tokens(block.text)}")
    attempt = item.state.get("retries_by_stage", {}).get(key, 0) + 1
    handle = self._agent_start(item, key, role, item.routes[role], prompt_file, attempt, causation,
                               prompt_sha256=sha256_hex(prompt.encode("utf-8")))
    try:
        doc, meta = self._role_body(item, key, role, prompt, kind, extra, cancel, handle)
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
              extra: Optional[Callable[[dict], list]], cancel, handle: dict) -> tuple:
    """``(result, meta)`` of a role: its closed document (or text when ``kind`` is None).

    A result outside its contract is first healed by rule (``heal``), then repaired by the report-fixer role from
    the role's own answer (``limits.repairs``), and only then is the whole role repeated (``limits.retries`` per
    step): a repeat costs a whole run of the role, a repair seconds. A role that failed at the provider (it exited
    with an error, or its stream ended in one) is not told its answer was rejected: ``retry.decide`` chooses between
    a repeat, a wait for the reset, another route and a stop (``_provider_failure``)."""
    route = item.routes[role]
    (item.directory / "prompts").mkdir(parents=True, exist_ok=True)
    (item.directory / "prompts" / f"{key}.md").write_text(prompt, encoding="utf-8")
    attempt = 0
    first_prompt = prompt
    trail = handle["trail"] = {"decisions": [], "error": None, "api_retries": 0, "denials": []}
    base = self._tree_mark() if self._writes(role) else None  # the tree this step started from
    route = self._start_route(item, key, role, route, cancel)
    while True:
        attempt += 1
        suffix = "" if attempt == 1 else f"-a{attempt}"
        raw = item.directory / "streams" / f"{key}{suffix}.{'txt' if route['transport'] == 'text' else 'jsonl'}"
        run = process.run_role(self._role_argv(item, role, route), prompt, transport=route["transport"], cwd=self.project,
                               timeout_s=route["timeout_s"], raw_path=raw, env=self._role_env(item, role, route),
                               idle_timeout_s=route.get("idle_timeout_s", 0), cancel=cancel,
                               on_tick=self._beacons(item, key, role, raw), provider=route["provider"])
        self._tokens(item, run.usage)
        self._keep_session(item, role, route, run)
        trail["api_retries"] += run.api_retries
        handle.update(last_exit=run.exit, stream=self._relative(raw), lingered=handle["lingered"] or run.lingered)
        if run.denials:  # a tool call refused without a prompt: the role could not do what it meant to
            trail["denials"] += run.denials
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(route),
                               reason_code="RESULT_SILENT_DENIAL", agent=handle["id"],
                               message=f"{self._denied(run.denials)} denied without a prompt")
        if run.lingered:
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(route),
                               reason_code="ROLE_LINGERED",
                               message=f"the answer was complete; the process was still alive {process.RESULT_GRACE_S} s later "
                                       "(a background task of the provider) and was stopped")
        if run.error == "CANCELLED":
            raise Stop("REVIEW_CANCELLED", f"{role} on {self.label(route)} was cancelled: the checks are red")
        if run.error in ("PROVIDER_UNAVAILABLE", "TRANSPORT_UNSUPPORTED"):
            raise Stop(run.error, f"{role} on {route['provider']}: {run.detail}")
        problem = f"{run.error}: {run.detail}" if run.error else None
        doc, healed, repaired = None, [], None
        if problem is None and kind:
            doc, healed, issues = self._closed(run.text, kind, extra)
            if issues:
                doc, healed, issues, repaired = self._repair(item, key, kind, extra, run.text, issues, doc, healed)
            if issues:
                problem = f"ROLE_OUTPUT_INVALID: {'; '.join(issues[:3])}"
        meta = {"session": run.session, "model": run.model, "stream": self._relative(raw), "attempts": attempt,
                "exit": run.exit, "usage": run.usage,
                **({"healed": healed} if healed else {}), **({"repaired_by": repaired} if repaired else {}),
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
        self._budget(item)
        if run.error:  # the role itself failed: a provider failure is decided, not judged as an answer
            route, prompt = self._provider_failure(item, key, role, route, run, by_stage[key], base, first_prompt,
                                                   trail, cancel)
            continue
        if by_stage[key] > item.options["limits"]["retries"]:  # a stage has its own repeats: a slow executor must not cost the review its only one
            raise Stop(problem.split(":", 1)[0], f"{role} on {self.label(route)}: {problem}")
        self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(route),
                           message=f"attempt {attempt} failed ({problem}); repeating")
        prompt = (f"{first_prompt}\n\n# Your previous answer was rejected\n\n{problem}\n\n"
                  "Do the work again as needed and end with one corrected block that fits the contract exactly.\n")


def closed(text: str, kind: str, extra) -> tuple:
    """``(document, healed, issues)`` of the result block in ``text``."""
    doc, error = json_block(text, kind)
    if error:
        return None, [], [error]
    doc, healed = heal.heal(kind, doc)
    if kind == "stage-report" and healed:
        doc = dict(doc, open_issues=list(doc.get("open_issues") or []) + [
            {"text": ("the conductor mended the form of this report: " + "; ".join(healed))[:900], "kind": "note",
             "impact": "none", "next": "none"}])
    issues = contract.problems(doc, kind)
    if not issues and extra:
        issues = extra(doc)
    return doc, healed, issues


def repair(self, item: Item, key: str, kind: str, extra, answer: str, issues: list, doc, healed) -> tuple:
    """The report-fixer rewrites the result block from the role's own answer; ``(doc, healed, issues, route)``."""
    if item.options["limits"]["repairs"] <= 0 or "report-fixer" not in item.routes:
        return doc, healed, issues, None
    route = item.routes["report-fixer"]
    if self.provider_disabled(route["provider"]) or not process.available(route["argv"]):
        return doc, healed, issues, None
    for number in range(1, item.options["limits"]["repairs"] + 1):
        problem = "; ".join(issues[:5])
        prompt = prompts.render(prompts.report_fixer(kind=kind, problem=problem, answer=answer, item=item.ref, step=key))
        raw = item.directory / "streams" / f"{key}-fix{number}.jsonl"
        prompt_file = item.directory / "prompts" / f"{key}-fix{number}.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        handle = self._agent_start(item, key, "report-fixer", route, prompt_file, number,
                                  prompt_sha256=sha256_hex(prompt.encode("utf-8")))  # the parent is the role mended
        try:
            run = process.run_role(self._role_argv(item, "report-fixer", route), prompt, transport=route["transport"],
                                   cwd=self.project, timeout_s=route["timeout_s"], raw_path=raw,
                                   env=self._role_env(item, "report-fixer", route))
            self._tokens(item, run.usage)
            handle.update(last_exit=run.exit, stream=self._relative(raw), lingered=run.lingered)
        except BaseException as error:
            self._agent_end(handle, {"code": type(error).__name__, "message": str(error)[:300] or type(error).__name__})
            raise
        self._agent_end(handle, {"code": run.error, "message": run.detail or run.error} if run.error else None)
        if run.error:
            self.progress.emit("info", item=item.ref, stage=key, role="report-fixer", route=self.label(route),
                               reason_code="REPAIR_FAILED", message=f"{run.error}: {run.detail}")
            return doc, healed, issues, None
        fixed, fixed_healed, fixed_issues = self._closed(run.text, kind, extra)
        self.progress.emit("info", item=item.ref, stage=key, role="report-fixer", route=self.label(route),
                           reason_code="RESULT_REPAIRED" if not fixed_issues else "REPAIR_FAILED",
                           message=f"was: {problem}" + (f"; still: {'; '.join(fixed_issues[:2])}" if fixed_issues else ""))
        if not fixed_issues:
            return fixed, healed + fixed_healed + [f"repaired by {self.label(route)}: {problem}"[:300]], [], self.label(route)
        issues = fixed_issues
    return doc, healed, issues, None


def beacons(self, item: Item, key: str, role: str, raw: Path) -> Callable:
    """The tick of a running role: a STAGE_SLOW beacon every ``stage_warn_s`` and a STAGE_IDLE one every
    ``stage_idle_warn_s`` of silence, each saying what the role runs now. Nothing is stopped."""
    limits = item.options["limits"]
    warn, idle_warn = limits.get("stage_warn_s", 0), limits.get("stage_idle_warn_s", 0)
    marks = {"slow": warn, "idle": idle_warn}
    current = getattr(self._local, "agent", None)
    agent = current["id"] if current else None

    def tick(elapsed: float, idle: float, pid: int) -> None:
        self._run_clock(item)
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


def add_tokens(self, item: Item, usage: dict) -> None:
    handle = getattr(self._local, "agent", None)
    if handle is not None:
        agents.add_usage(handle, usage)
    for bucket in (self.state.setdefault("tokens", {"input": 0, "output": 0}),
                   item.state.setdefault("tokens", {"input": 0, "output": 0}), self._step_tokens):
        for key in ("input", "cached", "output"):
            bucket[key] = bucket.get(key, 0) + int(usage.get(key, 0))


def relative(self, path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(self.project).as_posix()
    except ValueError:
        return str(path)


def writes(role: str) -> bool:
    """Whether the role may change files (``tools.filesystem`` of its manifest); a role without a manifest might."""
    try:
        manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return (manifest.get("tools") or {}).get("filesystem") == "write"


def tree_mark(self) -> str:
    """HEAD and the content of every changed path of the tree: what a failed attempt of a writing role can be
    compared with (the conductor reports are not the role's)."""
    try:
        head = checks_mod.head(self.project)
    except RuntimeError:  # no commit yet
        head = "-"
    parts = [head]
    for path in self._dirty_paths():
        file = self.project / path
        try:
            parts.append(path + ":" + sha256_hex(file.read_bytes() if file.is_file() else b"-"))
        except OSError:
            parts.append(path + ":?")
    return sha256_hex("\n".join(parts).encode("utf-8"))


def continuation(self, item: Item) -> str:
    """The section that turns a repeat of a writing role into a continuation: what is in the tree, what was checked."""
    head = checks_mod.head(self.project)
    status = checks_mod.git(self.project, "status", "--short").strip() or "(clean)"
    stat = checks_mod.git(self.project, "diff", "--stat", "HEAD").strip() or "(no change in tracked files)"
    closed = [f"{name}: {step.get('verdict', 'done')}" for name, step in (item.state.get("steps") or {}).items()
              if name.startswith("checks.") and step.get("status") == "done"]
    return ("\n\n# The previous attempt failed and left changes\n\n"
            "The previous attempt of this step ended with a failure of the provider, not with an answer. Its changes are "
            "still in the working tree and are yours: read them, keep what is right, finish the rest, and end with the "
            "closed block the contract asks for. Do not discard them and do not start over.\n\n"
            f"Base commit: {head}\n\n```\n$ git status --short\n{status}\n\n$ git diff --stat HEAD\n{stat}\n```\n\n"
            f"Checks closed before this step: {', '.join(closed) if closed else 'none'}.\n")


def role_argv(self, item: Item, role: str, route: dict) -> list:
    isolated = role in item.options["instructions"]["isolate_roles"]
    extra = ISOLATION_ARGS.get(route.get("provider")) if isolated else None
    if extra and not self._knows(route["argv"], extra):
        extra = None
    argv = list(route["argv"])
    if self._shared_session(item, role, route):  # a session that is not saved cannot be resumed by the next executor
        argv = [arg for arg in argv if arg != "--no-session-persistence"]
    argv = self._extra_write_dirs(item, role, argv)
    return argv + (extra or []) + self._resume_args(item, role, route) + self._sandbox_args(item, role, route)


def extra_write_dirs(self, item: Item, role: str, argv: list) -> list:
    """``scope.extra_paths`` for an executor started through ``ro-run.py``: one more ``--rw`` each, before the ``--``."""
    paths = list(self._scope_option(item, "extra_paths", []))
    if role != "executor" or "--" not in argv or not any(a.endswith("ro-run.py") for a in argv[:2]):
        return argv
    if self._shared_session(item, role, {"provider": "claude-code"}) and "claude" in argv[argv.index("--") + 1:][:1]:
        paths.append(self._claude_transcripts())  # else the guard stops the CLI from saving the session it must resume
    if not paths:
        return argv
    at = argv.index("--")
    return argv[:at] + [part for path in paths for part in ("--rw", os.path.expanduser(path))] + argv[at:]


TRANSCRIPT_NAME_MAX = 200  # Claude Code shortens a longer folder name and appends a hash it does not publish


def transcript_folder_name(project) -> str:
    """The folder name Claude Code gives a project: every UTF-16 code unit outside [A-Za-z0-9] becomes ``-`` (a character
    outside the basic plane is two units, so two dashes)."""
    return "".join(char if char.isascii() and char.isalnum() else "-" * (2 if ord(char) > 0xFFFF else 1) for char in str(project))


def claude_transcripts(self) -> str:
    """The folder where Claude Code keeps the transcripts of this project: ``~/.claude/projects/<path with every
    character outside [A-Za-z0-9] as -``. It is the one place besides the project that a resumable session needs. A
    path whose folder name would pass ``TRANSCRIPT_NAME_MAX`` gets a name with a hash suffix that is not known here: the
    whole ``~/.claude/projects`` is then writable for the executor (the transcripts of the other projects too)."""
    root = Path.home() / ".claude" / "projects"
    name = transcript_folder_name(self.project)
    folder = root if len(name) > TRANSCRIPT_NAME_MAX else root / name
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)


def scope_option(item: Item, key: str, default):
    return (item.options.get("scope") or {}).get(key, default)


def session_mode(item: Item) -> str:
    return (item.options.get("session") or {}).get("executor", "shared")


def shared_session(self, item: Item, role: str, route: dict) -> bool:
    """The executor of this run keeps one provider session across its pieces and correction rounds (``session.executor``)."""
    return role == "executor" and route.get("provider") == "claude-code" \
        and self._session_mode(item) == "shared"


def resume_args(self, item: Item, role: str, route: dict) -> list:
    session = (getattr(self, "state", None) or {}).get("executor_session")
    return ["--resume", session] if session and self._shared_session(item, role, route) else []


def keep_session(self, item: Item, role: str, route: dict, run) -> None:
    """Remember the session of an executor that finished, so the next executor of the run resumes it; forget a
    session that failed (a fresh one starts)."""
    if not self._shared_session(item, role, route):
        return
    if run.error or not run.session:
        self.state.pop("executor_session", None)
    else:
        self.state["executor_session"] = run.session
    self._save()


def role_env(self, item: Item, role: str, route: dict) -> Optional[dict]:
    """The environment of a role process. A role named in ``instructions.isolate_roles`` starts without the project
    instructions: they carry the rules of a developer's own session ("quality over speed", "fix every defect even
    beyond the scope"), which contradict the role's own scope rules; every role gets exactly the instructions of its
    own prompt."""
    extra = ISOLATION_ENV.get(route.get("provider")) if role in item.options["instructions"]["isolate_roles"] else None
    if not extra:
        return self.env
    base = dict(os.environ if self.env is None else self.env)
    base.update(extra)
    return base
