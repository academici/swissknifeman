"""The conductor loop: claim, brief, prepare, then the stages of one piece of work, registration and the commit.

Every step of a piece of work has a key (``brief``, ``prepare``, ``scout``, ``executor.1``, ``checks.1``,
``review.1``, ``triage.1``, ``register``, ``commit``) and is recorded in ``state.json`` once it closes. ``resume``
runs the same loop again: a closed step returns its recorded result and is not executed twice, so the loop takes
the same path up to the step that did not close. The work source is reached only through ``orch.py source``; the
roles only through the launch catalog (or ``[orch.conductor.argv]``) and see the execution-input, never the plan.

The conductor stops only on: a blocked piece of work (``on_blocked = "stop"``), red checks or confirmed findings
whose corrections stopped making progress (or reached the ceiling of their limit), a route below the minimum of the
work, an unavailable provider or role, a refusal of the work source, or a dirty working tree before new work. Nothing
is stopped for being long or costly: limits of time and tokens print beacons (``info`` lines with ``STAGE_SLOW``,
``STAGE_IDLE``, ``CHECK_SLOW``, ``BUDGET_OVER``, ``LIMIT_OVER``) that say what runs now, and the owner or an
observer decides.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import calendar
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import random
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Optional

from aicore.provider.config import routing_available
from aicore.state import blobs, project_state_dir
from aicore.util.digest import canonical_json_bytes, sha256_hex

from orch import catalog as catalogs, events, launch, policies, render, retry, sandbox
from orch import settings as settings_mod
from orch.conductor import checks as checks_mod, contract, gates, heal, observer, options as opts, process, prompts
from orch.conductor import scope as scopes
from orch.conductor.progress import Progress, human_duration
from orch.settings import ORCH_ROOT

CLASS_RANK = {"economy": 0, "implementation": 1, "frontier": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4, "ultra": 5}
LAUNCH_ROLE = {"context-scout": "scout"}
RULE_HEADING = re.compile(r"^## ([A-Za-z0-9_.-]+)[ \t]*$", re.M)
RUN_FILE, STATE_FILE = "run.json", "state.json"
REPORTS = Path(".swissknifeman") / "orch" / "reports"  # observer reports: run output, ignored
FALLBACK_ARTIFACTS = Path(".swissknifeman") / "orch-artifacts"  # committed records of a source without artifacts_dir
STATUS_EXIT = {"finished": 0, "stopped": 1}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
# An unclassified failure was always repeated (within ``limits.retries``); retry.decide would stop on it by default.
CONDUCTOR_ON_ERROR = {"unknown": {"action": "retry"}}
# The stop code of a failure class; a class that is not listed keeps the code of the failed role (``ROLE_FAILED``, ...).
PROVIDER_STOP_CODES = {"authentication": "PROVIDER_AUTH", "authorization": "PROVIDER_AUTHZ", "quota": "PROVIDER_QUOTA",
                       "rate_limit": "PROVIDER_QUOTA", "invalid_request": "PROVIDER_REFUSED",
                       "content_policy": "PROVIDER_REFUSED", "context_limit": "PROVIDER_CONTEXT",
                       "model_unavailable": "MODEL_UNAVAILABLE"}
TRANSIENT_CLASSES = ("provider_internal", "transport", "rate_limit")  # the provider CLI repeats these itself
JITTER_CAP_S, JITTER_BASE_S = 300, 30


def _mono() -> float:
    """The clock of the active run time (one place, so a test can replace it)."""
    return time.monotonic()


# The limits of the whole run (``limits.<name>_batch``) and the field of a piece's state that each one counts.
BATCH_FIELDS = {"review_rounds": "review_rounds_used", "corrections": "corrections_at", "findings": "findings_at"}
BATCH_LIMITS = tuple(BATCH_FIELDS)


class Stop(Exception):
    """An honest stop of the run: a stable code and what happened."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def sleep(seconds: float) -> None:
    """One second of a wait (a seam for the tests)."""
    time.sleep(seconds)


def wall() -> float:
    return time.time()


def unit_random() -> float:
    return random.random()


def utc_stamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return "cnd-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def runs_root(project: Path) -> Path:
    """The ignored runtime folder of every conductor run of a project."""
    return project_state_dir(project, "orch") / "conductor"


def safe(text: str) -> str:
    return _SAFE.sub("-", text).strip("-") or "x"


