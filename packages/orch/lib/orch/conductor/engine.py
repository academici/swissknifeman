"""The conductor loop: claim, brief, prepare, then the stages of one piece of work, registration and the commit.

Every step of a piece of work has a key (``brief``, ``prepare``, ``scout``, ``executor.1``, ``checks.1``,
``review.1``, ``triage.1``, ``register``, ``commit``) and is recorded in ``state.json`` once it closes. ``resume``
runs the same loop again: a closed step returns its recorded result and is not executed twice, so the loop takes
the same path up to the step that did not close. The work source is reached only through ``orch.py source``; the
roles only through the launch catalog (or ``[orch.conductor.argv]``) and see the execution-input, never the plan.

The conductor stops only on: a blocked piece of work (``on_blocked = "stop"``), red checks or confirmed findings
after the correction limits, an exhausted token budget, a route below the minimum of the work, an unavailable
provider or role, a refusal of the work source, or a dirty working tree before new work. Anything else goes on.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
from typing import Any, Callable, Optional

from aicore.state import blobs, project_state_dir
from aicore.util.digest import canonical_json_bytes, sha256_hex

from orch import catalog as catalogs, events, launch, policies, render
from orch.conductor import checks as checks_mod, contract, observer, options as opts, process, prompts
from orch.conductor.progress import Progress
from orch.settings import ORCH_ROOT

CLASS_RANK = {"economy": 0, "implementation": 1, "frontier": 2}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4, "ultra": 5}
LAUNCH_ROLE = {"context-scout": "scout"}
RUN_FILE, STATE_FILE = "run.json", "state.json"
REPORTS = Path(".swissknifeman") / "orch" / "reports"
STATUS_EXIT = {"finished": 0, "stopped": 1}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class Stop(Exception):
    """An honest stop of the run: a stable code and what happened."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


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


