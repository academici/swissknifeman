"""The loop over the pieces of a run: claim, the steps of one piece in order, each closed step recorded once, and
the run clock."""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any, Callable, Optional

from orch import events, policies as run_policies
from orch.conductor import observer, options as opts, prompts, scope as scopes
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import OPTIONS_COPY, REPORTS, safe, write_json
from orch.conductor.progress import human_duration

ROLE_ALIASES_ENGINE = {"scout": "context-scout"}  # the stage role names of the options that name a launch role


def active_s(self) -> float:
    """Active run time: the closed segments of earlier processes plus the one now running (a resume a day later
    does not count the day)."""
    segment = getattr(self, "_segment", None)
    return float(self.state.get("active_s", 0)) + (0.0 if segment is None else clock.mono() - segment)


def run_clock(self, item: Item, stop: bool = True) -> None:
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


def loop(self) -> int:
    started = time.monotonic()
    self._segment = clock.mono()
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


def pieces(self) -> None:
    """Explicit items in order, or the next ready pieces of the source (``--ready``). A piece that closed
    (done or blocked) in an earlier pass of this run is not claimed again; one that stopped half-way resumes
    on its own working tree, while new work needs a clean one."""
    doc = self.run_doc
    keys = [(f"item-{safe(ref)}", [ref]) for ref in doc["items"]] if doc["items"] else None
    count = index = 0
    claimed, first_adopted = {}, []
    if keys is not None and doc.get("grouped") is not False and len(keys) > 1:
        claimed, first_adopted = self._claim_all(keys)
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
        adopted = first_adopted if index == 1 else []
        if known is None:
            if doc.get("adopt") and index == 1:
                adopted = self._dirty_paths()  # the work of an earlier attempt, checked against the write set later
            else:
                self._require_clean_tree()
        answer = claimed.get(key) or self._claim(key, asked)
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


def claim_all(self, keys: list) -> tuple:
    """Every piece named by ``--items`` becomes in progress together, as one start of several items in the work source does: the
    pieces of one run share one executor session and the owner sees the whole batch at work. Pieces that closed in an
    earlier pass are left alone; ``--no-batch`` claims one piece at a time. ``(claimed answers by key, the changed
    paths of the tree taken over by ``--adopt``)``."""
    doc, claimed, adopted = self.run_doc, {}, []
    for key, asked in keys:
        known = self.state["claims"].get(key)
        outcome = self.state["items"].get(known["ref"], {}).get("outcome") if known else None
        if outcome in ("done", "done_with_deviations", "blocked"):
            continue
        if known is None and not claimed:  # new work starts on a clean tree: checked once, before the first claim
            if doc.get("adopt"):
                adopted = self._dirty_paths()
            else:
                self._require_clean_tree()
        try:
            answer = self._claim(key, asked, batch=True)
        except Stop as stop:
            if stop.code == "CLAIM_BLOCKED" and "DEPENDENCY_NOT_READY" in stop.message:
                continue  # waits for something outside this batch: claimed when its turn comes
            raise
        if answer is None:
            break
        claimed[key] = answer
    return claimed, adopted


def on_blocked(self) -> str:
    return self.state.get("on_blocked") or self.conductor.get("on_blocked") or "stop"


def dirty_paths(self) -> list:
    """Changed paths of the tree outside the conductor reports."""
    try:
        return scopes.own(scopes.dirty(self.project), [REPORTS.as_posix()])
    except RuntimeError as error:
        raise Stop("PROJECT_NOT_GIT", str(error)) from None


def require_clean_tree(self) -> None:
    """New work starts on a clean tree: changes outside the conductor reports would leak into it (``run --adopt``
    takes the changes of an earlier attempt of the first piece instead)."""
    dirty = self._dirty_paths()
    if dirty:
        raise Stop("WORKTREE_DIRTY", f"{len(dirty)} changed path(s) before new work, such as {dirty[0]}; "
                                     "commit or set them aside, or take them over with run --adopt, then resume")


def claim_actor(self) -> str:
    """Who runs the work, as claimed: the default executor (provider and model, no effort; the route of the
    work is checked by the source at registration against the executor that really ran)."""
    provider = self.conductor.get("provider") or "claude-code"
    entry = self._entry("executor", provider)
    model_class = self._invocation_executor_class() or entry["model_class"]
    model = self._catalog_get().resolve_model(provider, model_class) \
        if entry["model_set"] == "supported" else "default"
    return f"{provider}/{model}"


def invocation_executor_class(self) -> Optional[str]:
    """The executor class the run was started with (``stages`` of ``--options``): the claim names that executor, so a piece
    whose route minimum is higher than the default class (a ``frontier`` refactor) is not refused at the claim."""
    named = self.run_doc.get("options_file")
    for path in (Path(named) if named else None, self.directory / OPTIONS_COPY):
        try:
            found = json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None
        except (OSError, ValueError):
            found = None
        for stage in (found or {}).get("stages") or []:
            if ROLE_ALIASES_ENGINE.get(stage.get("role"), stage.get("role")) == "executor" and stage.get("model_class"):
                return stage["model_class"]
    return None


def piece(self, answer: dict) -> str:
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


