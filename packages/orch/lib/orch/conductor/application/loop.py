"""The loop over the pieces of a run: claim, the steps of one piece in order, each closed step recorded once, and
the run clock."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import threading
import time
import traceback
from typing import Any, Callable, Optional

from aicore.util.redact import env_secrets, redact_document

from orch import events, policies as run_policies
from orch.conductor import checks as checks_mod, observer, options as opts, prompts, questions as questions_mod
from orch.conductor import records, scope as scopes
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, disk
from orch.conductor.infrastructure.files import OPTIONS_COPY, REPORTS, safe
from orch.conductor.progress import human_duration
from orch.conductor.application import recovery, run_service
from orch.conductor.policies import budget as token_budget

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
    text = None
    with self.store.mutating():  # a check thread and the main loop both get here (I2)
        if warn and int(active // warn) > self.state.get("run_warned", 0):
            self.state["run_warned"] = int(active // warn)
            items = self.state.get("items", {})
            closed = sum(1 for row in items.values() if row.get("outcome") in ("done", "done_with_deviations", "blocked"))
            asked = len(self.run_doc.get("items") or [])
            text = (f"run active {human_duration(active)}; {closed} piece(s) closed"
                    + (f", {max(asked - closed, 0)} left" if asked else "")
                    + f"; now {item.ref} {token_budget.stage_key(self) or '-'}")
            self._plan_note(item, text)
    if text is not None:  # progress and the bus after the lock
        self.progress.emit("info", item=item.ref, reason_code="RUN_SLOW", message=text)
        self._beacon_event("orch.run.warning", item, {"reason_code": "RUN_SLOW", "step": token_budget.stage_key(self)})
    if stop and cap and active >= cap:
        raise Stop("RUN_TIMEOUT", f"the run was active {human_duration(active)}, past limits.run_timeout_s {cap}; "
                                  "raise it or set 0, then resume")


def disk_guard(self, item: Optional[Item] = None, stage: Optional[str] = None) -> None:
    """Stop with DISK_LOW (resumable: free the space, then resume) when the project or the temporary directory has less
    than ``limits.disk_min_gb`` free; the limit of the piece when there is one, else the configuration's."""
    limits = (item.options or {}).get("limits") if item is not None and item.options else None
    if limits is None:
        limits = {**opts.DEFAULT_LIMITS, **{k: v for k, v in (self.conductor.get("limits") or {}).items() if v is not None}}
    found = disk.shortage(self.project, limits.get("disk_min_gb", 0))
    if found:
        self.progress.emit("info", item=item.ref if item else None, stage=stage, reason_code="DISK_LOW", message=found)
        raise Stop("DISK_LOW", f"{found}; free the space, then resume")


def terminated(_signum, _frame) -> None:
    """SIGTERM/SIGHUP end the run like Ctrl-C: the role and check processes of the run are killed by the code that waits
    for them (a plain SIGTERM would leave the executor ``claude -p`` and its test workers running)."""
    raise KeyboardInterrupt


