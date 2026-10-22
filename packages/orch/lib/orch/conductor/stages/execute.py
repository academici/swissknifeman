"""Executor rounds: the prompt of a round, the questions it asks, the deviations fixed inside the piece, and what the
roles really changed in the tree."""
from __future__ import annotations

import json
import os
import shutil
from typing import Optional

from aicore.util.digest import sha256_hex

from orch.contracts import required_digest
from orch.conductor import checks as checks_mod, options as opts, prompts, questions as questions_mod, scope as scopes
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.report import evidence_paths, report_problems
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock, work_source
from orch.conductor.infrastructure.files import REPORTS, safe, write_json
from orch.conductor.stages import advice


def execute(self, item: Item, number: int, scout_text: str, correction: str, fix: str = "") -> dict:
    """One executor round. A blocking question is queued, denied or, with a default, answered by policy once and the
    round is asked again (``executor.<n>-q<k>``); the answers of earlier questions reach every round."""
    again = 0
    while True:
        key = f"executor.{number}" + (f"-q{again}" if again else "")
        report = self._round(item, key, number, again > 0, scout_text, correction, fix)
        if report.get("questions") and f"executor.{number}-q{again + 1}" in done_steps(item.state.get("steps", {})):
            again += 1  # a resume walks the closed rounds again
            continue
        report, rerun = self._questioned(item, key, report)
        if not rerun:
            return report
        again += 1


def executor_round(self, item: Item, key: str, number: int, refresh: bool, scout_text: str, correction: str,
                   fix: str = "") -> dict:
    route = item.routes["executor"]

    def run() -> dict:
        if number > 1 or refresh:
            self._refresh_input(item)
        scouted = (done_steps(item.state.get("steps") or {}).get("scout") or {}).get("result") or {}
        researched = self._researched(item)
        note = (item.state.get("interrupted_note") or {}).get(key, "")
        corrected = "\n\n".join(text for text in (correction, note) if text)
        answers = questions_mod.answers_text(self._questions(item))
        prompt = prompts.executor(item.input_doc, item=item.ref, step=key, scout_text=scout_text,
                                  rules=item.options["rules"], correction=corrected, roles_dir=self.roles_dir, stub=self._stub("executor", route),
                                  targeted_tests=not item.options["checks"]["executor_runs_checks"],
                                  self_check=item.options["checks"].get("self_check") or (),
                                  skills=self._skills(item, "executor"),
                                  repo_rules=self._repo_rules(item, "executor"),
                                  skill_texts=self._skill_texts(item, "executor"),
                                  expected=item.state.get("expected"),
                                  answers=answers, fix=fix,
                                  scout_origin=scouted.get("cache") or "",
                                  batch=self._batch_note(item), research=researched.get("result"),
                                  research_origin=researched.get("path") or "",
                                  fence=self._scope_option(item, "fence", "plan"),
                                  extra_paths=self._scope_option(item, "extra_paths", []),
                                  file_tools=self._file_tools_rule(item),
                                  containers=not self._codex_sandboxed(route))
        resumed = self._resumed_prompt(item, key, correction, note, fix, answers)
        report, meta = self._role(item, key, "executor", prompt, "stage-report", extra=report_problems, resumed=resumed)
        if self._shared_session(item, "executor", item.routes["executor"]) \
                and (answers or "executor_session_answers" in self.state):  # the session has now seen every answer the prompt carried
            with self.store.mutating():
                self.state["executor_session_answers"] = [answer_key(row) for row in answers]
                self._save()
        write_json(item.directory / "reports" / f"{key}.json", report)
        return {"report": report, "changed": self._changed_now(item), **meta}

    found = self._step(item, key, run, role="executor", route=self.label(route),
                       verdict=lambda result: result["report"]["status"])
    notes = item.state.get("interrupted_note") or {}
    if key in notes:
        del notes[key]
        if not notes:
            item.state.pop("interrupted_note", None)
        self._save()
    report = found["report"]
    tracked = set_aside_runtime(self, item, key, found)
    moved = (item.state.get("relocated") or {}).get(key)
    if moved:
        report = dict(report, open_issues=list(report.get("open_issues", [])) + [{
            "text": "runtime artifacts left in the tree were moved to the artifacts of the piece, not committed: "
                    + ", ".join(f"{path} -> {where}" for path, where in sorted(moved.items()))[:800],
            "kind": "note", "impact": "none", "next": "none"}])
    if tracked and report["status"] != "blocked":
        report = self._blocked(report, "OUTSIDE_RUNTIME_ARTIFACT", "the executor changed tracked runtime artifacts "
                               "(history, not product files): " + ", ".join(tracked[:20])
                               + "; restore them from git and keep logs and evidence out of the project, then retry")
    outside = self._outside(item)
    stranger = scopes.foreign(outside, (item.input_doc.get("scope") or {}).get("write_set"),
                              self._scope_option(item, "extra_paths", []), self.project)
    if stranger and report["status"] != "blocked" and item.options["scope"].get("outside_module", "block") == "block":
        report = self._blocked(report, "OUTSIDE_MODULE", "the executor changed files of other modules: "
                               + ", ".join(stranger[:20]) + "; add them to the item's task_files or set them aside, then retry")
    if outside and report["status"] != "blocked" and item.options["scope"]["outside"] == "block":
        report = self._blocked(report, "OUTSIDE_WRITE_SET", "the executor changed paths the write set does not own: "
                               + ", ".join(outside[:20]) + "; widen the write set in the plan or set them aside, then retry")
    return report