class Conductor:
    """One conductor run in a project (a git repository)."""

    def __init__(self, *, project: Path, settings, config_file: Optional[Path] = None, mode: str = "text",
                 stream=None, model_catalog: Optional[Path] = None, roles_dir: Optional[Path] = None,
                 env: Optional[dict] = None, clock: Optional[Callable[[], str]] = None):
        self.project = Path(project).resolve()
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
        argv = [sys.executable, str(ORCH_ROOT / "scripts" / "orch.py")]
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
            options_file: Optional[Path] = None) -> int:
        run_id = new_run_id()
        run_doc = {"run_id": run_id, "plan": plan, "plans_root": plans_root, "items": list(items), "batch": batch,
                   "max_items": max_items, "options_file": str(options_file) if options_file else None,
                   "config_file": str(self.config_file) if self.config_file else None, "created": utc_now(),
                   "project": str(self.project)}
        self._open(run_id, run_doc, {"status": "running", "items": {}, "claims": {}, "tokens": {"input": 0, "output": 0}})
        write_json(self.directory / RUN_FILE, run_doc)
        self._save()
        self.progress.emit("run.start", message=f"plan {plan}; " + (f"items {', '.join(items)}" if items else
                                                                     f"batch, at most {max_items or 'all'}"))
        return self._loop()

    def resume(self, run_id: str) -> int:
        directory = runs_root(self.project) / run_id
        run_doc, state = read_json(directory / RUN_FILE), read_json(directory / STATE_FILE)
        if run_doc is None or state is None:
            raise Stop("RUN_UNKNOWN", f"no conductor run {run_id} in {directory.parent}")
        if run_doc.get("config_file") and not self.config_file:
            self.config_file = Path(run_doc["config_file"])
        self._open(run_id, run_doc, state)
        state["status"] = "running"
        state["resumes"] = state.get("resumes", 0) + 1
        self._save()
        self.progress.emit("run.resume", message=f"resume {state['resumes']}")
        return self._loop()

    # ------------------------------------------------------------------ the loop over pieces of work

    def _loop(self) -> int:
        started = time.monotonic()
        code, reason, outcome = 0, None, "finished"
        try:
            self._pieces()
        except Stop as stop:
            code, reason, outcome = 1, stop, "stopped"
        except KeyboardInterrupt:
            code, reason, outcome = 130, Stop("INTERRUPTED", "interrupted; resume continues"), "stopped"
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
            if known is None:
                self._require_clean_tree()
            answer = self._claim(key, asked)
            if answer is None:
                return
            count += 1
            outcome = self._piece(answer)
            if outcome == "blocked" and (self._on_blocked() == "stop"
                                         or self.state["items"][answer["ref"]].get("partial")):
                why = "; it left changes in the tree" if self._on_blocked() != "stop" else ""
                raise Stop("ITEM_BLOCKED", f"{answer['ref']} is blocked{why}; see its escalation")

    def _on_blocked(self) -> str:
        return self.state.get("on_blocked") or self.conductor.get("on_blocked") or "stop"

    def _require_clean_tree(self) -> None:
        """New work starts on a clean tree: changes outside the conductor reports would leak into it."""
        try:
            listing = checks_mod.git(self.project, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        except RuntimeError as error:
            raise Stop("PROJECT_NOT_GIT", str(error)) from None
        reports = REPORTS.as_posix() + "/"
        dirty = []
        entries = listing.split("\0")
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not entry:
                continue
            status, path = entry[:2], entry[3:]
            if status[0] in "RC":
                index += 1  # the original name of a rename or copy follows
            if not path.startswith(reports):
                dirty.append(path)
        if dirty:
            raise Stop("WORKTREE_DIRTY", f"{len(dirty)} changed path(s) before new work, such as {dirty[0]}; "
                                         "commit or set them aside, then resume")

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
        self._resolve(item)
        item.launch_plan = self._step(item, "prepare", lambda: self._prepare(item))
        self._routes(item)
        scout_text = self._scout(item)
        limits = item.options["limits"]
        report = self._execute(item, 1, scout_text, "")
        if report["status"] == "blocked":
            return self._finish(item, report, None)
        round_no, rows = 1, self._run_checks(item, 1, report)
        state = item.state
        state.setdefault("check_fixes_used", 0)
        state.setdefault("corrections_used", 0)
        rows, report, round_no = self._green(item, rows, report, round_no, scout_text)
        if report["status"] == "blocked":
            return self._finish(item, report, rows)
        if self._review_enabled(item):
            review_round = 1
            while True:
                findings = self._review(item, review_round, rows)
                if not findings["findings"]:
                    break
                triage = self._triage(item, review_round, findings)
                if not triage["confirmed"]:
                    break
                if review_round >= limits["review_rounds"] or state["corrections_used"] >= limits["corrections"]:
                    ids = ", ".join(entry["finding"] for entry in triage["confirmed"])
                    return self._finish(item, self._blocked(report, "REVIEW_LIMIT",
                                        f"confirmed review findings {ids} remain after {review_round} review "
                                        f"round(s) and {state['corrections_used']} correction(s)"), rows)
                state["corrections_used"] += 1
                round_no += 1
                report = self._execute(item, round_no, scout_text, prompts.review_correction(findings, triage))
                if report["status"] == "blocked":
                    return self._finish(item, report, rows)
                rows = self._run_checks(item, round_no, report)
                rows, report, round_no = self._green(item, rows, report, round_no, scout_text)
                if report["status"] == "blocked":
                    return self._finish(item, report, rows)
                if not self._needs_rereview(findings, triage):
                    self.progress.emit("info", item=item.ref, message="only minor findings were corrected; "
                                                                       "no further review round")
                    break
                review_round += 1
        return self._finish(item, report, rows)

    def _green(self, item: Item, rows: list, report: dict, round_no: int, scout_text: str) -> tuple:
        """Correct red checks within ``check_fixes``; a red result after the limit blocks the piece of work."""
        state, limit = item.state, item.options["limits"]["check_fixes"]
        while not all(row["green"] for row in rows):
            red = [row for row in rows if not row["green"]]
            if state["check_fixes_used"] >= limit:
                names = ", ".join(row["id"] for row in red)
                return rows, self._blocked(report, "CHECKS_RED", f"acceptance checks {names} stay red after "
                                                                 f"{state['check_fixes_used']} correction(s)"), round_no
            state["check_fixes_used"] += 1
            round_no += 1
            report = self._execute(item, round_no, scout_text, prompts.check_correction(red))
            if report["status"] == "blocked":
                return rows, report, round_no
            rows = self._run_checks(item, round_no, report)
        return rows, report, round_no

    @staticmethod
    def _needs_rereview(findings: dict, triage: dict) -> bool:
        """A corrected round is reviewed again only when a confirmed finding was more than minor."""
        confirmed = {entry["finding"] for entry in triage["confirmed"]}
        minor = ("minor", "nit", "info", "low")
        return any(str(found.get("severity", "")).lower() not in minor
                   for found in findings["findings"] if found.get("id") in confirmed)

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
        events.emit("orch.run.stage.finished", {"run_id": item.orch_run, "stage_id": kind,
                                                 "attempt": int(number) if number.isdigit() else 1,
                                                 "status": status, "attempt_id": item.claim.get("attempt_id")},
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
        artifacts = answer.get("artifacts_dir") or (REPORTS / self.run_id / safe(item.ref)).as_posix()
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
                                                         "sources": item.sources})

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
            item.routes[role] = self._route(item, role)
        self._route_minimum(item)
        if persist:
            write_json(item.directory / "routes.json", item.routes)

    def _route(self, item: Item, role: str) -> dict:
        wanted = opts.stage_route(item.options, role)
        if role == "reviewer":
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
        override = (self.conductor.get("argv") or {}).get(role)
        try:
            if override:
                argv = catalogs.substitute(list(override), values)
            elif effort not in launch.EFFORTS:
                raise Stop("ROUTE_UNDERSHOOT", f"{role} needs effort {effort}, which {provider} cannot start")
            else:
                argv = launch.build_argv(launch.load_catalog(), LAUNCH_ROLE.get(role, role), provider, model=model,
                                         effort=effort, cwd=self.project)
        except launch.LaunchError as error:
            raise Stop(error.code, str(error)) from None
        timeout = item.options["limits"].get("stage_timeout_s") or entry["timeout_s"]
        return {"role": role, "provider": provider, "model": model, "effort": effort, "model_class": model_class,
                "transport": entry["transport"], "timeout_s": timeout, "argv": argv}

    def _route_minimum(self, item: Item) -> None:
        minimum = item.claim.get("route") or {}
        route = item.routes["executor"]
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
              extra: Optional[Callable[[dict], list]] = None) -> tuple:
        """``(result, meta)`` of a role: its closed document (or text when ``kind`` is None) after repeats."""
        route = item.routes[role]
        (item.directory / "prompts").mkdir(parents=True, exist_ok=True)
        (item.directory / "prompts" / f"{key}.md").write_text(prompt, encoding="utf-8")
        attempt = 0
        first_prompt = prompt
        while True:
            attempt += 1
            suffix = "" if attempt == 1 else f"-a{attempt}"
            raw = item.directory / "streams" / f"{key}{suffix}.{'txt' if route['transport'] == 'text' else 'jsonl'}"
            run = process.run_role(route["argv"], prompt, transport=route["transport"], cwd=self.project,
                                   timeout_s=route["timeout_s"], raw_path=raw, env=self.env)
            self._tokens(item, run.usage)
            if run.error in ("PROVIDER_UNAVAILABLE", "TRANSPORT_UNSUPPORTED"):
                raise Stop(run.error, f"{role} on {route['provider']}: {run.detail}")
            problem = f"{run.error}: {run.detail}" if run.error else None
            doc = None
            if problem is None and kind:
                doc, error = prompts.json_block(run.text, kind)
                issues = [error] if error else contract.problems(doc, kind)
                if not issues and extra:
                    issues = extra(doc)
                if issues:
                    problem = f"ROLE_OUTPUT_INVALID: {'; '.join(issues[:3])}"
            meta = {"session": run.session, "model": run.model, "stream": self._relative(raw), "attempts": attempt,
                    "exit": run.exit, "usage": run.usage}
            if problem is None:
                return (doc if kind else run.text), meta
            item.state["retries_used"] = item.state.get("retries_used", 0) + 1
            self._save()
            self._budget(item)
            if item.state["retries_used"] > item.options["limits"]["retries"]:
                raise Stop(problem.split(":", 1)[0], f"{role} on {self.label(route)}: {problem}")
            self.progress.emit("info", item=item.ref, stage=key, role=role, route=self.label(route),
                               message=f"attempt {attempt} failed ({problem}); repeating")
            prompt = (f"{first_prompt}\n\n# Your previous answer was rejected\n\n{problem}\n\n"
                      "Do the work again as needed and end with one corrected block that fits the contract exactly.\n")

    def _tokens(self, item: Item, usage: dict) -> None:
        for bucket in (self.state.setdefault("tokens", {"input": 0, "output": 0}),
                       item.state.setdefault("tokens", {"input": 0, "output": 0}), self._step_tokens):
            for key in ("input", "cached", "output"):
                bucket[key] = bucket.get(key, 0) + int(usage.get(key, 0))

    def _budget(self, item: Item) -> None:
        limit = item.options["limits"].get("tokens_max") or 0
        tokens = item.state.get("tokens", {})
        used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))  # cache reads are not spend
        if limit and used > limit:
            self._save()
            raise Stop("BUDGET_EXHAUSTED", f"{item.ref} used {used} tokens of {limit}")

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
        if not process.available(route["argv"]):
            if stage.get("on_unavailable") == "skip" and not stage.get("required"):
                self.progress.emit("stage.skip", item=item.ref, stage="scout", role="context-scout",
                                   route=self.label(route), reason_code="PROVIDER_UNAVAILABLE",
                                   message=f"{route['argv'][0]} not found; optional stage skipped")
                return ""
            raise Stop("PROVIDER_UNAVAILABLE", f"context-scout on {route['provider']}: {route['argv'][0]} not found")
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
                                   skills=item.options["skills"].get("context-scout", []))
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
            prompt = prompts.executor(item.input_doc, item=item.ref, step=key, scout_text=scout_text,
                                      rules=item.options["rules"], correction=correction, roles_dir=self.roles_dir,
                                      skills=item.options["skills"].get("executor", []))
            report, meta = self._role(item, key, "executor", prompt, "stage-report", extra=report_problems)
            write_json(item.directory / "reports" / f"{key}.json", report)
            return {"report": report, **meta}

        found = self._step(item, key, run, role="executor", route=self.label(route),
                           verdict=lambda result: result["report"]["status"])
        return found["report"]

    def _run_checks(self, item: Item, number: int, report: dict) -> list:
        key = f"checks.{number}"

        def run() -> list:
            try:
                return checks_mod.run_checks(
                    item.input_doc, project=self.project, evidence_dir=item.artifacts / "evidence",
                    log_dir=item.directory / "checks" / str(number),
                    timeout_s=item.options["limits"]["check_timeout_s"],
                    evidence_prefix=f"{self.run_id}:{item.ref}:{key}", report=report,
                    executor=self._actor(item.routes["executor"]))
            except (RuntimeError, ValueError, OSError) as error:
                raise Stop("CHECKS_FAILED", str(error)) from None

        def said(rows: list) -> str:
            red = [row["id"] for row in rows if not row["green"]]
            return "green" if not red else "red " + ",".join(red)

        return self._step(item, key, run, verdict=said)

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

    def _review(self, item: Item, number: int, rows: list) -> dict:
        route = item.routes["reviewer"]
        key = f"review.{number}"

        def run() -> dict:
            base = item.state["steps"]["brief"]["result"]["base"]
            prompt = prompts.reviewer(item.input_doc, item=item.ref, step=key, base=base,
                                      diff=checks_mod.diff(self.project, base), checks=rows, round_no=number,
                                      roles_dir=self.roles_dir, skills=item.options["skills"].get("reviewer", []))
            findings, meta = self._role(item, key, "reviewer", prompt, "review-findings", extra=findings_problems)
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
            base = item.state["steps"]["brief"]["result"]["base"]
            prompt = prompts.triager(item.input_doc, item=item.ref, step=key, base=base, findings=findings,
                                     roles_dir=self.roles_dir, skills=item.options["skills"].get(role, []))
            triage, meta = self._role(item, key, role, prompt, "triage-result",
                                      extra=lambda doc: contract.triage_problems(findings, doc))
            return {"triage": triage, **meta}

        found = self._step(item, key, run, role=role, route=self.label(route),
                           verdict=lambda result: f"confirmed {len(result['triage']['confirmed'])}, "
                                                  f"rejected {len(result['triage']['rejected'])}")
        self._verdict_file(item)
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
                if stop.code == "BUDGET_EXHAUSTED":
                    raise
                return {"by": "conductor", "reason_code": stop.code, "message": stop.message}
            return {"by": "closer", "answer": text[-1500:], **meta}

        found = self._step(item, "close", run, role="registrar", route=self.label(route),
                           verdict=lambda result: "closer ran" if result["by"] == "closer"
                           else f"closer failed ({result['reason_code']}); the conductor records")
        return found

    def _finish(self, item: Item, report: dict, rows: Optional[list]) -> str:
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