def loop(self) -> int:
    started = time.monotonic()
    self._segment = clock.mono()
    self.state.pop("ended", None)
    code, reason, outcome = 0, None, "finished"
    previous = {number: signal.signal(number, terminated) for number in (signal.SIGTERM, signal.SIGHUP)} \
        if threading.current_thread() is threading.main_thread() else {}
    try:
        self._disk_guard()
        self._pieces()
    except Stop as stop:
        code, reason, outcome = 1, stop, "stopped"
    except KeyboardInterrupt:
        code, reason, outcome = 130, Stop("INTERRUPTED", "interrupted; resume continues"), "stopped"
    except Exception as error:  # noqa: BLE001 — unexpected failures must close the run too
        secrets = env_secrets()
        crash = redact_document(traceback.format_exc(), secrets=secrets)
        # The artifact is best-effort. Failing to write it must not drop the original redacted stop, and the
        # message must not claim crash.txt exists. The state save and run.end below still run when they can.
        try:
            (self.directory / "crash.txt").write_text(crash, encoding="utf-8")
            written = True
        except Exception:  # noqa: BLE001 — a missing artifact never hides the crash of the run
            written = False
        detail = "see crash.txt" if written else "crash.txt unavailable"
        message = redact_document(f"{type(error).__name__}: {error}; {detail}; resume continues", secrets=secrets)
        code, reason, outcome = 1, Stop("CONDUCTOR_CRASHED", message), "stopped"
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    with self.store.mutating():
        self.state["active_s"] = round(self._active_s(), 1)
        self._segment = None
        self.state["status"] = outcome
        # Progress is second-granular; event timestamps carry fractions of a second.
        self.state["ended"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if reason is not None:
            self.state["stop"] = {"code": reason.code, "message": reason.message}
        self._save()
    held = run_service.held_pieces(self.state) if reason is not None and self._batch_held() else []
    if held:  # a stopped batch keeps its claims (resume continues them); say how to give them back instead
        self.progress.emit("info", reason_code="BATCH_HELD", message=run_service.held_hint(self.run_id, held))
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
    started = 0
    pending_retries = []
    claimed, first_adopted, held = {}, [], []
    # Ready mode used to return on max_items and on an empty claim, so a held dependency did not become
    # DEPENDENCY_BLOCKED. Explicit items still fall out of the loop when the list is exhausted, and that is the
    # only path that stops for a held piece. Pending answers are finalized on every exit (P3.7).
    exhausted = False
    if keys is None and doc.get("grouped") is not False:  # the batch a source names is a batch like --items
        expanded = self._expand_ready()
        if expanded:
            keys, claimed, first_adopted = expanded
    elif keys is not None and doc.get("grouped") is not False and len(keys) > 1:
        claimed, first_adopted = self._claim_all(keys)
    if keys is not None and len(keys) > 1 and doc.get("grouped") is not False and claimed:
        self._decide_review_strategy([claimed[key] for key, _ in keys if key in claimed])
    while True:
        if keys is not None:
            if index >= len(keys):
                exhausted = True
                break
            key, asked = keys[index]
        else:
            if doc.get("max_items") and count >= doc["max_items"]:
                break
            key, asked = f"next-{index + 1}", []
        index += 1
        known = self.state["claims"].get(key)
        outcome = self.state["items"].get(known["ref"], {}).get("outcome") if known else None
        if outcome in ("done", "done_with_deviations", "blocked"):
            if outcome in ("done", "done_with_deviations"):
                self._group_review_due(known["ref"])
            else:
                questions = questions_mod.read(self.directory / safe(known["ref"])) or {}
                if any(entry.get("status") == "answered" or
                       (entry.get("status") == "open" and entry.get("resolution"))
                       for entry in questions.get("questions", [])):
                    message = (f"answers of {known['ref']} wait: orch conduct resume --run {self.run_id} "
                               f"--retry {known['ref']}")
                    pending_retries.append(message)
                    self.progress.emit("info", item=known["ref"], reason_code="QUESTION_ANSWERED_NOT_RETRIED",
                                       message=message)
            count += 1
            continue
        adopted, first_adopted = first_adopted, []  # the paths of ``--adopt`` belong to the first piece that really runs
        if known is None:
            if doc.get("adopt") and not adopted and index == 1:
                adopted = self._dirty_paths()  # the work of an earlier attempt, checked against the write set later
            else:
                self._require_clean_tree()
        answer = claimed.get(key) or self._claim(key, asked)
        if answer is None:
            break
        count += 1
        if adopted:
            self.state["items"].setdefault(answer["ref"], {"steps": {}, "retries_used": 0, "orch_run": answer["run_id"]}) \
                .setdefault("adopted", adopted)
            self._save()
        waiting = blocked_dependencies(self, answer)
        if waiting:  # a piece on top of a blocked one of this run would build on work that is not accepted
            held.append(answer["ref"])
            self.progress.emit("info", item=answer["ref"], reason_code="DEPENDENCY_BLOCKED",
                               message=f"{answer['ref']} waits for {', '.join(waiting)} (blocked in this run): not started, "
                                       "it stays in progress; retry the blocked piece and resume")
            continue
        started += 1
        outcome = self._piece(answer)
        if outcome in ("done", "done_with_deviations"):
            self._group_review_due(answer["ref"])
        if outcome == "blocked" and (self._on_blocked() == "stop"
                                     or self.state["items"][answer["ref"]].get("partial")):
            why = "; it left changes in the tree" if self._on_blocked() != "stop" else ""
            raise Stop("ITEM_BLOCKED", f"{answer['ref']} is blocked{why}; see its escalation")
    if pending_retries and not started:
        raise Stop("QUESTION_ANSWERED_NOT_RETRIED", "; ".join(pending_retries))
    if held and exhausted:
        raise Stop("DEPENDENCY_BLOCKED", f"{', '.join(held)} not started: a piece they depend on is blocked; "
                                         "retry it (resume --retry), then resume")


def blocked_dependencies(self, answer: dict) -> list:
    """The pieces named in ``depends_on`` of a claim that ended ``blocked`` in this run."""
    items = self.state.get("items", {})
    return [dep for dep in answer.get("depends_on") or [] if (items.get(dep) or {}).get("outcome") == "blocked"]


def expand_ready(self) -> Optional[tuple]:
    """``--ready`` with a batch: the first claim lets the source pick a piece and name its lane (the pieces that go
    together); the run then goes on as ``--items`` of that lane, so every piece is in progress from the start.
    ``None`` when the source names no lane of several pieces (the run claims one piece at a time as before)."""
    doc = self.run_doc
    if self.state["claims"].get("next-1") is None:
        adopted = self._dirty_paths() if doc.get("adopt") else []
        if not adopted:
            self._require_clean_tree()
    else:
        adopted = []
    answer = self._claim("next-1", [], batch=True)
    lane = list(answer.get("lane") or []) if answer else []
    if len(lane) < 2:
        return None
    if doc.get("max_items"):
        lane = lane[:doc["max_items"]]
    if len(lane) < 2:
        return None
    first = f"item-{safe(lane[0])}"
    self.state["claims"][first] = self.state["claims"].pop("next-1")
    doc["items"] = lane
    self.store.save_run(doc)
    self._save()
    keys = [(f"item-{safe(ref)}", [ref]) for ref in lane]
    claimed = {first: answer}
    rest, _ = self._claim_all(keys[1:])
    claimed.update(rest)
    return keys, claimed, adopted


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
    takes the changes of an earlier attempt of the first piece instead). With ``[orch.conductor] foreign_untracked =
    "keep"`` untracked files that are already there (a tree shared with another session) do not stop the run: they are
    fingerprinted in ``state.foreign`` and are never the work of a piece while their content stays the same."""
    dirty = self._dirty_paths()
    if dirty and (self.conductor.get("foreign_untracked") or "refuse") == "keep":
        untracked = set(checks_mod.untracked(self.project))
        kept = [path for path in dirty if path in untracked]
        if kept and len(kept) == len(dirty):
            self.state["foreign"] = scopes.fingerprint(self.project, kept)
            self._save()
            self.progress.emit("info", reason_code="FOREIGN_KEPT",
                               message=f"{len(kept)} untracked path(s) of someone else stay in the tree and out of every "
                                       f"piece, such as {kept[0]}")
            return
    if dirty:
        raise Stop("WORKTREE_DIRTY", f"{len(dirty)} changed path(s) before new work, such as {dirty[0]}; "
                                     "commit or set them aside, or take them over with run --adopt, then resume")


def claim_actor(self) -> str:
    """Who runs the work, as claimed: the executor the run was started with (the ``executor`` stage of ``--options``:
    its provider, its model or the model of its class, and its effort), else the default executor (provider and model,
    no effort). The source checks the route of the work against this actor at the claim; an executor the options name
    but the claim does not carry is refused as ``ROUTE_MISMATCH`` / ``ROUTE_UNDERSHOOT`` before any work began, while
    the dry run, which builds the route from the same options, shows it green. Registration still checks the route
    against the executor that really ran."""
    stage = self._invocation_executor()
    provider = stage.get("provider") or self.conductor.get("provider") or "claude-code"
    entry = self._entry("executor", provider)
    model = stage.get("model")
    if not model:
        model_class = stage.get("model_class") or entry["model_class"]
        model = self._catalog_get().resolve_model(provider, model_class) if entry["model_set"] == "supported" \
            else "default"
    return "/".join(part for part in (provider, model, stage.get("effort")) if part)


def claim_actor_source(self) -> tuple:
    """``(source, fields, model_class)`` of the claim actor for the work source, as the stage merge of execution sees
    the ``executor`` stage of ``--options``: ``fields`` are the actor fields it names (provider, model, effort; a
    provider alone keeps the plan's model, as the merge does), ``model_class`` a class it names without a model (the
    source resolves its model on the provider of the merged actor). ``("default", None, None)`` when it names none of
    them: the source may use the executor of its own plan."""
    stage = self._invocation_executor()
    fields = [name for name in ("provider", "model", "effort") if stage.get(name)]
    model_class = stage.get("model_class") if not stage.get("model") else None
    return ("options", fields or None, model_class) if fields or model_class else ("default", None, None)


def invocation_executor(self) -> dict:
    """The ``executor`` stage of the run's ``--options`` file (``{}`` without one): provider, model, model class, effort."""
    named = self.run_doc.get("options_file")
    for path in (Path(named) if named else None, self.directory / OPTIONS_COPY):
        try:
            found = json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None
        except (OSError, ValueError):
            found = None
        for stage in (found or {}).get("stages") or []:
            if ROLE_ALIASES_ENGINE.get(stage.get("role"), stage.get("role")) == "executor":
                return {key: stage[key] for key in ("provider", "model", "model_class", "effort") if stage.get(key)}
    return {}