def set_aside_runtime(self, item: Item, key: str, found: dict) -> list:
    """What the executor round ``key`` left under ``scope.runtime_paths`` (logs, evidence). New untracked files are moved
    (``os.replace``) to ``<artifacts of the piece>/stray/<path>``, said once as ``RUNTIME_ARTIFACT_RELOCATED`` and kept in
    ``state.relocated`` so ``changed`` does not count them (the checks of a round use it too, key ``checks.<n>``); the folders of the conductor itself are not touched. The tracked
    paths under them that changed are returned: they are history and cannot be moved."""
    patterns = self._scope_option(item, "runtime_paths", opts.DEFAULT_SCOPE["runtime_paths"])
    listed = scopes.own([path for path in found.get("changed") or [] if scopes.under(path, patterns)],
                        self._not_the_role(item))
    if not listed:
        return []
    fresh = set(checks_mod.untracked(self.project))
    moved = {}
    for path in listed:
        if path not in fresh:
            continue
        target = work_source.stray_dir(item) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(self.project / path, target)
        except OSError:  # another file system: copy, then remove
            shutil.move(str(self.project / path), str(target))
        moved[path] = self._relative(target)
    if moved:
        with self.store.mutating():  # the checks of a round run in a thread beside the review (I2)
            item.state.setdefault("relocated", {}).setdefault(key, {}).update(moved)
            self._save()
        self.progress.emit("info", item=item.ref, stage=key, reason_code="RUNTIME_ARTIFACT_RELOCATED",
                           message=f"{len(moved)} runtime artifact(s) left in the tree were moved to the artifacts of the piece: "
                                   + ", ".join(f"{path} -> {where}" for path, where in sorted(moved.items())[:5])
                                   + (" …" if len(moved) > 5 else ""))
    return scopes.tracked(self.project, [path for path in listed if path not in fresh])


def answer_key(row: dict) -> str:
    """Names an answer by what it says, so the session that has seen it is not told it again."""
    return sha256_hex(json.dumps([row["id"], row["text"], row["answer"], row["by"]], ensure_ascii=False,
                                 sort_keys=True).encode("utf-8"))


def resumed_prompt(self, item: Item, key: str, correction: str, note: str, fix: str, answers: list) -> Optional[list]:
    """The delta blocks of this round (``prompts.executor_resumed``) for a session that continues: what the round asks
    (the correction, the deviation to fix, the note of an interrupted round) and the answers the session has not seen,
    with the paths the earlier round of the piece changed. ``None`` when the round asks nothing the session lacks (the
    first round of a piece, a repeat of it): it is sent the whole prompt, as before. Whether the delta really goes is
    decided per attempt (``_delta_mode``)."""
    seen = set(self.state.get("executor_session_answers") or [])
    fresh = [row for row in answers if answer_key(row) not in seen]
    if not (correction or note or fix or fresh):
        return None
    steps = done_steps(item.state.get("steps") or {})
    earlier = [step["result"].get("changed") or [] for name, step in steps.items()
               if name.startswith("executor.") and name != key and isinstance(step.get("result"), dict)]
    return prompts.executor_resumed(item=item.ref, step=key, correction=correction, answers=fresh, interrupted=note,
                                    fix=fix, changed_paths=earlier[-1] if earlier else [],
                                    targeted_tests=not item.options["checks"]["executor_runs_checks"],
                                    self_check=item.options["checks"].get("self_check") or ())