def write_json(path: Path, doc: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


@dataclass
class Item:
    """What the conductor knows about the piece of work it runs now."""

    ref: str
    orch_run: str
    state: dict
    directory: Path
    claim: dict
    input_doc: dict = field(default_factory=dict)
    artifacts: Optional[Path] = None
    policy: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    routes: dict = field(default_factory=dict)
    launch_plan: dict = field(default_factory=dict)
    route_notes: list = field(default_factory=list)  # routes moved at selection: gated or unavailable provider


class Conductor:
    """One conductor run in a project (a git repository)."""

    def __init__(self, *, project: Path, settings, config_file: Optional[Path] = None, mode: str = "text",
                 stream=None, model_catalog: Optional[Path] = None, roles_dir: Optional[Path] = None,
                 env: Optional[dict] = None, clock: Optional[Callable[[], str]] = None,
                 project_resolution: Optional[str] = None):
        self.project = Path(project).resolve()
        self.project_resolution = project_resolution
        self.settings = settings
        self.config_file = Path(config_file).resolve() if config_file else None
        self.mode = mode
        self.stream = stream
        self.model_catalog = model_catalog
        self.roles_dir = roles_dir
        self.env = env
        self.clock = clock
        self.conductor = dict(settings.conductor or {})
        self._catalog = None
        self._step_tokens = {"input": 0, "output": 0}
        self.run_id = ""
        self.directory = Path()
        self.run_doc: dict = {}
        self.state: dict = {}
        self.progress: Optional[Progress] = None

    # ------------------------------------------------------------------ run files

    def _open(self, run_id: str, run_doc: dict, state: dict) -> None:
        self.run_id, self.run_doc, self.state = run_id, run_doc, state
        self.directory = runs_root(self.project) / run_id
        self.progress = Progress(run_id, self.directory, self.mode, self.stream, self.clock)

    def _save(self) -> None:
        write_json(self.directory / STATE_FILE, self.state)

    def reports_dir(self) -> Path:
        return self.project / REPORTS / self.run_id

    # ------------------------------------------------------------------ partners

    def _orch(self, *args: str) -> tuple:
        """``(exit, JSON stdout or None, stderr)`` of this package's own ``orch.py``."""
        argv = [sys.executable, str(ORCH_ROOT / "scripts" / "orch.py"), "--project", str(self.project)]
        if self.project_resolution:  # the child is told the project; it records how the conductor found it
            argv += ["--project-resolution", self.project_resolution]
        if self.config_file:
            argv += ["--config", str(self.config_file)]
        done = subprocess.run(argv + list(args), cwd=str(self.project), capture_output=True, text=True,
                              env=self.env)
        try:
            doc = json.loads(done.stdout) if done.stdout.strip() else None
        except ValueError:
            doc = None
        return done.returncode, doc, done.stderr.strip()

    def _catalog_get(self):
        if self._catalog is None:
            try:
                self._catalog = catalogs.Catalog.load(self.model_catalog)
            except catalogs.CatalogError as error:
                raise Stop(error.code, str(error)) from None
        return self._catalog

    # ------------------------------------------------------------------ public verbs

    def run(self, *, plan: str, plans_root: Optional[str], items: list, batch: bool, max_items: int,
            options_file: Optional[Path] = None, adopt: bool = False) -> int:
        run_id = new_run_id()
        run_doc = {"run_id": run_id, "plan": plan, "plans_root": plans_root, "items": list(items), "batch": batch,
                   "max_items": max_items, "options_file": str(options_file) if options_file else None,
                   "adopt": bool(adopt),
                   "config_file": str(self.config_file) if self.config_file else None, "created": utc_now(),
                   "project": str(self.project), "project_resolution": self.project_resolution,
                   "working_directory": os.getcwd(), "config_digest": settings_mod.config_digest(self.settings),
                   "config_layers": settings_mod.config_layers(self.settings)}
        self._open(run_id, run_doc, {"status": "running", "items": {}, "claims": {}, "tokens": {"input": 0, "output": 0}})
        write_json(self.directory / RUN_FILE, run_doc)
        self._save()
        self.progress.emit("run.start", message=f"plan {plan}; " + (f"items {', '.join(items)}" if items else
                                                                     f"batch, at most {max_items or 'all'}"))
        return self._loop()

    def resume(self, run_id: str, retry=()) -> int:
        directory = runs_root(self.project) / run_id
        run_doc, state = read_json(directory / RUN_FILE), read_json(directory / STATE_FILE)
        if run_doc is None or state is None:
            raise Stop("RUN_UNKNOWN", f"no conductor run {run_id} in {directory.parent}")
        if run_doc.get("config_file") and not self.config_file:
            self.config_file = Path(run_doc["config_file"])
        self._open(run_id, run_doc, state)
        for ref in retry:
            self._retry(ref)
        state["status"] = "running"
        state["resumes"] = state.get("resumes", 0) + 1
        self._save()
        self.progress.emit("run.resume", message=f"resume {state['resumes']}")
        return self._loop()

    def _retry(self, ref: str) -> None:
        """Take a blocked piece back into the run: the input is built again from the (amended) plan, and the steps from the executor round that reported ``blocked`` on
        (and the closing steps after it) are repeated; the earlier rounds are kept and the work in the tree is not thrown away."""
        item = self.state["items"].get(ref)
        if not item or item.get("outcome") != "blocked":
            raise Stop("RETRY_NOT_BLOCKED", f"{ref} is not a blocked piece of this run")
        steps = item.get("steps", {})
        # the state file is sorted by key, so the order of the steps is the order of their ``ended`` stamps
        blocked = min((key for key in steps if key.startswith("executor.") and
                       (((steps[key].get("result") or {}).get("report") or {}).get("status") == "blocked")),
                      key=lambda key: steps[key].get("ended", ""), default=None)
        if blocked is None:
            raise Stop("RETRY_NOT_BLOCKED", f"{ref} has no executor round that reported blocked")
        since = steps[blocked].get("ended", "")
        # the input is built again too: the plan was amended (that is why the piece was blocked and reopened), and the
        # executor must see the amended write set, not the one of the first brief
        for key in [key for key in steps if key == blocked or key in ("brief", "prepare", "scout", "close", "register", "commit")
                    or steps[key].get("ended", "") > since]:
            steps.pop(key)
        for key in ("outcome", "stop", "partial"):
            item.pop(key, None)
        self._save()
        self.progress.emit("info", item=ref, message=f"retry: the steps from {blocked} on are repeated")

    @staticmethod
    def _work_began(state: dict) -> bool:
        """An executor round ran: the piece has this run's work in the tree and is no longer free to give back. Changes
        adopted from an earlier attempt do not count: they stay in the tree, and a later ``run --adopt`` takes them again."""
        return any(key.startswith("executor.") for key in state.get("steps", {}))

    def _release_claim(self, ref: str, state: dict, reason: str) -> bool:
        """Give the claim of ``ref`` back to the work source (``orch.py source release``), so that a later run can claim
        the piece. A source that does not serve ``release`` or refuses it keeps the claim: the stop is reported anyway."""
        code, answer, err = self._orch("source", "release", "--run", state["orch_run"], "--reason", reason)
        released = code == 0 and isinstance(answer, dict) and answer.get("outcome") in ("released", "no-op")
        state.setdefault("released", []).append({"at": utc_now(), "reason": reason, "ok": released})
        self._save()
        self.progress.emit("info", item=ref, reason_code="CLAIM_RELEASED" if released else "CLAIM_KEPT",
                           message=(f"the claim of {ref} is given back to the work source" if released else
                                    f"the claim of {ref} stays with run {state['orch_run']}: "
                                    f"{(answer or {}).get('message') or err or 'the source refused'}"))
        return released

    def release(self, run_id: str, ref: str, reason: str) -> int:
        """Give a piece of this run back to the work source by hand, when a run died or stopped before any work began
        (an executor round makes it refuse: settle or retry the piece instead)."""
        directory = runs_root(self.project) / run_id
        run_doc, state = read_json(directory / RUN_FILE), read_json(directory / STATE_FILE)
        if run_doc is None or state is None:
            raise Stop("RUN_UNKNOWN", f"no conductor run {run_id} in {directory.parent}")
        item = state.get("items", {}).get(ref)
        if item is None:
            raise Stop("ITEM_UNKNOWN", f"{ref} is not a piece of run {run_id}")
        if self._work_began(item) or item.get("outcome") in ("done", "done_with_deviations"):
            raise Stop("RELEASE_WORK_BEGAN", f"{ref} has work in the tree or is closed; settle it, or resume with --retry")
        self._open(run_id, run_doc, state)
        if not self._release_claim(ref, item, reason):
            raise Stop("RELEASE_REFUSED", f"the work source did not release {ref}; see the progress line")
        return 0

    def settle(self, run_id: str, ref: str, outcome: str, reason: str) -> int:
        """Set the outcome of a piece of this run by hand, after the owner or an observer finished it outside the
        conductor (committed it with the work source's own command, or gave it up). Nothing else changes: the work
        source keeps its own record; a resume then treats the piece as closed."""
        directory = runs_root(self.project) / run_id
        run_doc, state = read_json(directory / RUN_FILE), read_json(directory / STATE_FILE)
        if run_doc is None or state is None:
            raise Stop("RUN_UNKNOWN", f"no conductor run {run_id} in {directory.parent}")
        if ref not in state.get("items", {}):
            raise Stop("ITEM_UNKNOWN", f"{ref} is not a piece of run {run_id}")
        self._open(run_id, run_doc, state)
        item = state["items"][ref]
        before = item.get("outcome")
        item["outcome"] = outcome
        item.pop("stop", None)
        item.pop("partial", None)
        item.setdefault("settled", []).append({"from": before, "to": outcome, "reason": reason, "at": utc_now()})
        self._save()
        self.progress.emit("info", item=ref, reason_code="SETTLED", outcome=outcome, message=f"outcome {before or '-'} → {outcome} by hand: {reason}")
        return 0

    # ------------------------------------------------------------------ the loop over pieces of work

    def _active_s(self) -> float:
        """Active run time: the closed segments of earlier processes plus the one now running (a resume a day later
        does not count the day)."""
        segment = getattr(self, "_segment", None)
        return float(self.state.get("active_s", 0)) + (0.0 if segment is None else _mono() - segment)

    def _run_clock(self, item: Item, stop: bool = True) -> None:
        """RUN_SLOW every ``limits.run_warn_s`` of active run time (a beacon and one plan note per threshold, never a
        stop); ``limits.run_timeout_s`` > 0 stops the run with RUN_TIMEOUT (``stop`` false: from a thread of checks,
        where the next step boundary stops it). Called by role ticks, check ticks and step boundaries."""
        limits = (item.options or {}).get("limits") or {}
        warn, cap = limits.get("run_warn_s", 0), limits.get("run_timeout_s", 0)
        if not (warn or cap):
            return
        active = self._active_s()
        if warn and int(active // warn) > self.state.get("run_warned", 0):
            self.state["run_warned"] = int(active // warn)
            items = self.state.get("items", {})
            closed = sum(1 for row in items.values() if row.get("outcome") in ("done", "done_with_deviations", "blocked"))
            asked = len(self.run_doc.get("items") or [])
            text = (f"run active {human_duration(active)}; {closed} piece(s) closed"
                    + (f", {max(asked - closed, 0)} left" if asked else "") + f"; now {item.ref} {self._current_step or '-'}")
            self.progress.emit("info", item=item.ref, reason_code="RUN_SLOW", message=text)
            self._plan_note(item, text)
        if stop and cap and active >= cap:
            raise Stop("RUN_TIMEOUT", f"the run was active {human_duration(active)}, past limits.run_timeout_s {cap}; "
                                      "raise it or set 0, then resume")

    _current_step: Optional[str] = None

    def _loop(self) -> int:
        started = time.monotonic()
        self._segment = _mono()
        code, reason, outcome = 0, None, "finished"
        try:
            self._pieces()
        except Stop as stop:
            code, reason, outcome = 1, stop, "stopped"
        except KeyboardInterrupt:
            code, reason, outcome = 130, Stop("INTERRUPTED", "interrupted; resume continues"), "stopped"
        self.state["active_s"] = round(self._active_s(), 1)
        self._segment = None
        self.state["status"] = outcome
        if reason is not None:
            self.state["stop"] = {"code": reason.code, "message": reason.message}
        self._save()
        try:
            written = observer.write_report(self.directory, self.project, self.reports_dir())
            message = f"observer report {written['markdown']}"
        except Exception as error:  # noqa: BLE001 — a failed report never hides the outcome of the run
            message = f"observer report not written: {type(error).__name__}: {error}"
        self.progress.emit("run.end", outcome=outcome, reason_code=reason.code if reason else None,
                           duration_s=round(time.monotonic() - started, 1),
                           message=(reason.message + "; " if reason else "") + message)
        return code

    def _pieces(self) -> None:
        """Explicit items in order, or the next ready pieces of the source (``--batch``). A piece that closed
        (done or blocked) in an earlier pass of this run is not claimed again; one that stopped half-way resumes
        on its own working tree, while new work needs a clean one."""
        doc = self.run_doc
        keys = [(f"item-{safe(ref)}", [ref]) for ref in doc["items"]] if doc["items"] else None
        count = index = 0
        while True:
            if keys is not None:
                if index >= len(keys):
                    return
                key, asked = keys[index]
            else:
                if doc.get("max_items") and count >= doc["max_items"]:
                    return
                key, asked = f"next-{index + 1}", []
            index += 1
            known = self.state["claims"].get(key)
            outcome = self.state["items"].get(known["ref"], {}).get("outcome") if known else None
            if outcome in ("done", "done_with_deviations", "blocked"):
                count += 1
                continue
            adopted = []
            if known is None:
                if doc.get("adopt") and index == 1:
                    adopted = self._dirty_paths()  # the work of an earlier attempt, checked against the write set later
                else:
                    self._require_clean_tree()
            answer = self._claim(key, asked)
            if answer is None:
                return
            count += 1
            if adopted:
                self.state["items"].setdefault(answer["ref"], {"steps": {}, "retries_used": 0, "orch_run": answer["run_id"]}) \
                    .setdefault("adopted", adopted)
                self._save()
            outcome = self._piece(answer)
            if outcome == "blocked" and (self._on_blocked() == "stop"
                                         or self.state["items"][answer["ref"]].get("partial")):
                why = "; it left changes in the tree" if self._on_blocked() != "stop" else ""
                raise Stop("ITEM_BLOCKED", f"{answer['ref']} is blocked{why}; see its escalation")

    def _on_blocked(self) -> str:
        return self.state.get("on_blocked") or self.conductor.get("on_blocked") or "stop"

    def _dirty_paths(self) -> list:
        """Changed paths of the tree outside the conductor reports."""
        try:
            return scopes.own(scopes.dirty(self.project), [REPORTS.as_posix()])
        except RuntimeError as error:
            raise Stop("PROJECT_NOT_GIT", str(error)) from None

    def _require_clean_tree(self) -> None:
        """New work starts on a clean tree: changes outside the conductor reports would leak into it (``run --adopt``
        takes the changes of an earlier attempt of the first piece instead)."""
        dirty = self._dirty_paths()
        if dirty:
            raise Stop("WORKTREE_DIRTY", f"{len(dirty)} changed path(s) before new work, such as {dirty[0]}; "
                                         "commit or set them aside, or take them over with run --adopt, then resume")

    def _claim(self, key: str, asked: list) -> Optional[dict]:
        actor = self._claim_actor()
        submission = f"sub-{safe(self.run_id)}-{safe(key)}"[:120]
        args = ["source", "claim", "--plan", self.run_doc["plan"], "--actor", actor, "--submission-id", submission]
        if self.run_doc.get("plans_root"):
            args += ["--plans-root", self.run_doc["plans_root"]]
        for ref in asked:
            args += ["--item", ref]
        code, answer, err = self._orch(*args)
        if code == 3:
            raise Stop("WORK_SOURCE_UNAVAILABLE", err or "no work source")
        if not isinstance(answer, dict):
            raise Stop("WORK_SOURCE_FAILED", err or "claim printed no answer")
        if answer.get("status") == "none":
            self.progress.emit("info", message="the work source has no ready piece of work")
            return None
        if answer.get("status") != "claimed":
            raise Stop("CLAIM_BLOCKED", f"{answer.get('ref', '-')}: {answer.get('reason_code', '-')}: "
                                        f"{answer.get('message', err)}")
        self.state["claims"][key] = {"ref": answer["ref"], "orch_run": answer["run_id"], "submission": submission}
        self._save()
        return answer

    def _claim_actor(self) -> str:
        """Who runs the work, as claimed: the default executor (provider and model, no effort; the route of the
        work is checked by the source at registration against the executor that really ran)."""
        provider = self.conductor.get("provider") or "claude-code"
        entry = self._entry("executor", provider)
        model = self._catalog_get().resolve_model(provider, entry["model_class"]) \
            if entry["model_set"] == "supported" else "default"
        return f"{provider}/{model}"

    # ------------------------------------------------------------------ one piece of work

    def _piece(self, answer: dict) -> str:
        ref = answer["ref"]
        state = self.state["items"].setdefault(ref, {"steps": {}, "retries_used": 0, "orch_run": answer["run_id"]})
        if state.get("outcome") in ("done", "done_with_deviations"):
            return state["outcome"]
        item = Item(ref=ref, orch_run=answer["run_id"], state=state, directory=self.directory / safe(ref),
                    claim=answer)
        begin = time.monotonic()
        self.progress.emit("item.start", item=ref, message=answer.get("title") or "")
        try:
            outcome = self._conduct(item)
        except Stop as stop:
            state["outcome"] = "stopped"
            state["stop"] = {"code": stop.code, "message": stop.message}
            self._save()
            if not self._work_began(state):  # a claim nobody worked on must not outlive the stopped run
                self._release_claim(ref, state, f"stopped before any work began: {stop.code}")
            self.progress.emit("item.end", item=ref, outcome="stopped", reason_code=stop.code,
                               duration_s=round(time.monotonic() - begin, 1), message=stop.message)
            raise
        state["outcome"] = outcome
        self._save()
        self.progress.emit("item.end", item=ref, outcome=outcome, duration_s=round(time.monotonic() - begin, 1))
        return outcome

    def _conduct(self, item: Item) -> str:
        brief = self._step(item, "brief", lambda: self._brief(item))
        item.input_doc = json.loads(Path(brief["input_path"]).read_text(encoding="utf-8"))
        item.artifacts = self.project / brief["artifacts_dir"]
        if "source_paths" not in item.state:  # what the work source changed by claiming: never the role's work
            item.state["source_paths"] = sorted(set(self._dirty_paths()) - set(item.state.get("adopted") or []))
            self._save()
        self._resolve(item)
        self._routes(item, persist=False)
        self._refuse_acp(item)  # before prepare: the binding would refuse an acp route with a less telling code
        item.launch_plan = self._step(item, "prepare", lambda: self._prepare(item))
        self._routes(item)
        adopted = self._adopted(item)
        scout_text = self._scout(item)
        report = self._execute(item, 1, scout_text, prompts.ADOPTED.format(paths=", ".join(adopted)) if adopted else "")
        if report["status"] == "blocked":
            return self._finish(item, report, None)
        overlap = self._review_enabled(item) and item.options["checks"]["overlap_review"]
        round_no = 1
        rows = self._checks_then_review(item, report, 1, 1) if overlap else self._run_checks(item, 1, report)
        state = item.state
        state.setdefault("check_fixes_used", 0)
        state.setdefault("corrections_used", 0)
        state.setdefault("check_fixes_at", [])   # rounds that got a correction: a resume walks the closed rounds again,
        state.setdefault("corrections_at", [])   # so a counter that only counts up would count them twice
        rows, report, round_no = self._green(item, rows, report, round_no, scout_text, 1 if overlap else None)
        if report["status"] == "blocked":
            return self._finish(item, report, rows)
        if self._review_enabled(item):
            review_round, earlier = 1, None
            while True:
                findings = self._review(item, review_round, rows)
                if not findings["findings"]:
                    break
                triage = self._triage(item, review_round, findings)
                if not triage["confirmed"]:
                    break
                major, minor = self._split_confirmed(item, findings, triage)
                self._defer_minor(item, findings, minor)
                if not major:  # only findings below the floor: noted in the plan for the phase cleanup, no correction, no new audit
                    break
                # progress: fewer findings to correct than the round before, or other ones (a first round has
                # nothing to compare with, so it never goes past a target on its own)
                state["review_rounds_used"] = review_round
                state.setdefault("findings_at", {})[str(review_round)] = len(triage["confirmed"])
                places = sorted(self._place(findings, entry["finding"]) for entry in major)
                progress = earlier is not None and (len(places) < len(earlier) or places != earlier)
                earlier = places
                replayed = review_round in state["corrections_at"]
                rounds_why = self._allowance(item, "review_rounds", review_round, progress, emit=not replayed)
                rounds_why = rounds_why or self._batch_allowance(item, "findings", self._piece_count(state, "findings_at"),
                                                                 progress, emit=not replayed)
                if review_round in state.get("combined_done", []):  # corrected together with the red checks
                    if rounds_why:
                        self._plan_note(item, f"findings of review round {review_round} were corrected together with the "
                                              "red checks; the correction was not reviewed again")
                        break
                    review_round += 1
                    continue
                triage = dict(triage, confirmed=major)
                final = bool(rounds_why) and item.options["review"]["final_correction"]  # correct, but audit no more
                done_before = len([number for number in state["corrections_at"] if number != review_round])
                fixes_why = None if replayed else self._allowance(item, "corrections", done_before, progress)
                batch_why = next((why for why in (rounds_why, fixes_why) if why and why.startswith("batch:")), None)
                if not replayed and batch_why and not final:
                    blockers = [entry["finding"] for entry in major
                                if self._severity_of(findings, entry["finding"]) == "blocker"]
                    if blockers:
                        raise Stop("REVIEW_LIMIT", f"open Blocker finding(s) {', '.join(blockers)} remain and the "
                                                   f"batch limit is spent: {batch_why}")
                    self._defer_minor(item, findings, major)
                    self._plan_note(item, f"{batch_why}; the confirmed findings of review round {review_round} "
                                          "are noted, not corrected")
                    break
                if not replayed and ((rounds_why and not final) or fixes_why):
                    ids = ", ".join(entry["finding"] for entry in major)
                    return self._finish(item, self._blocked(report, "REVIEW_LIMIT",
                                        f"confirmed review findings {ids} remain after {review_round} review "
                                        f"round(s) and {done_before} correction(s): {rounds_why or fixes_why}"), rows)
                if not replayed:
                    state["corrections_at"].append(review_round)
                state["corrections_used"] = len(state["corrections_at"])
                round_no += 1
                report = self._execute(item, round_no, scout_text, prompts.review_correction(findings, triage))
                if report["status"] == "blocked":
                    return self._finish(item, report, rows)
                rows = (self._checks_then_review(item, report, round_no, review_round + 1) if overlap and not final
                        else self._run_checks(item, round_no, report))
                rows, report, round_no = self._green(item, rows, report, round_no, scout_text,
                                                     review_round + 1 if overlap and not final else None)
                if report["status"] == "blocked":
                    return self._finish(item, report, rows)
                if final:
                    ids = ", ".join(entry["finding"] for entry in major)
                    self._plan_note(item, f"findings {ids} of review round {review_round} were corrected after the last "
                                          "review round the limit allows; the correction was not reviewed again")
                    break
                review_round += 1
        return self._finish(item, report, rows)

    @staticmethod
    def _severity_of(findings: dict, finding_id: str) -> str:
        found = next((entry for entry in findings.get("findings", []) if entry.get("id") == finding_id), {})
        return str(found.get("severity", "")).lower()

    @staticmethod
    def _place(findings: dict, finding_id: str) -> str:
        found = next((entry for entry in findings.get("findings", []) if entry.get("id") == finding_id), {})
        return f"{found.get('location', '-')}|{str(found.get('failure_scenario', ''))[:80]}"

    def _allowance(self, item: Item, name: str, used: int, progress: bool, emit: bool = True) -> Optional[str]:
        """``None`` when one more round of ``name`` (``review_rounds``, ``corrections``, ``check_fixes``) may run after
        ``used`` of them, else why not. The limit is a target: past it a round still runs while the last one made
        progress, up to ``ceiling_factor`` times the target; every such round prints a LIMIT_OVER beacon and leaves a
        plan note, so a long fight with a piece of work is visible, and a correction that changes nothing ends it."""
        limits = item.options["limits"]
        why = self._over_target(item, name, limits[name], used, progress, emit, limits["ceiling_factor"])
        if why or name not in BATCH_LIMITS:
            return why
        return self._batch_allowance(item, name, used, progress, emit)

    def _over_target(self, item: Item, name: str, target: int, used: int, progress: bool, emit: bool, factor: int,
                     scope: str = "") -> Optional[str]:
        """The target and ceiling rule of ``_allowance`` for one limit (``scope`` "batch: " for a limit of the run)."""
        if used < target:
            return None
        ceiling = target * factor
        if used >= ceiling:
            return f"{scope}the ceiling of {ceiling} for {name} (target {target} × {factor}) is reached"
        if not progress:
            return f"{scope}past the target of {target} for {name} the last correction made no progress"
        if emit:
            text = (f"{scope}{name}: round {used + 1} goes past the target of {target} (ceiling {ceiling}) because the last "
                    "correction made progress")
            self.progress.emit("info", item=item.ref, reason_code="LIMIT_OVER", message=text)
            self._plan_note(item, text)
        return None

    def _batch_used(self, item: Item, name: str, own: int) -> int:
        """What the whole run has used of ``name`` (``review_rounds``, ``corrections``, ``findings``): the other pieces
        from their own state, this piece as ``own``. Derived from piece state, so a resume does not count twice."""
        key = BATCH_FIELDS[name]
        others = sum(self._piece_count(row, key) for ref, row in self.state["items"].items() if ref != item.ref)
        return others + own

    @staticmethod
    def _piece_count(row: dict, key: str) -> int:
        value = row.get(key, 0)
        return sum(value.values()) if isinstance(value, dict) else len(value) if isinstance(value, list) else int(value)

    def _batch_allowance(self, item: Item, name: str, used: int, progress: bool, emit: bool = True) -> Optional[str]:
        """The limit ``<name>_batch`` of the whole run, with the same target and ceiling rule; 0 has no limit.
        The refusal text starts with ``batch:``."""
        limits = item.options["limits"]
        target = limits.get(f"{name}_batch", 0)
        if not target:
            return None
        total = self._batch_used(item, name, used)
        self.state["batch"] = {key: self._batch_used(item, key, self._piece_count(item.state, BATCH_FIELDS[key]))
                               for key in BATCH_LIMITS}
        return self._over_target(item, f"{name}_batch", target, total, progress, emit, limits["ceiling_factor"], "batch: ")

    @staticmethod
    def _red_signature(rows: list) -> tuple:
        """The red checks of a round and how many failure lines their tails show (a correction that mends some of
        the tests of a red check is progress too)."""
        red = [row for row in rows if not row["green"] and not row.get("skipped")]
        failures = sum(len(re.findall(r"^(?:FAIL|ERROR|FAILED|not ok)\b", row.get("tail") or "", re.M)) for row in red)
        return tuple(sorted(row["id"] for row in red)), failures

    def _green(self, item: Item, rows: list, report: dict, round_no: int, scout_text: str,
               review_no: Optional[int] = None) -> tuple:
        """Correct red checks, within the ``check_fixes`` target or past it while the red checks change; otherwise
        the piece of work is blocked. With ``review_no`` (``checks.overlap_review``) the checks of a correction run
        while review ``review_no`` reads it."""
        state, earlier = item.state, None
        while not all(row["green"] for row in rows):
            red = [row for row in rows if not row["green"] and not row.get("skipped")]
            signature = self._red_signature(rows)
            progress = earlier is not None and (signature[0] != earlier[0] or signature[1] < earlier[1])
            earlier = signature
            replayed = round_no in state["check_fixes_at"]
            done_before = len([number for number in state["check_fixes_at"] if number != round_no])
            why = None if replayed else self._allowance(item, "check_fixes", done_before, progress)
            if why:
                names = ", ".join(row["id"] for row in red)
                return rows, self._blocked(report, "CHECKS_RED", f"acceptance checks {names} stay red after "
                                                                 f"{done_before} correction(s): {why}"), round_no
            if not replayed:
                state["check_fixes_at"].append(round_no)
            state["check_fixes_used"] = len(state["check_fixes_at"])
            round_no += 1
            text, combined = prompts.check_correction(red), state.get("combined")
            if combined:  # the finished review's confirmed findings are corrected in this one round, and only in it
                text += "\n\n" + combined["text"]
                if combined["review"] not in state.setdefault("combined_done", []):
                    state["combined_done"].append(combined["review"])
                if combined["review"] not in state["corrections_at"]:
                    state["corrections_at"].append(combined["review"])
                state["corrections_used"] = len(state["corrections_at"])
                state.pop("combined")
                self._save()
            report = self._execute(item, round_no, scout_text, text)
            if report["status"] == "blocked":
                return rows, report, round_no
            rows = (self._checks_then_review(item, report, round_no, review_no) if review_no is not None
                    else self._run_checks(item, round_no, report))
        return rows, report, round_no

    def _split_confirmed(self, item: Item, findings: dict, triage: dict) -> tuple:
        """``(corrected, deferred)`` confirmed entries by ``review.correct_min_severity``: only the first go to a
        correction and make a new audit necessary."""
        ranks = {name.lower(): rank for rank, name in enumerate(opts.SEVERITIES)}
        floor = ranks[item.options["review"]["correct_min_severity"].lower()]
        severity = {found.get("id"): ranks.get(str(found.get("severity", "")).lower(), 0)
                    for found in findings["findings"]}
        corrected = [entry for entry in triage["confirmed"] if severity.get(entry["finding"], 0) <= floor]
        deferred = [entry for entry in triage["confirmed"] if severity.get(entry["finding"], 0) > floor]
        return corrected, deferred

    @staticmethod
    def _notes(item: Item) -> list:
        """The plan notes the registration of the piece carries (``deferred_minors`` in runs before the rename)."""
        if "plan_notes" not in item.state and "deferred_minors" in item.state:
            item.state["plan_notes"] = item.state.pop("deferred_minors")
        return item.state.setdefault("plan_notes", [])

    @classmethod
    def _plan_note(cls, item: Item, text: str) -> None:
        note = {"text": text, "kind": "note", "impact": "the run of this piece went its own way here",
                "next": "a reviewer of the phase may look at it"}
        notes = cls._notes(item)
        if note not in notes:
            notes.append(note)

    def _note_rejected(self, item: Item, findings: dict, triage: dict) -> None:
        """A rejected finding at or above ``review.correct_min_severity`` is never lost: the reason travels as a plan
        note, because a single triager may reject a real defect as "outside the write set" and nobody picks it up."""
        ranks = {name.lower(): rank for rank, name in enumerate(opts.SEVERITIES)}
        floor = ranks[item.options["review"]["correct_min_severity"].lower()]
        by_id = {found.get("id"): found for found in findings["findings"]}
        deferred = self._notes(item)
        for entry in triage["rejected"]:
            found = by_id.get(entry["finding"], {})
            if ranks.get(str(found.get("severity", "")).lower(), len(ranks)) > floor:
                continue
            note = {"text": f"rejected {str(found.get('severity')).lower()} finding {found.get('location', '-')}: "
                            f"{found.get('failure_scenario', '')} Triage reason: {entry.get('reason', '-')}",
                    "kind": "note", "impact": "a real defect rejected as outside this item stays open until someone owns it",
                    "next": "the reviewer of the phase checks the rejection; a real defect gets an owner item"}
            if note not in deferred:
                deferred.append(note)

    @classmethod
    def _defer_minor(cls, item: Item, findings: dict, minor: list) -> None:
        """Confirmed minor findings are not corrected now: they travel as plan notes for the cleanup of the phase."""
        by_id = {found.get("id"): found for found in findings["findings"]}
        deferred = cls._notes(item)
        for entry in minor:
            found = by_id.get(entry["finding"], {})
            note = ({"text": f"deferred {str(found.get('severity', 'Minor')).lower()} finding "
                                     f"{found.get('location', '-')}: {found.get('failure_scenario', '')}",
                             "kind": "note", "impact": "none for the acceptance; found by the review of this item",
                     "next": f"fix at the cleanup of the phase; fix idea: {entry.get('fix', '-')}"})
            if note not in deferred:  # a resumed run walks the closed rounds again
                deferred.append(note)

    @staticmethod
    def _blocked(report: dict, code: str, text: str) -> dict:
        found = dict(report)
        found["status"] = "blocked"
        found["open_issues"] = list(report.get("open_issues", [])) + [
            {"text": f"{code}: {text}", "kind": "escalation", "next": "the owner decides how to go on"}]
        return found

    # ------------------------------------------------------------------ steps

    def _step(self, item: Item, key: str, run: Callable[[], Any], *, role: str = "deterministic",
              route: Optional[str] = None, verdict: Optional[Callable[[Any], str]] = None) -> Any:
        steps = item.state.setdefault("steps", {})
        known = steps.get(key)
        if known and known.get("status") == "done":
            self.progress.emit("stage.skip", item=item.ref, stage=key, role=role, route=known.get("route"),
                               verdict=known.get("verdict"), message="closed earlier; not repeated")
            return known["result"]
        self._current_step = key
        if item.options:
            self._run_clock(item)
        self.progress.emit("stage.start", item=item.ref, stage=key, role=role, route=route)
        begin = time.monotonic()
        self._step_tokens = {"input": 0, "output": 0}
        try:
            result = run()
        except Stop as stop:
            self.progress.emit("stage.end", item=item.ref, stage=key, role=role, route=route, verdict="stopped",
                               reason_code=stop.code, duration_s=round(time.monotonic() - begin, 1),
                               message=stop.message)
            self._stage_event(item, key, "refused" if stop.code != "TIMEOUT" else "timeout")
            raise
        tokens = self._step_tokens
        said = verdict(result) if verdict else "done"
        steps[key] = {"status": "done", "result": result, "verdict": said, "role": role, "route": route,
                      "duration_s": round(time.monotonic() - begin, 1), "ended": utc_now(),
                      **({"tokens": tokens} if tokens and any(tokens.values()) else {})}
        self._save()
        self.progress.emit("stage.end", item=item.ref, stage=key, role=role, route=route, verdict=said,
                           duration_s=steps[key]["duration_s"], tokens=steps[key].get("tokens"))
        self._stage_event(item, key, "completed")
        if item.options:
            self._budget(item)
        return result

    def _stage_event(self, item: Item, key: str, status: str) -> None:
        kind, _, number = key.partition(".")
        data = {"run_id": item.orch_run, "stage_id": kind, "attempt": int(number) if number.isdigit() else 1,
                "status": status, "attempt_id": item.claim.get("attempt_id"),
                # none before the options are resolved (the brief step)
                "options_digest": opts.digest(item.options) if item.options else None}
        events.emit("orch.run.stage.finished", {key: value for key, value in data.items() if value is not None},
                    subject=item.orch_run, settings=self.settings, project=self.project,
                    config_file=self.config_file)

    def _brief(self, item: Item) -> dict:
        code, answer, err = self._orch("source", "brief", "--run", item.orch_run)
        if code != 0 or not isinstance(answer, dict):
            raise Stop("BRIEF_REFUSED", err or "brief printed no answer")
        try:
            doc = json.loads(blobs.read_bytes(answer["input_ref"], project=self.project))
        except (OSError, ValueError, KeyError) as error:
            raise Stop("BRIEF_UNAVAILABLE", str(error)) from None
        path = write_json(item.directory / "input.json", doc)
        artifacts = answer.get("artifacts_dir") or (FALLBACK_ARTIFACTS / self.run_id / safe(item.ref)).as_posix()
        try:
            base = checks_mod.head(self.project)  # the review compares the candidate with this revision
        except RuntimeError as error:
            raise Stop("PROJECT_NOT_GIT", str(error)) from None
        return {"input_path": str(path), "input_id": answer.get("input_id"), "artifacts_dir": artifacts,
                "base": base}

    def _resolve(self, item: Item, persist: bool = True) -> None:
        """The run-policy of the scenario and the merged options (configuration, pack, source layers, invocation)."""
        scenario = item.claim.get("scenario") or self.settings.default_profile
        try:
            item.policy = policies.load(scenario, self.settings, warn=lambda message: None)
        except policies.PolicyError as error:
            raise Stop(error.code, str(error)) from None
        layers = list(item.claim.get("options") or [])
        if self.run_doc.get("options_file"):
            try:
                found = json.loads(Path(self.run_doc["options_file"]).read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise Stop("OPTIONS_INVALID", f"{self.run_doc['options_file']}: {error}") from None
            layers.append({"source": "invocation:--options", "options": found})
        try:
            item.options, item.sources = opts.effective(self.conductor, item.policy, layers)
        except opts.OptionsError as error:
            raise Stop(error.code, error.message) from None
        if persist:
            self.state["on_blocked"] = item.options["on_blocked"]
            write_json(item.directory / "options.json", {"scenario": scenario, "options": item.options,
                                                         "sources": item.sources, "digest": opts.digest(item.options),
                                                         "claim_route": item.claim.get("route")})

    def _prepare(self, item: Item) -> dict:
        provider = opts.stage_route(item.options, "executor").get("provider") or self.conductor.get("provider") \
            or "claude-code"
        args = ["source", "prepare", "--run", item.orch_run, "--provider", provider]
        if self.model_catalog:
            args += ["--model-catalog", str(self.model_catalog)]
        code, plan, err = self._orch(*args)
        if code != 0 or not isinstance(plan, dict):
            first = (err or "prepare refused").splitlines()[0]
            raise Stop("PREPARE_REFUSED", first)
        return {"stages": [{key: stage.get(key) for key in ("stage_id", "role", "provider", "model", "effort")}
                           for stage in plan.get("stages", [])],
                "refusals": [{key: item_.get(key) for key in ("stage_id", "reason_code")}
                             for item_ in plan.get("refusals", [])]}

    # ------------------------------------------------------------------ routes

    def _entry(self, role: str, provider: str) -> dict:
        try:
            return launch.entry(launch.load_catalog(), LAUNCH_ROLE.get(role, role), provider)
        except launch.LaunchError as error:
            raise Stop(error.code, str(error)) from None

    def _routes(self, item: Item, persist: bool = True) -> None:
        roles = ["executor"]
        if self._scout_stage(item) is not None:
            roles.insert(0, "context-scout")
        if self._review_enabled(item):
            roles += ["reviewer", self._triage_role(item)]
        if self._closer_named(item):
            roles.append("registrar")
        for role in roles:
            item.routes[role] = self._selected(item, role, persist)
        if item.options["limits"].get("repairs", 0) > 0:
            try:  # optional: without a launch entry or a model for it, results are only healed and repeated
                item.routes["report-fixer"] = self._selected(item, "report-fixer", persist)
            except Stop:
                pass
        self._route_minimum(item)
        if persist:
            self._preflight(item)
            write_json(item.directory / "routes.json", item.routes)

    def route_problem(self, route: dict) -> str | None:
        """Why a route cannot run, as ``CODE: text``; ``None`` when it can. An ``acp`` role is never driven by the
        conductor (D4), whatever command line stands in for it; a Codex route confined by ``--sandbox`` needs the
        provider sandbox to start on this machine."""
        disabled = self.provider_disabled(route["provider"])
        if disabled:
            return disabled
        if route["transport"] == "acp":
            return "TRANSPORT_UNSUPPORTED: the conductor does not drive acp roles"
        if self._codex_sandboxed(route) and not sandbox.probe()["available"]:
            return f"SANDBOX_UNAVAILABLE: {sandbox.probe()['reason']}"
        if not process.available(route["argv"]):
            return f"PROVIDER_UNAVAILABLE: {route['argv'][0]} not found"
        gate = gates.blocked(route["provider"], wall())
        if gate:
            return f"PROVIDER_QUOTA: {route['provider']} is gated until {gate['until']}"
        return None

    def provider_disabled(self, provider: str) -> str | None:
        """``PROVIDER_DISABLED: ...`` with the layer that set it when ``aicore.providers.available.<provider>.enabled`` is
        false (machine, invocation or flags: a project cannot enable what the machine disabled); ``None`` otherwise. The
        axis is independent of ``providers.selection``, which only decides which surfaces are rolled out."""
        found = self.settings.aicore if self.settings is not None else None
        if found is None:
            return None
        available, layer = routing_available(provider, resolved=found)
        if available:
            return None
        return f"PROVIDER_DISABLED: aicore.providers.available.{provider}.enabled = false ({layer})"

    def _selected(self, item: Item, role: str, persist: bool) -> dict:
        """The route of ``role`` that can start: its own, or, when its provider is gated (the account quota is known to
        be exhausted until a reset) or cannot start here (no CLI, a sandbox that does not start), the first declared
        fallback route that passes the admission. A gated route with no such fallback stops the run with
        ``PROVIDER_QUOTA``; one that cannot start keeps its route and is refused by the preflight with its own code (the
        optional scout is left to its own step: it is skipped when it may be)."""
        kept = (item.state.get("route_overrides") or {}).get(role)  # a fallback taken before a stop: a resume keeps it
        route = self._route(item, role, kept) if kept else self._route(item, role)
        gate = gates.blocked(route["provider"], wall())
        problem = None if gate else self.route_problem(route)
        if gate is None and problem is None:
            return route
        found, refused = self._fallback(item, role, route)
        until = f"{route['provider']} is gated until {gate['until']} ({gate['class']} {gate['code']}, set by {gate['set_by']})" \
            if gate else problem
        if found is None:
            if gate is None or role == "context-scout":
                return route
            raise Stop("PROVIDER_QUOTA", f"{role}: {until}" + (f"; no fallback: {'; '.join(refused)}" if refused else "")
                       + "; resume after the reset, or remove the gate with conduct.py gates --clear")
        reason = "CAPACITY_GATED" if gate else problem.split(":", 1)[0]
        item.route_notes.append({"role": role, "reason_code": reason, "from": self.label(route), "to": self.label(found),
                                 "detail": until})
        if persist and self.progress is not None:
            if gate:
                self.progress.emit("info", item=item.ref, role=role, route=self.label(found), reason_code="CAPACITY_GATED",
                                   message=f"{role}: {until}")
            self.progress.emit("info", item=item.ref, role=role, route=self.label(found), reason_code="ROUTE_FALLBACK",
                               message=f"{role}: {self.label(route)} -> {self.label(found)} ({reason})")
        return found

    def _fallback(self, item: Item, role: str, current: dict, declared: Optional[dict] = None) -> tuple:
        """``(route, refused)``: the first declared fallback route of ``role`` other than ``current`` that passes
        ``_admit`` (``declared`` narrows the choice to the route retry.decide named), and why the others were refused."""
        refused = []
        for entry in item.options.get("fallback_routes", []):
            if entry["role"] != role or (entry["provider"], entry["model_class"]) == (current["provider"],
                                                                                    current["model_class"]):
                continue
            if declared is not None and (entry["provider"], entry["model_class"]) != (declared["provider"],
                                                                                    declared["model_class"]):
                continue
            try:
                candidate = self._route(item, role, entry)
            except Stop as stop:
                refused.append(f"{entry['provider']}/{entry['model_class']}: {stop.code}: {stop.message}")
                continue
            problem = self._admit(item, role, candidate)
            if problem is None:
                return candidate, refused
            refused.append(f"{self.label(candidate)}: {problem}")
        return None, refused

    def _admit(self, item: Item, role: str, route: dict) -> Optional[str]:
        """Why ``route`` may not take over the work of ``role``, as ``CODE: text``; ``None`` when it may: not below the
        class and effort the work requires, startable here (transport, sandbox, command) and not gated."""
        if role == "executor":
            try:
                self._route_minimum(item, route)
            except Stop as stop:
                return f"{stop.code}: {stop.message}"
        return self.route_problem(route) or self._claude_sandbox_problem(item, route)

    def _claude_sandbox_problem(self, item: Item, route: dict) -> Optional[str]:
        """``SANDBOX_UNAVAILABLE: ...`` when ``instructions.sandbox`` is ``require`` and a Claude Code role with Bash on
        ``route`` could not be confined (the sandbox cannot start, or the CLI does not list ``--settings``): the rule of
        the preflight, applied to a route that was not in it."""
        if self._sandbox_mode(item) != "require" or not self._claude_bash(route):
            return None
        probed = sandbox.probe()
        if not probed["available"]:
            return f"SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the sandbox cannot start ({probed['reason']})"
        if not self._knows(route["argv"], ["--settings"]):
            return "SANDBOX_UNAVAILABLE: instructions.sandbox is require, and the claude CLI does not list --settings"
        return None

    @staticmethod
    def _codex_sandboxed(route: dict) -> bool:
        argv = route["argv"]
        mode = argv[argv.index("--sandbox") + 1] if "--sandbox" in argv[:-1] else None
        return route.get("provider") == "codex" and mode in ("read-only", "workspace-write")

    OPTIONAL_ROLES = {"context-scout", "report-fixer"}

    def _refuse_acp(self, item: Item) -> None:
        unsupported = [(role, route) for role, route in item.routes.items()
                       if role not in self.OPTIONAL_ROLES and route["transport"] == "acp"]
        if unsupported:
            raise Stop("TRANSPORT_UNSUPPORTED", "; ".join(
                f"{role} on {route['provider']}: the conductor does not drive acp roles; "
                "use claude-code or codex for this role" for role, route in unsupported))

    def _preflight(self, item: Item) -> None:
        """Every required role can start before any work is done: an acp route or a missing CLI stops the run now with a
        plain message, not after an hour of executor work (an optional scout or report-fixer is only skipped)."""
        self._refuse_acp(item)
        required = {role: route for role, route in item.routes.items() if role not in self.OPTIONAL_ROLES}
        codex = [(role, route) for role, route in required.items() if self._codex_sandboxed(route)]
        claude = self._sandbox_mode(item) == "require" and any(self._claude_bash(route) for route in required.values())
        blocked = []
        if (codex or claude) and not sandbox.probe()["available"]:  # probed only when a role depends on it
            reason = sandbox.probe()["reason"]
            blocked = [f"{role} on {route['provider']}: the provider sandbox cannot start ({reason})"
                       for role, route in codex]
            if claude:
                blocked.append(f"instructions.sandbox is require, and the sandbox cannot start ({reason})")
        elif claude:  # the sandbox starts, but a CLI that does not list --settings would run the role unconfined
            blocked = [f"{role}: instructions.sandbox is require, and the claude CLI does not list --settings"
                       for role, route in required.items()
                       if self._claude_bash(route) and not self._knows(route["argv"], ["--settings"])]
        if blocked:
            raise Stop("SANDBOX_UNAVAILABLE", "; ".join(blocked))
        off = [f"{role}: {self.provider_disabled(route['provider'])}" for role, route in required.items()
               if self.provider_disabled(route["provider"])]
        if off:
            raise Stop("PROVIDER_UNAVAILABLE", f"cannot start {'; '.join(off)}")
        missing = [f"{role} ({route['argv'][0]})" for role, route in item.routes.items()
                   if role not in self.OPTIONAL_ROLES and not process.available(route["argv"])]
        if missing:
            raise Stop("PROVIDER_UNAVAILABLE", f"cannot start {', '.join(missing)}: install or log in the CLI, then resume")
        gated = [f"{role} on {route['provider']} until {gate['until']}" for role, route in required.items()
                 for gate in [gates.blocked(route["provider"], wall())] if gate]
        if gated:
            raise Stop("PROVIDER_QUOTA", f"{'; '.join(gated)}: the account quota is exhausted; resume after the reset, "
                                         "or remove the gate with conduct.py gates --clear")

    def _route(self, item: Item, role: str, override: Optional[dict] = None) -> dict:
        """The route of ``role``; ``override`` (a ``fallback_routes`` entry or retry.decide's route) replaces the
        provider, the model class and, when it has one, the effort of the stage and drops its model."""
        wanted = opts.stage_route(item.options, role)
        if override:
            wanted = {**{key: value for key, value in wanted.items() if key not in ("provider", "model", "model_class")},
                      **{key: override[key] for key in ("provider", "model_class", "effort") if override.get(key)}}
        if role == "reviewer" and not override:
            selector = opts.parse_selector(item.options["reviewer"])
            provider, model, effort = selector["provider"], selector["model"], selector.get("effort")
        else:
            provider = wanted.get("provider") or self.conductor.get("provider") or "claude-code"
            model, effort = wanted.get("model"), wanted.get("effort")
        entry = self._entry(role, provider)
        model_class = wanted.get("model_class") or entry["model_class"]
        if role == "executor" and not effort:
            effort = (item.claim.get("route") or {}).get("effort")
        effort = effort or entry["effort"]
        if entry["model_set"] == "supported" and not model:
            planned = next((stage for stage in item.launch_plan.get("stages", [])
                            if LAUNCH_ROLE.get(stage.get("role"), stage.get("role")) == LAUNCH_ROLE.get(role, role)
                            and stage.get("provider") == provider and stage.get("model")
                            and not wanted.get("model_class")), None)
            try:
                model = planned["model"] if planned else self._catalog_get().resolve_model(provider, model_class)
            except catalogs.CatalogError as error:
                raise Stop(error.code, str(error)) from None
        values = {"model": model or "", "effort": effort, "cwd": str(self.project), "orch": str(ORCH_ROOT)}
        argv_override = (self.conductor.get("argv") or {}).get(role)
        try:
            if argv_override:
                argv = catalogs.substitute(list(argv_override), values)
            elif effort not in launch.EFFORTS:
                raise Stop("ROUTE_UNDERSHOOT", f"{role} needs effort {effort}, which {provider} cannot start")
            else:
                argv = launch.build_argv(launch.load_catalog(), LAUNCH_ROLE.get(role, role), provider, model=model,
                                         effort=effort, cwd=self.project)
        except launch.LaunchError as error:
            raise Stop(error.code, str(error)) from None
        # A role is never stopped for being long: both ceilings (``stage_timeout_s``, ``stage_idle_timeout_s``) are off
        # unless asked for, and beacons report a long or silent run. A ``text`` role writes only at its end, so the
        # catalog timeout stays its ceiling.
        limits, streaming = item.options["limits"], entry["transport"] != "text"
        timeout = limits.get("stage_timeout_s") or (0 if streaming else entry["timeout_s"])
        idle = limits.get("stage_idle_timeout_s", 0) if streaming else 0
        return {"role": role, "provider": provider, "model": model, "effort": effort, "model_class": model_class,
                "transport": entry["transport"], "timeout_s": timeout, "idle_timeout_s": idle, "argv": argv}

    def _route_minimum(self, item: Item, route: Optional[dict] = None) -> None:
        minimum = item.claim.get("route") or {}
        route = route or item.routes["executor"]
        if minimum.get("class") and CLASS_RANK.get(route["model_class"], -1) < CLASS_RANK[minimum["class"]]:
            raise Stop("ROUTE_UNDERSHOOT", f"the executor class {route['model_class']} is below "
                                           f"{minimum['class']} required by {item.ref}")
        if minimum.get("effort") and EFFORT_RANK.get(route["effort"], -1) < EFFORT_RANK[minimum["effort"]]:
            raise Stop("ROUTE_UNDERSHOOT", f"the executor effort {route['effort']} is below "
                                           f"{minimum['effort']} required by {item.ref}")

    @staticmethod
    def label(route: dict) -> str:
        return "/".join(part for part in (route.get("provider"), route.get("model"), route.get("effort")) if part)

    def _actor(self, role_route: dict) -> dict:
        return {key: role_route[key] for key in ("provider", "model", "effort") if role_route.get(key)}

    # ------------------------------------------------------------------ model stages

    def _role(self, item: Item, key: str, role: str, prompt: str, kind: Optional[str],
              extra: Optional[Callable[[dict], list]] = None, cancel=None) -> tuple:
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
        trail = {"decisions": [], "error": None, "api_retries": 0}
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
            trail["api_retries"] += run.api_retries
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

    def _start_route(self, item: Item, key: str, role: str, route: dict, cancel) -> dict:
        """The route a role starts on: its own unless its provider was gated after the routes of the piece were chosen
        (an earlier role exhausted the account). Then the first admissible fallback route; else, when the gate ends
        within ``limits.provider_wait_max_s``, a wait for it; else ``PROVIDER_QUOTA`` before the call."""
        gate = gates.blocked(route["provider"], wall())
        if gate is None:
            return route
        found, refused = self._fallback(item, role, route)
        until = f"{route['provider']} is gated until {gate['until']} ({gate['class']} {gate['code']}, set by {gate['set_by']})"
        if found is not None:
            item.routes[role] = found
            write_json(item.directory / "routes.json", item.routes)
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(found),
                               reason_code="CAPACITY_GATED", message=f"{role}: {until}")
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(found),
                               reason_code="ROUTE_FALLBACK",
                               message=f"{role}: {self.label(route)} -> {self.label(found)} (CAPACITY_GATED)")
            return found
        left = max(0, calendar.timegm(time.strptime(gate["until"], "%Y-%m-%dT%H:%M:%SZ")) - wall())
        if left <= item.options["limits"].get("provider_wait_max_s", 900):
            self._wait(item, key, role, {"class": gate["class"]}, int(left) + 1, cancel)
            return route
        raise Stop("PROVIDER_QUOTA", f"{role}: {until}" + (f"; no fallback: {'; '.join(refused)}" if refused else "")
                   + "; resume after the reset, or remove the gate with conduct.py gates --clear")

    # ------------------------------------------------------------------ provider failures

    def _provider_failure(self, item: Item, key: str, role: str, route: dict, run, attempts: int, base: Optional[str],
                          first_prompt: str, trail: dict, cancel) -> tuple:
        """``(route, prompt)`` of the next attempt of a role that failed at the provider, or a ``Stop``.

        One ``retry.decide`` call decides (knowledge/provider-errors#flow). The conductor does not multiply repeats: when
        the provider CLI already repeated the request itself (``api_retry`` events) a transient failure is repeated
        only after a pause, and a writing role that left changes in the tree continues from them, never from scratch."""
        error = run.error_doc or {"class": "timeout" if run.error == "TIMEOUT" else "unknown"}
        trail["error"] = error
        limits = item.options["limits"]
        writes = self._writes(role)
        dirty = base is not None and self._tree_mark() != base
        self._gate(item, route, error)
        inputs = retry.RetryInputs(
            error_class=error["class"], stage_writes=writes, worktree_dirty=dirty, receipt_unresolved=False,
            attempts_used=attempts, stage_retries_max=limits["retries"], budget_left=limits["retries"] + 1 - attempts,
            retry_after_s=error.get("retry_after_s"),
            current_route={"provider": route["provider"], "model_class": route["model_class"]},
            max_wait_s=limits.get("provider_wait_max_s", 900))
        policy = {"on_error": {**CONDUCTOR_ON_ERROR, **item.options.get("on_error", {})},
                  "fallback_routes": [entry for entry in item.options.get("fallback_routes", []) if entry["role"] == role]}
        decision = retry.decide(inputs, policy)
        if decision.action == "reconcile" and attempts > limits["retries"]:  # decide does not bound a reconcile
            decision = retry.RetryDecision("stop", decision.reason_codes + ("BUDGET_EXHAUSTED",))
        trail["decisions"].append({"action": decision.action, "reason_codes": list(decision.reason_codes),
                                   **({"wait_s": decision.wait_s} if decision.wait_s is not None else {}),
                                   **({"route": decision.route} if decision.route else {})})
        label = self.label(route)
        self.progress.emit("info", item=item.ref, stage=key, role=role, route=label,
                           message=f"attempt {attempts} failed at the provider ({error['class']}: "
                                   f"{error.get('safe_message') or run.detail}); {decision.action} "
                                   f"({', '.join(decision.reason_codes)})")
        if decision.action == "retry":
            if run.api_retries and error["class"] in TRANSIENT_CLASSES:
                self._wait(item, key, role, error, error.get("retry_after_s") if error.get("retry_after_s") is not None
                           else int(min(JITTER_CAP_S, JITTER_BASE_S * 2 ** (attempts - 1)) * unit_random()), cancel)
            return route, first_prompt
        if decision.action == "retry_after":
            self._wait(item, key, role, error, decision.wait_s, cancel)
            return route, first_prompt
        if decision.action == "reconcile":
            return route, first_prompt + self._continuation(item)
        refused = []
        if decision.action == "fallback_route":
            found, refused = self._fallback(item, role, route, decision.route)
            if found is not None:
                item.routes[role] = found
                item.state.setdefault("route_overrides", {})[role] = {
                    key: found[key] for key in ("provider", "model_class", "effort") if found.get(key)}
                self._save()
                write_json(item.directory / "routes.json", item.routes)
                self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(found),
                                   reason_code="ROUTE_FALLBACK",
                                   message=f"{role}: {label} -> {self.label(found)} ({error['class']}; "
                                           f"{', '.join(decision.reason_codes)})")
                return found, first_prompt
        raise Stop(*self._provider_stop(role, route, run, error, decision, refused))

    def _provider_stop(self, role: str, route: dict, run, error: dict, decision, refused: list) -> tuple:
        code = PROVIDER_STOP_CODES.get(error["class"]) or run.error
        text = f"{role} on {self.label(route)}: {error['class']} ({error.get('safe_message') or run.detail}); " \
               f"{', '.join(decision.reason_codes)}"
        if error["class"] in ("quota", "rate_limit") and error.get("retry_after_s") is not None:
            reset = utc_stamp(wall() + error["retry_after_s"])
            text += f"; the limit resets {reset}, resume after {reset}"
        elif error["class"] in ("quota", "rate_limit"):
            text += "; the reset time is unknown, resume after the limit is lifted"
        if refused:
            text += f"; no admissible fallback route: {'; '.join(refused)}"
        return code, text

    def _gate(self, item: Item, route: dict, error: dict) -> None:
        """Remember an exhausted account quota with a known reset on the machine: nobody starts the provider again
        before it (``gates.py``). A gate that cannot be written does not stop the run."""
        if error["class"] != "quota" or error.get("retry_after_s") is None or error.get("scope") != "account":
            return
        now = wall()
        try:
            gates.set_gate(route["provider"], until=now + error["retry_after_s"], code=error.get("code", "PROVIDER_QUOTA"),
                           run_id=self.run_id, now=now)
        except (gates.GateError, OSError) as failure:
            self.progress.emit("info", item=item.ref, reason_code="GATE_NOT_WRITTEN",
                               message=f"the capacity gate of {route['provider']} was not written: {failure}")

    def _wait(self, item: Item, key: str, role: str, error: dict, seconds: int, cancel) -> None:
        """Wait ``seconds`` before the repeat (a ``PROVIDER_WAIT`` beacon names the class, the wait and the reset)."""
        if seconds <= 0:
            return
        reset = utc_stamp(wall() + seconds)
        self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="PROVIDER_WAIT",
                           message=f"{role}: {error['class']}; waiting {seconds} s, until {reset}")
        self._pause(seconds, cancel)

    @staticmethod
    def _pause(seconds: float, cancel=None) -> None:
        """Sleep ``seconds``, looking at ``cancel`` every second."""
        remaining = float(seconds)
        while remaining > 0:
            if cancel is not None and cancel.is_set():
                raise Stop("REVIEW_CANCELLED", "cancelled while waiting for the provider: the checks are red")
            step = min(1.0, remaining)
            sleep(step)
            remaining -= step

    @staticmethod
    def _writes(role: str) -> bool:
        """Whether the role may change files (``tools.filesystem`` of its manifest); a role without a manifest might."""
        try:
            manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return True
        return (manifest.get("tools") or {}).get("filesystem") == "write"

    def _tree_mark(self) -> str:
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

    def _continuation(self, item: Item) -> str:
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

    @staticmethod
    def _closed(text: str, kind: str, extra) -> tuple:
        """``(document, healed, issues)`` of the result block in ``text``."""
        doc, error = prompts.json_block(text, kind)
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

    def _repair(self, item: Item, key: str, kind: str, extra, answer: str, issues: list, doc, healed) -> tuple:
        """The report-fixer rewrites the result block from the role's own answer; ``(doc, healed, issues, route)``."""
        if item.options["limits"]["repairs"] <= 0 or "report-fixer" not in item.routes:
            return doc, healed, issues, None
        route = item.routes["report-fixer"]
        if self.provider_disabled(route["provider"]) or not process.available(route["argv"]):
            return doc, healed, issues, None
        for number in range(1, item.options["limits"]["repairs"] + 1):
            problem = "; ".join(issues[:5])
            prompt = prompts.report_fixer(kind=kind, problem=problem, answer=answer, item=item.ref, step=key)
            raw = item.directory / "streams" / f"{key}-fix{number}.jsonl"
            (item.directory / "prompts" / f"{key}-fix{number}.md").write_text(prompt, encoding="utf-8")
            run = process.run_role(self._role_argv(item, "report-fixer", route), prompt, transport=route["transport"],
                                   cwd=self.project, timeout_s=route["timeout_s"], raw_path=raw,
                                   env=self._role_env(item, "report-fixer", route))
            self._tokens(item, run.usage)
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

    def _beacons(self, item: Item, key: str, role: str, raw: Path) -> Callable:
        """The tick of a running role: a STAGE_SLOW beacon every ``stage_warn_s`` and a STAGE_IDLE one every
        ``stage_idle_warn_s`` of silence, each saying what the role runs now. Nothing is stopped."""
        limits = item.options["limits"]
        warn, idle_warn = limits.get("stage_warn_s", 0), limits.get("stage_idle_warn_s", 0)
        marks = {"slow": warn, "idle": idle_warn}

        def tick(elapsed: float, idle: float, pid: int) -> None:
            self._run_clock(item)
            if warn and elapsed >= marks["slow"]:
                marks["slow"] += warn
                self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STAGE_SLOW",
                                   message=f"running {human_duration(elapsed)}; {process.activity(pid, raw)}")
            if idle_warn:
                if idle < idle_warn:
                    marks["idle"] = idle_warn
                elif idle >= marks["idle"]:
                    marks["idle"] += idle_warn
                    self.progress.emit("info", item=item.ref, stage=key, role=role, reason_code="STAGE_IDLE",
                                       message=f"no output for {human_duration(idle)} (running {human_duration(elapsed)}); "
                                               f"{process.activity(pid, raw)}")
        return tick

    # The environment that keeps a provider's project instructions (the repository CLAUDE.md, the project memory) out of
    # a role process. Claude Code reads both by itself; grok was probed and does not read the repository CLAUDE.md; codex
    # would need its own CODEX_HOME (not used by a run so far).
    ISOLATION_ENV = {"claude-code": {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}}

    # Arguments that start a role with no customizations at all: no CLAUDE.md, project memory, plugins, MCP servers, user
    # skills or hooks (a measured start-up context of 6 K instead of 16 K tokens, and none of the developer-session rules).
    ISOLATION_ARGS = {"claude-code": ["--safe-mode"]}

    def _role_argv(self, item: Item, role: str, route: dict) -> list:
        isolated = role in item.options["instructions"]["isolate_roles"]
        extra = self.ISOLATION_ARGS.get(route.get("provider")) if isolated else None
        if extra and not self._knows(route["argv"], extra):
            extra = None
        return list(route["argv"]) + (extra or []) + self._sandbox_args(item, role, route)

    @staticmethod
    def _sandbox_mode(item: Item) -> str:
        return item.options["instructions"].get("sandbox", "prefer")

    @staticmethod
    def _claude_bash(route: dict) -> bool:
        """A Claude Code role that can run shell commands, the only commands the Claude sandbox confines."""
        argv = route["argv"]
        return route.get("provider") == "claude-code" and "--tools" in argv[:-1] \
            and "Bash" in argv[argv.index("--tools") + 1].split(",")

    @staticmethod
    def declared_network(role: str) -> str:
        """``tools.network`` of the role manifest: what the role is meant to reach (``none`` when it has no manifest)."""
        try:
            manifest = json.loads((ORCH_ROOT / "roles" / f"{role}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "none"
        return (manifest.get("tools") or {}).get("network", "none")

    def _sandbox_args(self, item: Item, role: str, route: dict) -> list:
        """``--settings`` with only the ``sandbox`` block for a Claude Code role with Bash (the provider merges it with
        the user's settings). A sandbox that cannot start never leaves the commands unconfined silently: ``prefer``
        says so once and goes on under the filesystem guard, ``require`` was stopped in the preflight."""
        mode = self._sandbox_mode(item)
        if mode == "off" or not self._claude_bash(route):
            return []
        probed = sandbox.probe()
        if not probed["available"]:
            if mode == "prefer" and not self._sandbox_noted and self.progress is not None:
                self._sandbox_noted = True
                self.progress.emit("info", reason_code="ISOLATION_PARTIAL",
                                   message=f"sandbox unavailable: {probed['reason']}; the commands of claude-code roles "
                                           "run under the filesystem guard only")
            return []
        if not self._knows(route["argv"], ["--settings"]):
            return []
        block = {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True}
        if self.declared_network(role) != "allowed":
            block["network"] = {"strictAllowlist": True,
                                "allowedDomains": list(item.options["instructions"].get("sandbox_domains") or [])}
        return ["--settings", json.dumps({"sandbox": block}, sort_keys=True)]

    _sandbox_noted = False

    _KNOWN: dict = {}

    def _knows(self, argv: list, flags: list) -> bool:
        """Whether the provider CLI of ``argv`` lists ``flags`` in its ``--help`` (an older CLI without ``--safe-mode``
        still runs, isolated by the environment only, and the run says so once)."""
        command = next((arg for arg in argv if os.path.basename(arg) in ("claude", "codex", "grok")), None)
        if command is None:  # a test stand-in or a wrapper the conductor does not know: pass the flags as asked
            return True
        key = (command, tuple(flags))
        if key not in self._KNOWN:
            try:
                text = subprocess.run([command, "--help"], capture_output=True, text=True, timeout=20).stdout
            except (OSError, subprocess.SubprocessError):
                text = ""
            self._KNOWN[key] = all(flag in text for flag in flags)
            if not self._KNOWN[key] and self.progress is not None:
                self.progress.emit("info", reason_code="ISOLATION_PARTIAL",
                                   message=f"{command} does not list {' '.join(flags)}; roles are isolated by the environment only")
        return self._KNOWN[key]

    def _role_env(self, item: Item, role: str, route: dict) -> Optional[dict]:
        """The environment of a role process. A role named in ``instructions.isolate_roles`` starts without the project
        instructions: they carry the rules of a developer's own session ("quality over speed", "fix every defect even
        beyond the scope"), which contradict the role's own scope rules; every role gets exactly the instructions of its
        own prompt."""
        extra = self.ISOLATION_ENV.get(route.get("provider")) if role in item.options["instructions"]["isolate_roles"] else None
        if not extra:
            return self.env
        base = dict(os.environ if self.env is None else self.env)
        base.update(extra)
        return base

    def _tokens(self, item: Item, usage: dict) -> None:
        for bucket in (self.state.setdefault("tokens", {"input": 0, "output": 0}),
                       item.state.setdefault("tokens", {"input": 0, "output": 0}), self._step_tokens):
            for key in ("input", "cached", "output"):
                bucket[key] = bucket.get(key, 0) + int(usage.get(key, 0))

    def _budget(self, item: Item) -> None:
        """``tokens_max`` is a beacon: past it a BUDGET_OVER line is printed once per piece, nothing is stopped."""
        limit = item.options["limits"].get("tokens_max") or 0
        tokens = item.state.get("tokens", {})
        used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))  # cache reads are not spend
        if limit and used > limit and not item.state.get("budget_over"):
            item.state["budget_over"] = used
            self._save()
            self.progress.emit("info", item=item.ref, reason_code="BUDGET_OVER",
                               message=f"{item.ref} used {used} fresh tokens, past tokens_max {limit}; the run goes on")

    def _relative(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self.project).as_posix()
        except ValueError:
            return str(path)

    def _scout_stage(self, item: Item) -> Optional[dict]:
        return next((stage for stage in item.policy.get("stages", [])
                     if stage.get("role") in ("scout", "context-scout")), None)

    def _scout(self, item: Item) -> str:
        stage = self._scout_stage(item)
        if stage is None:
            return ""
        route = item.routes["context-scout"]
        gate = gates.blocked(route["provider"], wall())
        disabled = self.provider_disabled(route["provider"])
        if gate or disabled or not process.available(route["argv"]):
            code, why = ("PROVIDER_QUOTA", f"{route['provider']} is gated until {gate['until']}") if gate else \
                ("PROVIDER_DISABLED", disabled.split(": ", 1)[1]) if disabled else \
                ("PROVIDER_UNAVAILABLE", f"{route['argv'][0]} not found")
            if stage.get("on_unavailable") == "skip" and not stage.get("required"):
                self.progress.emit("stage.skip", item=item.ref, stage="scout", role="context-scout",
                                   route=self.label(route), reason_code=code, message=f"{why}; optional stage skipped")
                return ""
            raise Stop(code, f"context-scout on {route['provider']}: {why}")
        key = sha256_hex(canonical_json_bytes({
            "input": item.input_doc.get("digest"),
            "plan": (item.input_doc.get("provenance") or {}).get("source_digest"),
            "route": [route["provider"], route["model"], route["effort"]],
            "role": render.load_role("context-scout", self.roles_dir)[0].get("instructions"),
            "skills": item.options["skills"].get("context-scout", [])}))
        cache = runs_root(self.project) / "cache" / "scout" / safe(item.ref) / f"{key[:32]}.txt"

        def run() -> dict:
            if cache.is_file():
                return {"text": cache.read_text(encoding="utf-8"), "cache": self._relative(cache), "hit": True}
            prompt = prompts.scout(item.input_doc, item=item.ref, step="scout", roles_dir=self.roles_dir,
                                   skills=item.options["skills"].get("context-scout", []),
                                   skill_texts=self._skill_texts(item, "context-scout"))
            text, meta = self._role(item, "scout", "context-scout", prompt, None)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(text, encoding="utf-8")
            return {"text": text, "cache": self._relative(cache), "hit": False, **meta}

        found = self._step(item, "scout", run, role="context-scout", route=self.label(route),
                           verdict=lambda result: "cache" if result.get("hit") else "mapped")
        return found["text"]

    def _execute(self, item: Item, number: int, scout_text: str, correction: str) -> dict:
        route = item.routes["executor"]
        key = f"executor.{number}"

        def run() -> dict:
            if number > 1:
                self._refresh_input(item)
            prompt = prompts.executor(item.input_doc, item=item.ref, step=key, scout_text=scout_text,
                                      rules=item.options["rules"], correction=correction, roles_dir=self.roles_dir,
                                      targeted_tests=not item.options["checks"]["executor_runs_checks"],
                                      skills=item.options["skills"].get("executor", []),
                                      repo_rules=self._repo_rules(item, "executor"),
                                      skill_texts=self._skill_texts(item, "executor"))
            report, meta = self._role(item, key, "executor", prompt, "stage-report", extra=report_problems)
            write_json(item.directory / "reports" / f"{key}.json", report)
            return {"report": report, "changed": self._changed_now(item), **meta}

        found = self._step(item, key, run, role="executor", route=self.label(route),
                           verdict=lambda result: result["report"]["status"])
        report = found["report"]
        outside = self._outside(item)
        if outside and report["status"] != "blocked" and item.options["scope"]["outside"] == "block":
            report = self._blocked(report, "OUTSIDE_WRITE_SET", "the executor changed paths the write set does not own: "
                                   + ", ".join(outside[:20]) + "; widen the write set in the plan or set them aside, then retry")
        return report

    # ------------------------------------------------------------------ what the roles really changed

    def _changed_now(self, item: Item) -> list:
        """The paths the roles have changed so far: the dirty tree without what the work source wrote when it claimed,
        the artifact folder, the plan folder of the input and the conductor reports."""
        source = set(item.state.get("source_paths") or [])
        return [path for path in scopes.own(self._dirty_paths(), self._not_the_role(item)) if path not in source]

    def _not_the_role(self, item: Item) -> list:
        """Folders whose changes are never the role's work: the conductor reports, the artifact folder of the piece
        and the plan folder of the input."""
        return [REPORTS.as_posix(), self._relative(item.artifacts) if item.artifacts else "",
                str((item.input_doc.get("provenance") or {}).get("plan_dir") or "")]

    def _changed(self, item: Item) -> list:
        """Every path any executor round of the piece changed (git, not the reports)."""
        steps = item.state.get("steps", {})
        found = set(item.state.get("adopted") or [])
        for key, step in steps.items():
            if key.startswith("executor.") and isinstance(step.get("result"), dict):
                found.update(step["result"].get("changed") or [])
        return sorted(found)

    def _outside(self, item: Item) -> list:
        return scopes.outside(self._changed(item), (item.input_doc.get("scope") or {}).get("write_set"))

    def _adopted(self, item: Item) -> list:
        """``run --adopt``: the changed paths taken over must lie in the write set of the piece. The artifact folder of
        the piece (evidence, review verdict of the earlier attempt) and the plan folder are allowed and are not
        counted as the role's changes."""
        adopted = scopes.own(item.state.get("adopted") or [], self._not_the_role(item))
        item.state["adopted"] = adopted
        stray = scopes.outside(adopted, (item.input_doc.get("scope") or {}).get("write_set"))
        if stray:
            raise Stop("WORKTREE_DIRTY", f"run --adopt takes only changes inside the write set of {item.ref}; outside it: "
                                         + ", ".join(stray[:10]))
        return adopted

    def _refresh_input(self, item: Item) -> None:
        """A plan amended during the piece (a wider write set, a fixed check) reaches the next executor round: the brief
        is asked again and, when its digest changed, replaces the input of every later step."""
        code, answer, _ = self._orch("source", "brief", "--run", item.orch_run)
        if code != 0 or not isinstance(answer, dict) or not answer.get("input_ref"):
            return
        try:
            doc = json.loads(blobs.read_bytes(answer["input_ref"], project=self.project))
        except (OSError, ValueError, KeyError):
            return
        if doc.get("digest") and doc.get("digest") != item.input_doc.get("digest"):
            write_json(item.directory / "input.json", doc)
            item.input_doc = doc
            self.progress.emit("info", item=item.ref, reason_code="INPUT_REBUILT",
                               message=f"the plan changed during the piece: input {answer.get('input_id', '-')} is used from now on")

    # ------------------------------------------------------------------ what an isolated role still needs to know

    def _repo_rules(self, item: Item, role: str) -> str:
        """The instruction sections of ``instructions.module_rules`` from the CLAUDE.md (else AGENTS.md) of the
        repository root and of every folder on the way to a write-set path. An isolated role does not read those
        files, and the rest of them are the rules of a developer's session, not of this role."""
        wanted = item.options["instructions"].get("module_rules") or []
        if not wanted:
            return ""
        folders = {Path(".")}
        for pattern in (item.input_doc.get("scope") or {}).get("write_set") or []:
            fixed = []
            for part in str(pattern).split("/")[:-1]:
                if any(mark in part for mark in "*?["):
                    break
                fixed.append(part)
            for depth in range(1, len(fixed) + 1):
                folders.add(Path(*fixed[:depth]))
        lines, size = [], 0
        for folder in sorted(folders, key=lambda path: (len(path.parts), str(path))):
            carrier = next((self.project / folder / name for name in ("CLAUDE.md", "AGENTS.md")
                            if (self.project / folder / name).is_file()), None)
            if carrier is None:
                continue
            text = carrier.read_text(encoding="utf-8", errors="replace")
            heads = list(RULE_HEADING.finditer(text))
            for index, head in enumerate(heads):
                name = head.group(1)
                if not any(name == rule or name.endswith("." + rule) for rule in wanted):
                    continue
                body = text[head.end():heads[index + 1].start() if index + 1 < len(heads) else len(text)]
                body = " ".join(body.split())
                if body and size + len(body) < 4000:
                    lines.append(f"- `{name}` ({self._relative(carrier)}): {body}")
                    size += len(body)
        return "\n".join(lines)

    def _skill_texts(self, item: Item, role: str) -> dict:
        """The text of the skills a role is given, when the role runs isolated (its provider then loads no skill by
        name): the SKILL.md of the project's skill folders, without its front matter."""
        names = item.options["skills"].get(role, [])
        if not names or role not in item.options["instructions"]["isolate_roles"]:
            return {}
        texts = {}
        for name in names:
            for folder in (".claude/skills", ".agents/skills"):
                path = self.project / folder / name / "SKILL.md"
                if path.is_file():
                    body = path.read_text(encoding="utf-8", errors="replace")
                    if body.startswith("---"):
                        end = body.find("\n---", 3)
                        body = body[end + 4:] if end != -1 else body
                    texts[name] = body.strip()[:12000]
                    break
        return texts

    @staticmethod
    def _red_before(item: Item, number: int) -> list:
        """The checks that were red in the latest earlier round, when ``checks.red_first`` asks to run them first."""
        if not item.options["checks"]["red_first"]:
            return []
        steps = item.state.get("steps", {})
        for earlier in range(number - 1, 0, -1):
            rows = (steps.get(f"checks.{earlier}") or {}).get("result")
            if rows:
                return [row["id"] for row in rows if not row.get("green") and not row.get("skipped")]
        return []

    def _compute_checks(self, item: Item, number: int, report: dict, on_result=None) -> list:
        """The rows of the checks of one round; touches no run state, so it may run beside a model role."""
        try:
            return checks_mod.run_checks(
                item.input_doc, project=self.project, evidence_dir=item.artifacts / "evidence",
                log_dir=item.directory / "checks" / str(number),
                timeout_s=item.options["limits"]["check_timeout_s"],
                evidence_prefix=f"{self.run_id}:{item.ref}:checks.{number}", report=report,
                executor=self._actor(item.routes["executor"]), parallel=item.options["checks"]["parallel"],
                on_result=on_result, first=self._red_before(item, number), kinds=tuple(item.options["checks"]["kinds"]),
                cadence=tuple(item.options["checks"]["cadence"]), warn_s=item.options["limits"].get("check_warn_s", 0),
                on_slow=lambda check_id, elapsed, pid: self._check_tick(item, number, check_id, elapsed, pid))
        except (RuntimeError, ValueError, OSError) as error:
            raise Stop("CHECKS_FAILED", str(error)) from None

    def _check_tick(self, item: Item, number: int, check_id: str, elapsed: float, pid: int) -> None:
        self.progress.emit("info", item=item.ref, stage=f"checks.{number}", reason_code="CHECK_SLOW",
                           message=f"{check_id} running {human_duration(elapsed)}; {process.activity(pid, Path(os.devnull))}")
        self._run_clock(item, stop=False)

    def _run_checks(self, item: Item, number: int, report: dict, computed=None) -> list:
        """The step ``checks.N``; ``computed`` is a future of the rows started earlier (the overlap with the review)."""
        key = f"checks.{number}"

        def run() -> list:
            return computed.result() if computed is not None else self._compute_checks(item, number, report)

        def said(rows: list) -> str:
            red = [row["id"] for row in rows if not row["green"]]
            return "green" if not red else "red " + ",".join(red)

        return self._step(item, key, run, verdict=said)

    def _checks_then_review(self, item: Item, report: dict, checks_no: int, review_no: int) -> list:
        """With ``checks.overlap_review`` the checks of a round run while the review of that candidate reads it. When the
        checks are red the review read a candidate that is about to change: its step is dropped and made again later."""
        steps = item.state.setdefault("steps", {})
        if steps.get(f"checks.{checks_no}", {}).get("status") == "done" \
                or steps.get(f"review.{review_no}", {}).get("status") == "done":
            return self._run_checks(item, checks_no, report)
        cancel = threading.Event()  # a red check ends the review at once: it reads a candidate that is about to change
        with ThreadPoolExecutor(max_workers=1) as pool:
            computed = pool.submit(self._compute_checks, item, checks_no, report,
                                   lambda row: None if row.get("green") else cancel.set())
            try:
                self._review(item, review_no, [], pending=True, cancel=cancel)
            except Stop as stop:
                if stop.code != "REVIEW_CANCELLED":
                    if computed.exception() is None:  # the checks ran to the end: keep them for the resume
                        self._run_checks(item, checks_no, report, computed=computed)
                    raise
            finally:
                computed.exception()  # wait for the checks before the pool closes, whatever the review did
        rows = self._run_checks(item, checks_no, report, computed=computed)
        if not all(row["green"] for row in rows):
            if steps.get(f"review.{review_no}", {}).get("status") == "done":
                self._carry_review(item, review_no)
            else:
                steps.pop(f"review.{review_no}", None)
                self.progress.emit("info", item=item.ref, message="the checks are red: the parallel review is dropped "
                                                                   "and repeated after the correction")
        return rows

    def _carry_review(self, item: Item, review_no: int) -> None:
        """The review finished before the red checks: keep it. Its confirmed findings at the floor go into the same
        correction as the red checks (one executor round, not two), and the next audit is the pre-final one."""
        findings = item.state["steps"][f"review.{review_no}"]["result"]["findings"]
        major = []
        if findings["findings"]:
            triage = self._triage(item, review_no, findings)
            major, minor = self._split_confirmed(item, findings, triage)
            self._defer_minor(item, findings, minor)
            if major:
                item.state["combined"] = {"review": review_no,
                                          "text": prompts.review_correction(findings, dict(triage, confirmed=major))}
        self.progress.emit("info", item=item.ref, message=f"the checks are red but review {review_no} is done: its "
                                                          f"{len(major)} finding(s) to correct go into the same correction")

    def _review_enabled(self, item: Item) -> bool:
        review = item.policy.get("review") or {}
        return bool(review.get("enabled")) and item.options["limits"]["review_rounds"] > 0

    @staticmethod
    def _closer_named(item: Item) -> bool:
        """A model records the result (closing stage) only when a layer of the options names the registrar."""
        return bool(opts.stage_route(item.options, "registrar"))

    def _triage_role(self, item: Item) -> str:
        triage = (item.policy.get("review") or {}).get("triage") or {}
        return triage.get("role") or "triager"

    @staticmethod
    def _corrected(item: Item, previous: int) -> list:
        """The confirmed findings of review round ``previous`` that the correction after it had to fix."""
        steps = item.state.get("steps", {})
        findings = ((steps.get(f"review.{previous}") or {}).get("result") or {}).get("findings") or {}
        triage = ((steps.get(f"triage.{previous}") or {}).get("result") or {}).get("triage") or {}
        by_id = {found.get("id"): found for found in findings.get("findings", [])}
        return [dict(by_id.get(entry["finding"], {}), id=entry["finding"], fix=entry.get("fix", ""))
                for entry in triage.get("confirmed", [])]

    def _review(self, item: Item, number: int, rows: list, pending: bool = False, cancel=None) -> dict:
        route = item.routes["reviewer"]
        key = f"review.{number}"

        def run() -> dict:
            base = checks_mod.head(self.project)  # not the claim-time base: commits made meanwhile are not the candidate
            corrected = self._corrected(item, number - 1) if number > 1 and item.options["review"]["audit_scope"] == "corrected" else []
            prompt = prompts.reviewer(item.input_doc, item=item.ref, step=key, base=base, corrected=corrected,
                                      diff=checks_mod.diff(self.project, base), checks=rows, round_no=number,
                                      pre_final=number > 1 and item.options["review"]["pre_final"],
                                      min_severity=item.options["review"]["correct_min_severity"],
                                      roles_dir=self.roles_dir, skills=item.options["skills"].get("reviewer", []),
                                      checks_pending=pending, outside=self._outside(item),
                                      repo_rules=self._repo_rules(item, "reviewer"),
                                      skill_texts=self._skill_texts(item, "reviewer"))
            findings, meta = self._role(item, key, "reviewer", prompt, "review-findings", extra=findings_problems,
                                        cancel=cancel)
            return {"findings": findings, **meta}

        found = self._step(item, key, run, role="reviewer", route=self.label(route),
                           verdict=lambda result: f"{result['findings']['verdict']} "
                                                  f"{len(result['findings']['findings'])} finding(s)")
        self._verdict_file(item)
        return found["findings"]

    def _triage(self, item: Item, number: int, findings: dict) -> dict:
        role = self._triage_role(item)
        route = item.routes[role]
        key = f"triage.{number}"

        def run() -> dict:
            base = checks_mod.head(self.project)  # not the claim-time base: commits made meanwhile are not the candidate
            prompt = prompts.triager(item.input_doc, item=item.ref, step=key, base=base, findings=findings,
                                     roles_dir=self.roles_dir, skills=item.options["skills"].get(role, []),
                                     repo_rules=self._repo_rules(item, role), skill_texts=self._skill_texts(item, role))
            triage, meta = self._role(item, key, role, prompt, "triage-result",
                                      extra=lambda doc: contract.triage_problems(findings, doc))
            return {"triage": triage, **meta}

        found = self._step(item, key, run, role=role, route=self.label(route),
                           verdict=lambda result: f"confirmed {len(result['triage']['confirmed'])}, "
                                                  f"rejected {len(result['triage']['rejected'])}")
        self._verdict_file(item)
        self._note_rejected(item, findings, found["triage"])
        return found["triage"]

    def _verdict_file(self, item: Item) -> None:
        """``review-verdict.json`` in the item's artifacts: the short committed record of every review round; the
        streams stay in the ignored runtime folder."""
        steps = item.state.get("steps", {})
        rounds = []
        number = 1
        while f"review.{number}" in steps:
            review = steps[f"review.{number}"]["result"]
            triage = (steps.get(f"triage.{number}") or {}).get("result") or {}
            triaged = triage.get("triage") or {}
            reproduced = {entry["finding"]: entry["reproduction"] for entry in triaged.get("confirmed", [])}
            route = item.routes.get("reviewer", {})
            rounds.append({
                "round": number, "provider": route.get("provider"), "model": review.get("model") or route.get("model"),
                "effort": route.get("effort"), "session": review.get("session"),
                "verdict": review["findings"]["verdict"],
                "findings": [{**finding, **({"triage_reproduction": reproduced[finding["id"]]}
                                            if finding["id"] in reproduced else {})}
                             for finding in review["findings"]["findings"]],
                "triage": {"confirmed": [entry["finding"] for entry in triaged.get("confirmed", [])],
                           "rejected": [{"finding": entry["finding"], "reason": entry["reason"]}
                                        for entry in triaged.get("rejected", [])],
                           "session": triage.get("session")} if triage else None,
                "stream": review.get("stream")})
            number += 1
        doc = {"schema": "orch-conductor-review-verdict/v1", "item": item.ref, "run": self.run_id,
               "selector": item.options.get("reviewer"), "rounds": rounds}
        write_json(item.artifacts / "review-verdict.json", doc)

    # ------------------------------------------------------------------ registration and commit

    def _close(self, item: Item, args: list) -> Optional[dict]:
        """The closing stage: a model registrar records the result with the one command built here. The conductor
        registers the result again right after: a repeat is a no-op when the closer did it, and it records the result
        when the closer could not (``close`` then says ``conductor`` and why), so the closing never loses a result."""
        route = item.routes["registrar"]
        # ``python3`` as a bare name: the launch catalog allows the registrar exactly ``python3 *orch.py source register *``.
        argv = ["python3", str(ORCH_ROOT / "scripts" / "orch.py"), *args]
        if self.config_file:  # an invocation config before the verb is outside that allowance: the closer is refused
            argv[2:2] = ["--config", str(self.config_file)]

        def run() -> dict:
            prompt = prompts.closer(item=item.ref, step="close", command=shlex.join(argv))
            try:
                text, meta = self._role(item, "close", "registrar", prompt, None)
            except Stop as stop:
                return {"by": "conductor", "reason_code": stop.code, "message": stop.message}
            return {"by": "closer", "answer": text[-1500:], **meta}

        found = self._step(item, "close", run, role="registrar", route=self.label(route),
                           verdict=lambda result: "closer ran" if result["by"] == "closer"
                           else f"closer failed ({result['reason_code']}); the conductor records")
        return found

    def _finish(self, item: Item, report: dict, rows: Optional[list]) -> str:
        changed = self._changed(item)
        if changed or any("changed" in (step.get("result") or {}) for key, step in item.state.get("steps", {}).items()
                          if key.startswith("executor.") and isinstance(step.get("result"), dict)):
            report = dict(report, changed_paths=changed)  # git, not the report of the last round
        outside = self._outside(item)
        if outside and report["status"] != "blocked":
            issue = {"text": "changed outside the write set: " + ", ".join(outside)[:800], "kind": "deviation",
                     "impact": "the commit takes these paths with the piece; the reviewer saw them",
                     "next": "widen the write set of later items like this one"}
            report = dict(report, status="done_with_deviations",
                          open_issues=list(report.get("open_issues", [])) + [issue])
        notes = self._notes(item)
        if notes:
            report = dict(report, open_issues=list(report.get("open_issues", [])) + notes)
        status = report["status"]
        write_json(item.artifacts / "stage-report.json", report)
        body = {key: value for key, value in report.items() if key != "status"}
        if status != "blocked":
            body["open_issues"] = [issue for issue in body["open_issues"] if issue["kind"] != "escalation"]
        else:  # a blocked registration takes no deviation issue (the register verb pairs it with done_with_deviations)
            body["open_issues"] = [dict(issue, kind="difficulty", text=f"deviation: {issue['text']}")
                                   if issue["kind"] == "deviation" else issue for issue in body["open_issues"]]
        report_path = write_json(item.directory / "register-report.json", body)
        evidence = {row["id"]: row["evidence"] for row in rows or [] if row.get("evidence") and row["kind"] == "acceptance"}
        executor = self._actor(item.routes["executor"])
        registrar = self.conductor.get("registrar") or "orch/conductor"

        args = ["source", "register", "--run", item.orch_run, "--report", str(report_path), "--status", status,
                "--actor", registrar, "--executed-by", self.label(executor)]
        for check_id, path in sorted(evidence.items()):
            args += ["--evidence", f"{check_id}={path}"]
        closed = self._close(item, args) if self._closer_named(item) else None

        def register() -> dict:
            code, answer, err = self._orch(*args)
            if code == 3:
                raise Stop("WORK_SOURCE_UNAVAILABLE", err or "no work source")
            if not isinstance(answer, dict) or answer.get("outcome") not in ("recorded", "no-op"):
                reason = (answer or {}).get("reason_code") or "REGISTER_REFUSED"
                raise Stop("REGISTER_REFUSED", f"{reason}: {(answer or {}).get('message') or err}")
            return {"outcome": answer["outcome"], "gate": (answer.get("gate") or {}).get("verdict")}

        def said(result: dict) -> str:
            by_closer = closed is not None and closed["by"] == "closer" and result["outcome"] == "no-op"
            note = " (recorded by the closer)" if by_closer else ""
            return f"{result['outcome']} gate {result['gate']}{note}"

        self._step(item, "register", register, role="registrar", route=registrar, verdict=said)
        # A blocked piece is committed only under on_blocked = "report" and only when it changed nothing: then its
        # records (artifacts, the source's state) are all there is, and the next piece starts on a clean tree.
        records_only = status == "blocked" and item.options["on_blocked"] == "report" \
            and not report.get("changed_paths")
        if status == "blocked" and not records_only:
            item.state["partial"] = bool(report.get("changed_paths"))
        if (status != "blocked" or records_only) and item.policy.get("git_action") == "commit":
            paths = sorted(set(report.get("changed_paths", [])) | {self._relative(item.artifacts) + "/"})

            def commit() -> dict:
                args = ["source", "commit", "--run", item.orch_run]
                for path in paths:
                    args += ["--path", path]
                code, answer, err = self._orch(*args)
                if code == 3:
                    raise Stop("WORK_SOURCE_UNAVAILABLE", err or "no work source")
                if not isinstance(answer, dict) or answer.get("outcome") not in ("committed", "no-op"):
                    reason = (answer or {}).get("reason_code") or "COMMIT_REFUSED"
                    raise Stop("COMMIT_REFUSED", f"{reason}: {(answer or {}).get('message') or err}")
                return {"outcome": answer["outcome"], "sha": answer.get("sha")}

            self._step(item, "commit", commit, verdict=lambda result: f"{result['outcome']} {result.get('sha') or ''}".strip())
        return status


def report_problems(report: dict) -> list:
    """What the closed stage-report cannot say: deviations without a deviation issue, a blocked report without an
    escalation, an escalation in a report that is not blocked."""
    kinds = {issue["kind"] for issue in report.get("open_issues", [])}
    issues = []
    if report["status"] == "done_with_deviations" and "deviation" not in kinds:
        issues.append("/status: done_with_deviations needs a deviation issue")
    if report["status"] == "blocked" and "escalation" not in kinds:
        issues.append("/status: blocked needs an escalation issue naming what is missing")
    if report["status"] != "blocked" and "escalation" in kinds:
        issues.append("/open_issues: an escalation belongs to a blocked report")
    return issues


def findings_problems(findings: dict) -> list:
    ids = [item["id"] for item in findings.get("findings", [])]
    issues = [f"/findings: id {name} repeats" for name in sorted(set(ids)) if ids.count(name) > 1]
    if findings["verdict"] == "GREEN" and any(item["severity"] in ("Blocker", "Major") for item in findings["findings"]):
        issues.append("/verdict: GREEN with a Blocker or Major finding")
    if findings["verdict"] != "GREEN" and not findings["findings"]:
        issues.append(f"/verdict: {findings['verdict']} without findings")
    return issues