def invocation_executor_class(self) -> Optional[str]:
    """The executor class the run was started with (``stages`` of ``--options``), None without one."""
    return self._invocation_executor().get("model_class")


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
        if not self._work_began(state) and not self._batch_held():  # a claim nobody worked on must not outlive the stopped run
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
    self._open_artifacts(item, brief)
    if "source_paths" not in item.state:  # what the work source changed by claiming: never the role's work
        item.state["source_paths"] = sorted(set(self._dirty_paths()) - set(item.state.get("adopted") or []))
        self._save()
    self._resolve(item)
    self._admit_budget(item)
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
    report, round_no = self._self_check_return(item, report, round_no, scout_text)
    if report["status"] == "blocked":
        return self._finish(item, report, None)
    rows = self._checks_then_review(item, report, round_no, 1) if overlap else self._run_checks(item, round_no, report)
    rows, report, round_no = self._green(item, rows, report, round_no, scout_text, 1 if overlap else None)
    if report["status"] == "blocked":
        return self._finish(item, report, rows)
    self._dynamic_review(item, report)
    self._review_requested_off(item)
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
            # progress: fewer findings to correct than the round before; other findings in other places are not
            # (a reviewer that finds something new every round would otherwise keep the loop going)
            state["review_rounds_used"] = review_round
            state.setdefault("findings_at", {})[str(review_round)] = len(triage["confirmed"])
            places = sorted(self._place(findings, entry["finding"]) for entry in major)
            progress = earlier is not None and len(places) < len(earlier)
            earlier = places
            replayed = review_round in state["corrections_at"]
            rounds_why = self._allowance(item, "review_rounds", review_round, progress, emit=not replayed)
            # a spent run-wide budget (``*_batch``) is its own limit and wins over the per-piece wall, which refuses
            # before ``allowance`` reaches the batch rule
            batch_rounds = (self._batch_allowance(item, "review_rounds", review_round, progress, emit=False)
                            if rounds_why else None)
            batch_findings = self._batch_allowance(item, "findings", self._piece_count(state, "findings_at"),
                                                   progress, emit=not replayed)
            rounds_why = batch_rounds or batch_findings or rounds_why
            if review_round in state.get("combined_done", []):  # corrected together with the red checks
                if rounds_why:
                    self._plan_note(item, f"findings of review round {review_round} were corrected together with the "
                                          "red checks; the correction was not reviewed again")
                    self._review_debt(item, review_round, [entry["finding"] for entry in major])
                    break
                review_round += 1
                continue
            triage = dict(triage, confirmed=major)
            # correct, but audit no more; a spent run-wide budget (``*_batch``) stays the explicit limit it is
            final = bool(rounds_why) and not rounds_why.startswith("batch:") and item.options["review"]["final_correction"]
            done_before = len([number for number in state["corrections_at"] if number != review_round])
            if final:  # bounded by the review wall: the per-piece corrections target does not refuse it, a run-wide one does
                fixes_why = None if replayed else self._batch_allowance(item, "corrections", done_before, progress,
                                                                        emit=not replayed)
                final = not fixes_why
            else:
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
            before = self._product_snapshot(self.project) if final and not replayed else None
            report = self._execute(item, round_no, scout_text, prompts.review_correction(findings, triage))
            if report["status"] == "blocked":
                return self._finish(item, report, rows)
            if before is not None and before == self._product_snapshot(self.project):
                # no further review will look, so an unchanged tree is not "corrected": the findings stay open, loudly
                ids = [entry["finding"] for entry in major]
                self._defer_minor(item, findings, major)
                self._plan_note(item, f"the final correction of review round {review_round} changed no product file; "
                                      f"findings {', '.join(ids)} stay open")
                self._review_debt(item, review_round, ids, corrected=False)
                break
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
                self._review_debt(item, review_round, [entry["finding"] for entry in major])
                break
            review_round += 1
    return self._finish(item, report, rows)