def batch_note(self, item: Item) -> str:
    """The run block of the executor prompt: every piece of the run with its title and state, so one shared session
    knows the whole batch from the first prompt."""
    refs = self.run_doc.get("items") or []
    mode = self._session_mode(item)
    if len(refs) < 2 or mode not in ("shared", "handoff") \
            or not self._shared_session(item, "executor", item.routes["executor"]):
        return ""
    claims = {value["ref"]: value for value in (self.state.get("claims") or {}).values()}
    rows, done_refs = [], []
    for ref in refs:
        done = (self.state["items"].get(ref) or {}).get("outcome")
        if ref != item.ref and done in ("done", "done_with_deviations"):
            done_refs.append(ref)
        mark = "this piece" if ref == item.ref else ("done and committed" if done in ("done", "done_with_deviations")
                                                     else "next" if done is None else done)
        title = (claims.get(ref) or {}).get("title")
        rows.append(f"- `{ref}`{' — ' + title if title else ''} ({mark})")
    if mode == "handoff":
        resumed = self.state.get("executor_session_item") == item.ref and bool(self.state.get("executor_session"))
        lines = ["## Run batch", "", "All pieces of this run are in progress; each piece has a session of its own, in order:",
                 *rows, "",
                 (f"You are resuming the session of {item.ref}; the instructions below are for its next round." if resumed
                  else f"You start {item.ref} in a fresh session. Keep the choices you make here compatible with the later "
                       "pieces and say in `open_issues` what the next piece must know."
                       + (" The earlier pieces are done and committed; their handoff follows: read the code they committed "
                          "only where this piece needs it." if done_refs else ""))]
        if not resumed:
            lines += [block for ref in done_refs for block in ("", handoff_of(self, ref))]
        return "\n".join(lines)
    resumed = bool(self.state.get("executor_session"))
    lines = ["## Run batch", "", "All pieces of this run are in progress and one session carries them in order:", *rows, "",
             (f"You are resuming that session: the pieces before {item.ref} are done and committed, what you learned stays "
              "valid (re-read only what this piece needs), and the instructions below are for this piece."
              if resumed else
              f"You start with {item.ref}; the later pieces arrive in this session as new messages, so keep the "
              "choices you make here compatible with them and say in `open_issues` what the next piece must know.")]
    return "\n".join(lines)


HANDOFF_ISSUES = 8  # the open issues of an earlier piece named in a handoff
HANDOFF_TEXT = 400  # characters of the summary and of each issue
HANDOFF_PATHS = 25  # changed paths named


