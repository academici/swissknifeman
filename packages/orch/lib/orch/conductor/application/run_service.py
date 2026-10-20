"""The verbs of a conductor run: ``run``, ``resume`` (with ``--retry`` of a blocked piece), ``release`` and ``settle``."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from aicore.stubs import StubError

from orch import settings as settings_mod
from orch.conductor import debug_mode, options as opts, progress, stubs as stubs_mod
from orch.conductor.domain.report import continued
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import RunStore, safe, write_json
from orch.conductor.policies.budget import HARD_LIMITS, effective_limit
from orch.worksource import WorkSourceError
from orch.worksource_file import read_input


def run(self, *, plan: Optional[str], plans_root: Optional[str], items: list, batch: bool, max_items: int,
        options_file: Optional[Path] = None, adopt: bool = False, input_file: Optional[Path] = None,
        commit: bool = False, scenario: Optional[str] = None,
        fence: Optional[str] = None, extra_paths: Optional[list] = None,
        grouped: Optional[bool] = None) -> int:
    """Conduct the pieces of a plan, or with ``input_file`` the one piece of an execution-input document (the built-in
    file source: no plan; ``scenario`` is then the scenario of the run, ``commit`` lets it commit its paths)."""
    run_id = clock.new_run_id()
    source = None
    if input_file is not None:
        try:
            found = read_input(input_file)
        except WorkSourceError as error:
            raise Stop(error.code, error.message) from None
        plan, plans_root, items, batch = str(Path(input_file).resolve()), None, [found["input_id"]], False
        source = {"kind": "file", "path": plan, "commit": bool(commit)}
    instructions = snapshot_stubs(self)
    run_doc = {"run_id": run_id, "plan": plan, "plans_root": plans_root, "items": list(items), "batch": batch,
               "source": source, "scenario": scenario,
               "max_items": max_items, "options_file": str(options_file) if options_file else None,
               "adopt": bool(adopt), "grouped": grouped, "fence": fence,
               "extra_paths": [str(path) for path in extra_paths or []] or None,
               "config_file": str(self.config_file) if self.config_file else None, "created": clock.utc_now(),
               "project": str(self.project), "project_resolution": self.project_resolution,
               "working_directory": os.getcwd(), "config_digest": settings_mod.config_digest(self.settings),
               "config_layers": settings_mod.config_layers(self.settings),
               "instructions_digest": instructions["digest"], "debug": bool(getattr(self.settings, "debug", False)),
               "limits_run": limits_run(self, options_file)}
    store = RunStore(self.project, run_id)
    with store.ownership("run", checkout=True, create=True):
        run_doc["lease"] = True
        self._open(run_id, run_doc, {"status": "running", "items": {}, "claims": {}, "tokens": {"input": 0, "output": 0}}, store)
        self.store.create(run_doc)
        write_json(self.directory / stubs_mod.SNAPSHOT_FILE, instructions)
        self.instructions = instructions
        if options_file:
            self.store.keep_options(options_file)
        self._save()
        self.progress.emit("run.start", message=(f"input {plan}; " if source else f"plan {plan}; ") + (f"items {', '.join(items)}" if items else
                                                                     f"batch, at most {max_items or 'all'}"))
        debug_mode.announce(self.progress, self.directory, run_id, self.settings)
        return self._loop()


def resume(self, run_id: str, retry=(), raise_limits=()) -> int:
    store = RunStore(self.project, run_id)
    with store.ownership("resume", checkout=True):
        run_doc, state = store.load()
        if run_doc.get("config_file") and not self.config_file:
            self.config_file = Path(run_doc["config_file"])
        self._open(run_id, run_doc, state, store)
        changes = limit_raises(self, raise_limits)
        if run_doc.get("lease") is True and progress.summarize(progress.read_lines(self.directory))["status"] == "running":
            self._kill_orphaned_roles()
        stubs_changed(self, run_doc)
        for ref in retry:
            self._retry(ref)
        self._reconcile_interrupted()
        if changes:
            state.setdefault("limit_raises", []).extend(changes)
            self._save()
            for change in changes:
                self.progress.emit("info", reason_code="LIMIT_RAISED",
                                   message=f"{change['key']}: {change['from']} -> {change['to']} by invocation")
        state["status"] = "running"
        state["resumes"] = state.get("resumes", 0) + 1
        earlier = state.pop("stop", None)  # the stop answered by this resume is history now
        if earlier:
            state["last_stop"] = {**earlier, "resume": state["resumes"]}
        self._save()
        self.progress.emit("run.resume", message=f"resume {state['resumes']}")
        debug_mode.announce(self.progress, self.directory, run_id, self.settings)
        return self._loop()


def limits_run(self, options_file: Optional[Path]) -> dict:
    """Freeze the run cap and its trusted origin before claiming work or making a model call."""
    key = "run_tokens_hard_max"
    layers = []
    if options_file:
        try:
            found = json.loads(Path(options_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Stop("OPTIONS_INVALID", f"{options_file}: {error}") from None
        issues = opts.layer_problems(found)
        if issues:
            raise Stop("OPTIONS_INVALID", f"{options_file}: {'; '.join(issues[:3])}")
        # Piece limits are validated after all source layers merge, not while snapshotting the run cap.
        only_run = {key: found["limits"][key]} if key in found.get("limits", {}) else {}
        layers.append({"source": "invocation:--options", "options": {"limits": only_run}, "trusted": True})
    try:
        configured = {key: value for key, value in (self.conductor.get("limits") or {}).items()
                      if key == "run_tokens_hard_max"}
        options, sources = opts.effective({"limits": configured}, {}, layers)
    except opts.OptionsError as error:
        raise Stop(error.code, error.message) from None
    source = sources.get(f"limits.{key}", "defaults")
    origin = {"source": source}
    resolved = self.settings.resolved
    if source == "invocation:--options":
        origin["file"] = str(Path(options_file).resolve())
    elif resolved is not None:
        entry = resolved.explain(f"conductor.limits.{key}")[0]
        origin = {"source": f"config:{entry.layer}", "file": entry.file}
    return {key: {"value": options["limits"][key], **origin}}


def limit_raises(self, values) -> list:
    """Validate every requested raise before changing state; the history is the effective overlay on resume."""
    if not values:
        return []
    parsed = []
    for value in values:
        match = re.fullmatch(r"(tokens_hard_max|run_tokens_hard_max)=([0-9]+)", value)
        if match is None:
            raise Stop("OPTIONS_INVALID", "--raise-limit must be tokens_hard_max=N or run_tokens_hard_max=N (integer >= 0)")
        parsed.append((match[1], int(match[2])))
    items = self.state.get("items", {})
    refs = list(dict.fromkeys([*(self.run_doc.get("items") or []), *items]))
    ref = next((ref for ref in refs if items.get(ref, {}).get("outcome") == "stopped"), None)
    ref = ref or next((ref for ref in refs if items.get(ref, {}).get("outcome") not in
                      ("done", "done_with_deviations", "blocked", "abandoned")), None)
    ref = ref or (refs[-1] if refs else "run")
    claim = next((claim for claim in (self.state.get("claims") or {}).values() if claim.get("ref") == ref), {})
    item = Item(ref=ref, orch_run=claim.get("run_id", ""), state=items.get(ref, {}),
                directory=self.directory / safe(ref), claim=claim)
    self._resolve(item, persist=False)
    current = {key: effective_limit(self, item, key) for key in HARD_LIMITS}
    changes = []
    for key, value in parsed:
        previous = current[key]
        if value != 0 and value <= previous:
            raise Stop("OPTIONS_INVALID", f"--raise-limit {key}={value} must exceed the effective value {previous}, or be 0")
        changes.append({"key": key, "from": previous, "to": value, "at": clock.utc_now(), "by": "invocation"})
        current[key] = value
    try:
        opts.validate_limits({**item.options["limits"], **current})
    except opts.OptionsError as error:
        raise Stop(error.code, error.message) from None
    return changes


def snapshot_stubs(self) -> dict:
    """The stubs of the roles, resolved once for the whole run; a stub that cannot be used stops it before any work."""
    try:
        return stubs_mod.snapshot(self.project, getattr(self.settings, "stubs", None), env=self.env)
    except StubError as error:
        raise Stop("STUBS_INVALID", f"{error.code}: {error.message}") from None


def stubs_changed(self, run_doc: dict) -> None:
    """A resume keeps the snapshot of the run; when the files say something else now, the beacon ``STUBS_CHANGED`` says
    that the new text waits for a new run."""
    if "instructions_digest" not in run_doc:
        return  # a run of an older conductor has no snapshot
    try:
        now = stubs_mod.snapshot(self.project, getattr(self.settings, "stubs", None), env=self.env)["digest"]
    except StubError as error:
        now = f"invalid ({error.code})"
    if now != run_doc["instructions_digest"]:
        self.progress.emit("info", reason_code="STUBS_CHANGED",
                           message="the stubs changed since the run started; the run keeps its snapshot "
                                   f"({run_doc['instructions_digest'] or 'none'}), a new run reads them")


def retry(self, ref: str) -> None:
    """Take a blocked piece back into the run: the input is built again from the (amended) plan, and the steps from the executor round that reported ``blocked`` on
    (and the closing steps after it) are repeated; the earlier rounds are kept and the work in the tree is not thrown away."""
    item = self.state["items"].get(ref)
    if item and item.get("retried") and item.get("outcome") in (None, "stopped"):
        # the first resume already took the piece back and stopped again: the same command again is not an error
        self.progress.emit("info", item=ref, message="retry: already taken back by an earlier resume; the run goes on from there")
        return
    if not item or item.get("outcome") != "blocked":
        raise Stop("RETRY_NOT_BLOCKED", f"{ref} is not a blocked piece of this run")
    steps = item.get("steps", {})
    completed = done_steps(steps)
    # the state file is sorted by key, so the order of the steps is the order of their ``ended`` stamps
    blocked = min((key for key in completed if key.startswith("executor.") and key not in continued(completed) and
                   (((steps[key].get("result") or {}).get("report") or {}).get("status") == "blocked")),
                  key=lambda key: steps[key].get("ended", ""), default=None)
    held = any(name.startswith("orch-advice-") for name in (self.state.get("questions") or {}).get(ref, {}))
    if blocked is None and not held:
        # blocked by the conductor itself (red checks past the limit, a review limit, a path outside the scope with
        # ``scope.outside: block``): no round reported ``blocked``, so the last executor round is where the piece goes on
        rounds = [key for key in completed if key.startswith("executor.") and key not in continued(completed)]
        blocked = max(rounds, key=lambda key: steps[key].get("ended", ""), default=None)
    if blocked is None and not held:
        raise Stop("RETRY_NOT_BLOCKED", f"{ref} has no executor round to go on from")
    # the input is built again too: the plan was amended (that is why the piece was blocked and reopened), and the
    # executor must see the amended write set, not the one of the first brief. A piece held on advice (red checks or a
    # rejected finding, the question ``orch-advice-<n>`` waits for the owner) reported no blocked round: its closed rounds,
    # checks, reviews and advice stay and only the opening and closing steps are repeated.
    since = steps[blocked].get("ended", "") if blocked else None
    dropped = [key for key in steps if steps[key].get("status") != "done" or key == blocked
               or key in ("brief", "prepare", "scout", "close", "register", "commit")
               or (since is not None and steps[key].get("ended", "") > since)]
    archive_attempt(self, ref, item, dropped)  # the repeated steps write the same files again: the first attempt is kept aside
    for key in dropped:
        steps.pop(key)
    for key in ("outcome", "stop", "partial", "skills_auto", "skills_checked"):  # the skills are chosen again from the amended write set
        item.pop(key, None)
    item["retried"] = clock.utc_now()
    self._save()
    self.progress.emit("info", item=ref, message=f"retry: the steps from {blocked} on are repeated" if blocked
                       else "retry: the answer to the advice is applied; the closed rounds are kept")


ATTEMPT_DIRS = ("streams", "reports", "prompts", "checks")


def archive_attempt(self, ref: str, item: dict, dropped: list) -> None:
    """Keep what a ``retry`` is about to repeat: the record of the dropped steps in ``item["attempts"]`` and their
    files (stream, report, prompt, checks) under ``<piece>/attempts/<n>/``. The count of reviews a piece went through is
    the reviews of its attempts and of its current steps; a step key alone is not a history."""
    steps = item.get("steps", {})
    attempts = item.setdefault("attempts", [])
    number = len(attempts) + 1
    kept = [key for key in steps if key not in dropped]
    directory = self.directory / safe(ref)
    record = {}
    for key in dropped:
        step = steps[key]
        if step.get("status") != "done":
            continue  # attempt summaries describe results; unfinished steps have none
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        report = result.get("report") if isinstance(result.get("report"), dict) else {}
        row = {name: step[name] for name in ("verdict", "role", "route", "ended") if step.get(name)}
        if report.get("status"):
            row["report_status"] = report["status"]
        moved = []
        for folder in ATTEMPT_DIRS:
            for path in sorted((directory / folder).glob("*")) if (directory / folder).is_dir() else []:
                name = path.name
                if not (name == key or name.startswith((key + ".", key + "-"))):
                    continue
                if any(name == other or name.startswith((other + ".", other + "-")) for other in kept if len(other) > len(key)):
                    continue  # a file of a longer step key that stays (``executor.1-q1`` beside a dropped ``executor.1``)
                target = directory / "attempts" / str(number) / folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                path.replace(target)
                moved.append(f"{folder}/{name}")
        if moved:
            row["files"] = moved
        record[key] = row
    attempts.append({"n": number, "retried_at": clock.utc_now(), "steps": record})


def work_began(state: dict) -> bool:
    """An executor round ran: the piece has this run's work in the tree and is no longer free to give back. Changes
    adopted from an earlier attempt do not count: they stay in the tree, and a later ``run --adopt`` takes them again."""
    return bool(state.get("executor_started")) or any(key.startswith("executor.") for key in done_steps(state.get("steps", {})))


def batch_held(self) -> bool:
    """The pieces of this run are one batch (several pieces, ``--batch`` unless ``--no-batch``): they are in progress
    together, so a stop gives none of them back on its own (a stop is resumable; ``release`` is the hand that frees)."""
    return self.run_doc.get("grouped") is not False and len(self.run_doc.get("items") or []) > 1


def release(self, run_id: str, ref, reason: str) -> int:
    """Give pieces of this run back to the work source by hand, when a run died or stopped before any work began
    (an executor round makes it refuse: settle or retry the piece instead). ``ref``: one reference, a list of them, or
    ``None`` for every piece of the run that nobody worked on and that is not closed (the pieces with work are named and
    left alone, and the command says so)."""
    store = RunStore(self.project, run_id)
    with store.ownership("release"):
        return _release_owned(self, store, run_id, ref, reason)


def _release_owned(self, store: RunStore, run_id: str, ref, reason: str) -> int:
    run_doc, state = store.load()
    items = state.setdefault("items", {})
    known = list(dict.fromkeys([*state_claims(state), *(run_doc.get("items") or []), *items]))  # claimed, maybe never started
    everything = ref is None
    refs = known if everything else ([ref] if isinstance(ref, str) else list(ref))
    for one in refs:
        if one not in known:
            raise Stop("ITEM_UNKNOWN", f"{one} is not a piece of run {run_id}")
    self._open(run_id, run_doc, state, store)
    freed, kept, failed = [], [], []
    for one in refs:
        owner = next((claim.get("orch_run") for claim in (state.get("claims") or {}).values() if claim.get("ref") == one), None)
        item = items.setdefault(one, {"steps": {}, "retries_used": 0, "orch_run": owner})
        closed = item.get("outcome") in ("done", "done_with_deviations")
        if self._work_began(item) or closed:
            if not everything:
                raise Stop("RELEASE_WORK_BEGAN", f"{one} has work in the tree or is closed; settle it, or resume with --retry")
            kept.append(one)
        elif self._release_claim(one, item, reason):
            freed.append(one)
        elif not everything:
            raise Stop("RELEASE_REFUSED", f"the work source did not release {one}; see the progress line")
        else:
            failed.append(one)
    if everything:
        self.progress.emit("info", reason_code="RELEASED_ALL", message=f"released: {', '.join(freed) or '-'}; "
                           f"kept (work began or closed): {', '.join(kept) or '-'}; refused by the source: {', '.join(failed) or '-'}")
    if failed:
        raise Stop("RELEASE_REFUSED", f"the work source did not release {', '.join(failed)}; see the progress lines")
    return 0


def state_claims(state: dict) -> list:
    """The references of the pieces a run claimed, in the order of its claims."""
    return [claim["ref"] for claim in (state.get("claims") or {}).values() if claim.get("ref")]


def settle(self, run_id: str, ref: str, outcome: str, reason: str) -> int:
    """Set the outcome of a piece of this run by hand, after the owner or an observer finished it outside the
    conductor (committed it with the work source's own command, or gave it up). Nothing else changes: the work
    source keeps its own record; a resume then treats the piece as closed."""
    store = RunStore(self.project, run_id)
    with store.ownership("settle"):
        return _settle_owned(self, store, run_id, ref, outcome, reason)


def _settle_owned(self, store: RunStore, run_id: str, ref: str, outcome: str, reason: str) -> int:
    run_doc, state = store.load()
    if ref not in state.get("items", {}):
        raise Stop("ITEM_UNKNOWN", f"{ref} is not a piece of run {run_id}")
    self._open(run_id, run_doc, state, store)
    item = state["items"][ref]
    before = item.get("outcome")
    item["outcome"] = outcome
    item.pop("stop", None)
    item.pop("partial", None)
    item.setdefault("settled", []).append({"from": before, "to": outcome, "reason": reason, "at": clock.utc_now()})
    self._save()
    self.progress.emit("info", item=ref, reason_code="SETTLED", outcome=outcome, message=f"outcome {before or '-'} → {outcome} by hand: {reason}")
    return 0