def start_step(self, item: Item, key: str, *, role: str = "deterministic", route: Optional[str] = None) -> None:
    """Persist the boundary before work starts, including checks computed beside a review."""
    try:
        base = checks_mod.head(self.project)
    except RuntimeError:
        base = None
    dirty = recovery.dirty_paths(self.project) if key.startswith("checks.") else None
    with self.store.mutating():
        item.state.setdefault("steps", {})[key] = {
            "status": "started", "started_at": clock.utc_now(), "role": role, "route": route,
            "base_head": base, "attempt": item.claim.get("attempt_id"), "dirty_before": dirty}
        self._save()


def step(self, item: Item, key: str, run: Callable[[], Any], *, role: str = "deterministic",
         route: Optional[str] = None, verdict: Optional[Callable[[Any], str]] = None) -> Any:
    with self.store.mutating():
        steps = item.state.setdefault("steps", {})
        known = steps.get(key)
    if known and known.get("status") == "done":
        self.progress.emit("stage.skip", item=item.ref, stage=key, role=role, route=known.get("route"),
                           verdict=known.get("verdict"), message="closed earlier; not repeated")
        return known["result"]
    # Keep the fresh tokens this logical step already counted. Resetting the shared slot here let a resume,
    # and any overlap, admit a call the step had already spent (P3-STAGE-BUDGET-STATE-001).
    self._bind_stage(item, key)
    if item.options:
        self._run_clock(item)
        if role != "deterministic":
            self._admit_budget(item)
    if not known or known.get("status") != "started":
        self._start_step(item, key, role=role, route=route)
    self.progress.emit("stage.start", item=item.ref, stage=key, role=role, route=route)
    begin = time.monotonic()
    try:
        result = run()
    except Stop as stop:
        with self.store.mutating():
            steps[key] = {"status": "stopped", "code": stop.code, "ended": clock.utc_now()}
            self._save()
        self.progress.emit("stage.end", item=item.ref, stage=key, role=role, route=route, verdict="stopped",
                           reason_code=stop.code, duration_s=round(time.monotonic() - begin, 1),
                           message=stop.message)
        self._stage_event(item, key, "refused" if stop.code != "TIMEOUT" else "timeout")
        raise
    tokens = dict(self._stage_bucket())
    said = verdict(result) if verdict else "done"
    with self.store.mutating():
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
        self._admit_budget(item)
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
    # the work source cannot mark its own layers trusted: only the invocation layers below are
    layers = [{key: value for key, value in layer.items() if key != "trusted"} for layer in item.claim.get("options") or []]
    if self.run_doc.get("options_file"):
        named, kept = Path(self.run_doc["options_file"]), self.directory / OPTIONS_COPY
        origin = named if named.is_file() or not kept.is_file() else kept  # an edited file still wins on resume
        try:
            found = json.loads(origin.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise Stop("OPTIONS_INVALID", f"{origin}: {error}") from None
        layers.append({"source": "invocation:--options", "options": found, "trusted": True})
    if self.run_doc.get("grouped") is not None:
        layers.append({"source": "invocation:--batch" if self.run_doc["grouped"] else "invocation:--no-batch",
                       "options": {"session": {"executor": "handoff" if self.run_doc["grouped"] else "per-item"}},
                       "trusted": True})
    flags = {key: self.run_doc[name] for key, name in (("fence", "fence"), ("extra_paths", "extra_paths"))
             if self.run_doc.get(name)}
    if flags:
        layers.append({"source": "invocation:--fence/--allow-path", "options": {"scope": flags}, "trusted": True})
    try:
        item.options, item.sources = opts.effective(self.conductor, item.policy, layers)
        item.options["scope"]["extra_paths"] = opts.checked_extra_paths(item.options["scope"]["extra_paths"], self.project)
    except opts.OptionsError as error:
        raise Stop(error.code, error.message) from None
    planned = item.input_doc.get("review_rounds_max")  # the plan's bound lowers the target, never raises it
    if isinstance(planned, int) and 0 < planned < item.options["limits"]["review_rounds"]:
        item.options["limits"]["review_rounds"] = planned
        item.sources["limits.review_rounds"] = "plan:review.rounds_max"
    if persist:
        self.state["on_blocked"] = item.options["on_blocked"]
        # Raises are a state overlay, never a rewrite of the piece's recorded options.
        if self.state.get("limit_raises") and (item.directory / "options.json").is_file():
            return
        records.write(item.directory / "options.json", {
            "scenario": scenario, "options": records.options_layer(item.options), "sources": item.sources,
            "digest": opts.digest(item.options), "claim_route": item.claim.get("route")}, "item-options")