def handoff_of(self, ref: str) -> str:
    """What a later piece of the run must know of the done piece ``ref``: its commit, summary, open issues and changed
    paths, from the report it registered (``register-report.json``), each part bounded."""
    state = self.state["items"].get(ref) or {}
    sha = ((done_steps(state.get("steps") or {}).get("commit") or {}).get("result") or {}).get("sha")
    try:
        report = json.loads((self.directory / safe(ref) / "register-report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    lines = [f"### Handoff of `{ref}`" + (f" (commit {sha[:12]})" if sha else "")]
    if report.get("summary"):
        lines += ["", str(report["summary"])[:HANDOFF_TEXT]]
    issues = [row for row in report.get("open_issues") or [] if isinstance(row, dict) and row.get("text")]
    if issues:
        lines += ["", "Open issues:"] + [f"- [{row.get('kind', 'note')}] {str(row['text'])[:HANDOFF_TEXT]}"
                                         for row in issues[:HANDOFF_ISSUES]]
    paths = [str(path) for path in report.get("changed_paths") or []]
    if paths:
        rest = len(paths) - HANDOFF_PATHS
        lines += ["", "Changed: " + ", ".join(f"`{path}`" for path in paths[:HANDOFF_PATHS])
                  + (f" and {rest} more" if rest > 0 else "")]
    return "\n".join(lines)


def autofixable(self, item: Item, report: dict) -> list:
    """The deviations of a finished round the conductor may have fixed: ``auto_fixable``, not a ``spec_mismatch`` and
    not left to the owner, every path of the evidence inside the write set (and at least one), in a piece that has
    acceptance checks to prove the fix. Whether the change is safe (no public API, no product decision, no security
    boundary) is the declaration of the role (``roles/executor.md``); only what can be checked is checked here."""
    write_set = (item.input_doc.get("scope") or {}).get("write_set")
    checks = [row for row in (item.input_doc.get("acceptance") or {}).get("checks", [])
              if row.get("kind", "acceptance") == "acceptance"]
    if report["status"] == "blocked" or not write_set or not checks:
        return []
    found = []
    for issue in report.get("open_issues", []):
        paths = evidence_paths(issue.get("evidence") or [])
        if (issue["kind"] == "deviation" and issue.get("auto_fixable") is True and issue.get("class") != "spec_mismatch"
                and issue.get("outcome") != "owner_decision" and paths and not scopes.outside(paths, write_set)):
            found.append(issue)
    return found


def autofix(self, item: Item, report: dict, round_no: int, scout_text: str) -> tuple:
    """``(report, round_no)``: one correction round for the fixable deviations of the executor report, when the
    ``corrections`` budget allows one (it is checked, not spent: the fix happens once per piece and leaves the review
    its own corrections); the checks that follow are the same ones. The deviation is kept in
    ``state.autofixed`` and settled by ``_finish``: accepted with a note when the piece ends green, as it was when not."""
    found = self._autofixable(item, report)
    state = item.state
    if not found:
        return report, round_no
    replayed = round_no in state["autofix_at"]
    done_before = len([number for number in state["autofix_at"] if number != round_no]) + len(state["corrections_at"])
    why = None if replayed else self._allowance(item, "corrections", done_before, False)
    if why:
        self.progress.emit("info", item=item.ref, reason_code="DEVIATION_AUTOFIX_SKIPPED",
                           message=f"{len(found)} auto_fixable deviation(s) stay as reported: {why}")
        return report, round_no
    if not replayed:
        state["autofix_at"].append(round_no)
        state.setdefault("autofixed", []).extend(
            {"issue": issue, "round": round_no, "event": self._deviation_recorded(item, issue)} for issue in found)
        self.progress.emit("info", item=item.ref, reason_code="DEVIATION_AUTOFIX",
                           message=f"correction {len(state['autofix_at'])}: {len(found)} auto_fixable deviation(s) "
                                   "are fixed in the write set, then the checks run again")
    self._save()
    round_no += 1
    return self._execute(item, round_no, scout_text, prompts.DEVIATION_FIX, prompts.fix_deviation(found)), round_no


def deviation_data(item: Item, issue: dict) -> dict:
    """``deviation_id`` (``<item>/dev-<n>``, n counting the deviations of the piece), ``class`` and ``outcome``."""
    seen = item.state.setdefault("deviation_ids", [])
    if issue["text"] not in seen:
        seen.append(issue["text"])
    return {"deviation_id": f"{item.ref}/dev-{seen.index(issue['text']) + 1}", "class": issue.get("class"),
            "outcome": issue.get("outcome")}


def deviation_recorded(self, item: Item, issue: dict) -> Optional[str]:
    """``orch.deviation.recorded`` for a deviation of a report; the id of the event."""
    return self._beacon_event("orch.deviation.recorded", item, {
        **self._deviation_data(item, issue), **({"auto_fixable": issue["auto_fixable"]}
                                               if isinstance(issue.get("auto_fixable"), bool) else {})})


def deviation_resolved(self, item: Item, issue: dict, recorded: Optional[str]) -> None:
    """``orch.deviation.resolved`` for a deviation a correction round closed; ``corrects`` is the recorded event."""
    if recorded:
        self._beacon_event("orch.deviation.resolved", item, {**self._deviation_data(item, issue), "corrects": recorded})


def autofix_issues(self, item: Item, report: dict) -> list:
    """The deviations of the fix rounds as the registration must carry them: accepted with a note when the piece is
    done, unchanged when it is not; none that the final report names itself."""
    carried = []
    for entry in item.state.get("autofixed", []):
        issue = entry["issue"]
        if any(known.get("text") == issue["text"] for known in report.get("open_issues", [])):
            continue  # the executor reported it again: it was not fixed
        if report["status"] == "blocked":
            carried.append(issue)
            continue
        number = item.state["autofix_at"].index(entry["round"]) + 1
        carried.append(dict(issue, outcome="accepted", next=f"fixed in correction {number}"))
        self._deviation_resolved(item, issue, entry.get("event"))
        self._plan_note(item, f"deviation fixed in correction {number}: {issue['text']}")
    return carried


def answer_digest(input_doc: dict) -> str:
    """Bind an answer to the substantive input, independently of source lifecycle and context rendering."""
    return required_digest(input_doc)


def questions(self, item: Item) -> dict:
    return self.state.setdefault("questions", {}).setdefault(item.ref, {})


def save_questions(self, item: Item) -> None:
    store = self._questions(item)
    if store:
        questions_mod.save(item.directory, self.run_id, item.ref, store)
    self._save()


def questioned(self, item: Item, key: str, report: dict) -> tuple:
    """``(report, rerun)``: the questions of a round recorded with their binding; a blocking one that waits turns the
    report into a blocked one (``QUESTION`` or, under ``questions = deny``, ``QUESTION_DENIED``); ``rerun`` when
    ``questions = defaults`` answered all of them from their defaults."""
    asked = report.get("questions") or []
    if not asked:
        return report, False
    store = self._questions(item)
    binding = {"run": self.run_id, "item": item.ref, "step": key, "input_digest": item.input_doc.get("digest"),
               "input_part_digest": answer_digest(item.input_doc)}
    new = questions_mod.record(store, asked, binding, clock.utc_now())
    waiting = questions_mod.blocking_open(store, asked)
    for entry in new:  # a round walked again by a resume adds nothing
        self._beacon_event("orch.agent.questioned", item, {
            "step": key, "question_id": entry["id"], "revision": entry["revision"], "blocking": bool(entry["blocking"])})
    mode = self.conductor.get("questions") or "queue"
    if mode == "advisor" and not self._advisor_on():
        self.progress.emit("info", item=item.ref, stage=key, reason_code="ADVISOR_DISABLED",
                           message="questions = advisor, but orch.advisor.enabled is false: the question is queued")
        mode = "queue"
    if waiting and mode == "deny":
        for entry in waiting:
            if entry["kind"] not in ("approval", "credential"):
                entry["status"] = "denied"
    elif waiting and mode == "defaults":
        now = clock.utc_now()
        for entry in list(waiting):
            if questions_mod.resolve_default(entry, now, advice.authority(self, item, "defaults")):
                waiting.remove(entry)
                self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_DEFAULT",
                                   message=f"question {entry['id']} answered by policy with its default")
    elif waiting and mode == "advisor":
        for entry in list(waiting):
            if self._advise_question(item, key, entry, report):
                waiting.remove(entry)
    for entry in waiting:
        if entry["kind"] in ("approval", "credential"):
            self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_OWNER_ONLY",
                               message=f"question {entry['id']} ({entry['kind']}) can only be answered by the owner")
    self._save_questions(item)
    if not waiting:
        return report, any(entry["status"] == "applied" and entry["binding"]["step"] == key
                           for entry in store.values())
    said = "; ".join(f"{entry['id']} {entry['text']}{self._advice_note(entry)}" for entry in waiting)
    self._beacon_event("orch.run.waiting", item, {"reason_code": "QUESTION", "step": key,
                                                  "question_ids": [entry["id"] for entry in waiting]})
    if mode == "deny" and all(entry["status"] == "denied" for entry in waiting):
        self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_DENIED", message=said[:300])
        return self._blocked(report, "QUESTION_DENIED", said), False
    self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_QUEUED",
                       message=f"{said[:240]}; answer with orch conduct answer, then resume --retry {item.ref}")
    blocked = report
    for entry in waiting:
        blocked = self._blocked(blocked, "QUESTION", f"{entry['id']} {entry['text']}{self._advice_note(entry)}")
    return blocked, False