def conduct(self, item: Item) -> str:
    brief = self._step(item, "brief", lambda: self._brief(item))
    item.input_doc = json.loads(Path(brief["input_path"]).read_text(encoding="utf-8"))
    item.artifacts = self.project / brief["artifacts_dir"]
    if "source_paths" not in item.state:  # what the work source changed by claiming: never the role's work
        item.state["source_paths"] = sorted(set(self._dirty_paths()) - set(item.state.get("adopted") or []))
        self._save()
    self._resolve(item)
    self._sync_questions(item)
    self._routes(item, persist=False)
    self._refuse_acp(item)  # before prepare: the binding would refuse an acp route with a less telling code
    item.launch_plan = self._step(item, "prepare", lambda: self._prepare(item))
    self._routes(item)
    adopted = self._adopted(item)
    scout_text = self._scout(item)
    self._research(item)
    report = self._execute(item, 1, scout_text, prompts.ADOPTED.format(paths=", ".join(adopted)) if adopted else "")
    if report["status"] == "blocked":
        return self._finish(item, report, None)
    state = item.state
    state.setdefault("check_fixes_used", 0)
    state.setdefault("corrections_used", 0)
    state.setdefault("check_fixes_at", [])   # rounds that got a correction: a resume walks the closed rounds again,
    state.setdefault("corrections_at", [])   # so a counter that only counts up would count them twice
    state.setdefault("autofix_at", [])       # rounds whose deviation got its fix round (a correction of the budget)
    overlap = self._review_enabled(item) and item.options["checks"]["overlap_review"]
    report, round_no = self._autofix(item, report, 1, scout_text)
    if report["status"] == "blocked":
        return self._finish(item, report, None)
    rows = self._checks_then_review(item, report, round_no, 1) if overlap else self._run_checks(item, round_no, report)
    rows, report, round_no = self._green(item, rows, report, round_no, scout_text, 1 if overlap else None)
    if report["status"] == "blocked":
        return self._finish(item, report, rows)
    self._dynamic_review(item, report)
    if self._reviewing(item):
        review_round, earlier = 1, None
        while True:
            findings = self._review(item, review_round, rows)
            if not findings["findings"]:
                break
            triage = self._triage(item, review_round, findings)
            triage, held = self._retriage(item, review_round, findings, triage)
            if held:
                return self._finish(item, self._blocked(report, "QUESTION", held), rows)
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


def step(self, item: Item, key: str, run: Callable[[], Any], *, role: str = "deterministic",
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
                  "duration_s": round(time.monotonic() - begin, 1), "ended": clock.utc_now(),
                  **({"tokens": tokens} if tokens and any(tokens.values()) else {})}
    self._save()
    self.progress.emit("stage.end", item=item.ref, stage=key, role=role, route=route, verdict=said,
                       duration_s=steps[key]["duration_s"], tokens=steps[key].get("tokens"),
                       agent=result.get("agent") if isinstance(result, dict) else None)
    self._stage_event(item, key, "completed")
    if item.options:
        self._budget(item)
    return result


def stage_event(self, item: Item, key: str, status: str) -> None:
    kind, _, number = key.partition(".")
    data = {"run_id": item.orch_run, "stage_id": kind, "attempt": int(number) if number.isdigit() else 1,
            "status": status, "attempt_id": item.claim.get("attempt_id"),
            # none before the options are resolved (the brief step)
            "options_digest": opts.digest(item.options) if item.options else None}
    events.emit("orch.run.stage.finished", {key: value for key, value in data.items() if value is not None},
                subject=item.orch_run, settings=self.settings, project=self.project,
                config_file=self.config_file)


def resolve(self, item: Item, persist: bool = True) -> None:
    """The run-policy of the scenario and the merged options (configuration, pack, source layers, invocation)."""
    scenario = item.claim.get("scenario") or self.run_doc.get("scenario") or self.settings.default_profile
    try:
        item.policy = run_policies.load(scenario, self.settings, warn=lambda message: None)
    except run_policies.PolicyError as error:
        raise Stop(error.code, str(error)) from None
    layers = list(item.claim.get("options") or [])
    if self.run_doc.get("options_file"):
        named, kept = Path(self.run_doc["options_file"]), self.directory / OPTIONS_COPY
        origin = named if named.is_file() or not kept.is_file() else kept  # an edited file still wins on resume
        try:
            found = json.loads(origin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Stop("OPTIONS_INVALID", f"{origin}: {error}") from None
        layers.append({"source": "invocation:--options", "options": found})
    if self.run_doc.get("grouped") is not None:
        layers.append({"source": "invocation:--batch" if self.run_doc["grouped"] else "invocation:--no-batch",
                       "options": {"session": {"executor": "shared" if self.run_doc["grouped"] else "per-item"}}})
    flags = {key: self.run_doc[name] for key, name in (("fence", "fence"), ("extra_paths", "extra_paths"))
             if self.run_doc.get(name)}
    if flags:
        layers.append({"source": "invocation:--fence/--allow-path", "options": {"scope": flags}})
    try:
        item.options, item.sources = opts.effective(self.conductor, item.policy, layers)
    except opts.OptionsError as error:
        raise Stop(error.code, error.message) from None
    if persist:
        self.state["on_blocked"] = item.options["on_blocked"]
        write_json(item.directory / "options.json", {"scenario": scenario, "options": item.options,
                                                     "sources": item.sources, "digest": opts.digest(item.options),
                                                     "claim_route": item.claim.get("route")})