def sync_questions(self, item: Item) -> None:
    """Take the answers written by ``orch conduct answer`` into the state and hand them to the executor, when the input
    is still the one they were asked on; an answer to another input is stale, its question is asked again."""
    store = self._questions(item)
    if not store:
        return
    with questions_mod.questions_lock(item.directory):
        questions_mod.merge_file(store, questions_mod.read(item.directory))
        applied, stale = questions_mod.apply(store, item.input_doc.get("digest"), answer_digest(item.input_doc), clock.utc_now())
        write_json(questions_mod.path(item.directory), questions_mod.document(self.run_id, item.ref, store))
        self._save()
    for name in applied:
        self.progress.emit("info", item=item.ref, reason_code="QUESTION_ANSWERED",
                           message=f"question {name} answered by {store[name]['resolution']['by']}")
    for name in stale:
        self.progress.emit("info", item=item.ref, reason_code="QUESTION_STALE",
                           message=f"the answer to {name} was given for an earlier input and is not used; it is asked "
                                   f"again as revision {store[name]['revision']}")
    waiting = [name for name, entry in store.items() if entry["status"] == "open"]
    if waiting:
        self.progress.emit("info", item=item.ref, reason_code="QUESTION_OPEN",
                           message=f"no answer yet to {', '.join(waiting)}")


def changed_now(self, item: Item) -> list:
    """The paths the roles have changed so far: the dirty tree without what the work source wrote when it claimed,
    the artifact folder, the plan folder of the input and the conductor reports."""
    source = set(item.state.get("source_paths") or [])
    foreign = scopes.untouched(self.project, self.state.get("foreign") or {})  # kept at the start, not changed since
    return [path for path in scopes.own(self._dirty_paths(), self._not_the_role(item))
            if path not in source and path not in foreign]


def not_the_role(self, item: Item) -> list:
    """Folders whose changes are never the role's work: the conductor reports, the artifact folder of the piece
    and the plan folder of the input."""
    return [REPORTS.as_posix(), self._relative(item.artifacts) if item.artifacts else "",
            str((item.input_doc.get("provenance") or {}).get("plan_dir") or "")]


def changed(self, item: Item) -> list:
    """Every path any executor round of the piece changed (git, not the reports) and the checks changed (``checks_changed``:
    a formatter or a generator), without the runtime artifacts that were set aside (``relocated``)."""
    steps = done_steps(item.state.get("steps", {}))
    found = set(item.state.get("adopted") or [])
    for key, step in steps.items():
        if key.startswith("executor.") and isinstance(step.get("result"), dict):
            found.update(step["result"].get("changed") or [])
    for paths in (item.state.get("checks_changed") or {}).values():
        found.update(paths)
    for moved in (item.state.get("relocated") or {}).values():
        found.difference_update(moved)
    return sorted(found)


def outside(self, item: Item) -> list:
    return scopes.outside(self._changed(item), (item.input_doc.get("scope") or {}).get("write_set"))


def expected_outside(item: Item, outside: list) -> list:
    """The paths outside the write set that the scout's hint (``state.expected``) names."""
    patterns = [row for key in ("paths", "tests") for row in ((item.state.get("expected") or {}).get(key) or [])]
    return [path for path in outside if any(scopes.matches(path, pattern) for pattern in patterns)]


def adopted(self, item: Item) -> list:
    """``run --adopt``: the changed paths taken over must lie in the write set of the piece. The artifact folder of
    the piece (evidence, review verdict of the earlier attempt) and the plan folder are allowed and are not
    counted as the role's changes."""
    adopted = scopes.own(item.state.get("adopted") or [], self._not_the_role(item))
    dirty = set(self._dirty_paths())
    adopted = [path for path in adopted if path in dirty or any(path.startswith(d.rstrip("/") + "/") for d in dirty)]
    item.state["adopted"] = adopted  # a stray file the owner has removed since the snapshot is no longer adopted
    stray = scopes.outside(adopted, (item.input_doc.get("scope") or {}).get("write_set"))
    if stray:
        raise Stop("WORKTREE_DIRTY", f"run --adopt takes only changes inside the write set of {item.ref}; outside it: "
                                     + ", ".join(stray[:10]))
    return adopted
