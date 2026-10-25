"""The end of a piece: the report it registers (git paths, deviations, notes, assumptions), the registration and the
commit through the work source."""
from __future__ import annotations

from typing import Optional

from orch.conductor import checks as checks_mod, questions as questions_mod
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.report import escalation_code
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import write_json
from orch.conductor.infrastructure import clock, commit_stages, work_source
from orch.conductor.infrastructure.work_source import FALLBACK_ARTIFACTS
from orch.conductor.stages import decisions
from orch.worksource_report import report_problems


def settle_pending(self, report: dict, rows: Optional[list]) -> dict:
    """``done_pending_checks`` is what the executor says while the checks it could not run still wait for the conductor;
    it is never registered. The piece closes on the result of the checks: they are green here (red ones were corrected
    or blocked the piece before), so the report becomes ``done`` and its ``pending`` issues are replaced by one note that
    names who proved what. When the conductor ran no check at all (every one skipped or none declared) nothing proves
    the work the executor could not prove: the piece is blocked, not closed on the executor's word."""
    if report["status"] != "done_pending_checks":
        return report
    ran = [row["id"] for row in rows or [] if not row.get("skipped")]
    skipped = [row["id"] for row in rows or [] if row.get("skipped")]
    if not ran:
        return self._blocked(report, "CHECKS_NOT_RUN", "the executor reported done_pending_checks, but the conductor ran no "
                             "acceptance check, so nothing proves the work; run the checks, or close the piece by hand "
                             "with its evidence")
    text = (f"checks the executor could not run were run by the conductor: {', '.join(ran)} green"
            + (f"; not run for this piece (skipped by cadence or kind): {', '.join(skipped)}" if skipped else ""))
    issues = [issue for issue in report.get("open_issues", []) if issue["kind"] != "pending"]
    return dict(report, status="done", open_issues=issues + [{"text": text, "kind": "note", "impact": "none", "next": "none"}])


def finish(self, item: Item, report: dict, rows: Optional[list]) -> str:
    deferred = item.state.get("deferred_findings", [])
    if deferred:
        self._plan_note(item, "Confirmed findings remain deferred after the correction allowance: "
                        + ", ".join(row["key"] for row in deferred)
                        + f"; full evidence: {self._relative(work_source.artifact_path(item, 'review-verdict.json'))}")
    report = self._correction_settle(item, report)  # the scope check of a correction round the conductor lost
    report = self._settle_pending(report, rows)
    changed = self._changed(item)
    if changed or any("changed" in (step.get("result") or {}) for key, step in done_steps(item.state.get("steps", {})).items()
                      if key.startswith("executor.") and isinstance(step.get("result"), dict)):
        report = dict(report, changed_paths=changed)  # git, not the report of the last round
    outside = self._outside(item)
    if outside and report["status"] != "blocked":
        expected = self._expected_outside(item, outside)
        note = f" (expected by the scout: {', '.join(expected)})"[:400] if expected else ""
        issue = {"text": "changed outside the write set: " + ", ".join(outside)[:800] + note, "kind": "deviation",
                 "impact": "the commit takes these paths with the piece; the reviewer saw them",
                 "next": "widen the write set of later items like this one",
                 "class": "write_set", "outcome": "accepted", "evidence": list(outside)[:20]}
        report = dict(report, status="done_with_deviations",
                      open_issues=list(report.get("open_issues", [])) + [issue])
    fixed = self._autofix_issues(item, report)
    if fixed:
        report = dict(report, open_issues=list(report.get("open_issues", [])) + fixed)
        if report["status"] == "done" and any(issue["kind"] == "deviation" for issue in fixed):
            report["status"] = "done_with_deviations"
    if report["status"] == "done" and any(issue["kind"] == "deviation" and issue["text"].startswith("CORRECTION_SCOPE_GREW")
                                          for issue in report.get("open_issues", [])):
        report = dict(report, status="done_with_deviations")  # the register verb pairs a deviation with this status
    notes = self._notes(item)
    if notes:
        report = dict(report, open_issues=list(report.get("open_issues", [])) + notes)
    assumed = [issue for issue in questions_mod.assumptions(self._questions(item))
               if issue not in report.get("open_issues", [])]
    if assumed:
        report = dict(report, open_issues=list(report.get("open_issues", [])) + assumed)
    status = report["status"]
    self._write_artifact(item, "stage-report.json", report)
    reported = {entry["issue"]["text"] for entry in item.state.get("autofixed", [])}
    for issue in report.get("open_issues", []):  # the fixed ones were recorded when their correction began
        if issue["kind"] == "deviation" and issue["text"] not in reported:
            self._deviation_recorded(item, issue)
    if status == "blocked":
        escalations = [issue["text"] for issue in report.get("open_issues", []) if issue["kind"] == "escalation"]
        codes = [code for code in (escalation_code(issue) for issue in report.get("open_issues", [])) if code]
        self._beacon_event("orch.work.blocked", item, {"code": codes[0] if codes else "BLOCKED"})
        waiting = waiting_questions(self, item, escalations)
        before = item.state.get("waiting") or {}
        if waiting:
            item.state["waiting"] = {"question_ids": waiting, "since": (before.get("since") if before.get("question_ids")
                                                                         == waiting else None) or clock.utc_now()}
        else:
            item.state.pop("waiting", None)
        item.escalation = {"code": codes[0] if codes else "BLOCKED",  # the item.end line and status show it
                           "text": " ".join((escalations[0] if escalations else report.get("summary") or "").split())[:300]}
    # the self-check claim stays with the stage-report of the run; the planner's register-report does not carry it
    body = {key: value for key, value in report.items()
            if key not in ("status", "questions", "review_recommendation", "self_check")}
    # the class of an escalation is the conductor's routing, not part of the register-report of the work source
    body["open_issues"] = [{key: value for key, value in issue.items() if key != "escalation_class"}
                           for issue in body.get("open_issues", [])]
    if status != "blocked":
        body["open_issues"] = [issue for issue in body["open_issues"] if issue["kind"] != "escalation"]
    else:  # a blocked registration takes no deviation issue (the register verb pairs it with done_with_deviations)
        body["open_issues"] = [dict(issue, kind="difficulty", text=f"deviation: {issue['text']}")
                               if issue["kind"] == "deviation" else issue for issue in body["open_issues"]]
    found = report_problems(body)
    if found:  # the conductor built a body the source would refuse after the work is done: a defect of the conductor
        raise Stop("REGISTER_REPORT_INVALID", f"{item.ref}: the register-report is outside work-source/v1 register-report: "
                   + "; ".join(found[:3]))
    report_path = write_json(item.directory / "register-report.json", body)
    evidence = {row["id"]: row["evidence"] for row in rows or [] if row.get("evidence") and row["kind"] == "acceptance"}
    review_only = item.input_doc.get("provenance", {}).get("kind") == "review"
    executor = self._actor(item.routes["reviewer" if review_only else "executor"])
    registrar = self.conductor.get("registrar") or "orch/conductor"

    receipt = work_source.review_receipt(item) if status != "blocked" and self._reviewing(item) else None
    args = self._register_args(item, report_path, status, registrar, self.label(executor), evidence,
                               review_receipt=self._relative(receipt) if receipt else None)
    closed = self._close(item, args) if not review_only and self._closer_named(item) else None

    def said(result: dict) -> str:
        by_closer = closed is not None and closed["by"] == "closer" and result["outcome"] == "no-op"
        note = " (recorded by the closer)" if by_closer else ""
        return f"{result['outcome']} gate {result['gate']}{note}"

    self._step(item, "register", lambda: self._register(item, args), role="registrar", route=registrar, verdict=said)
    if status != "blocked":  # a decision changes the input of the piece: never while a question of it still waits
        decisions.record_decisions(self, item)
    # A blocked piece is committed only under on_blocked = "report" and only when it changed nothing: then its
    # records (artifacts, the source's state) are all there is, and the next piece starts on a clean tree.
    records_only = status == "blocked" and item.options["on_blocked"] == "report" \
        and not report.get("changed_paths")
    if status == "blocked" and not records_only:
        item.state["partial"] = bool(report.get("changed_paths"))
    if not review_only and (status != "blocked" or records_only) and item.policy.get("git_action") == "commit":
        paths = commit_paths(self, item, report)
        split = {"role": "executor", "stage": "final", "trailers": commit_stages.stage_trailers(item, "final")} \
            if splitting(self, item) else {}  # the commit of what the stages left: records, plan files, other paths
        self._step(item, "commit", lambda: self._commit(item, paths, **split), verdict=commit_verdict)
    return status


def commit_verdict(result: dict) -> str:
    return " ".join(part for part in (result["outcome"], result.get("sha"), result.get("message")) if part)


def splitting(self, item: Item) -> bool:
    """The piece is committed in stages: ``commit.mode`` is ``implementation-and-fixes``, the run commits and the input is
    not a read-only review. ``final-only`` (the default) keeps the one commit after the registration."""
    return (item.options.get("commit", {}).get("mode") == "implementation-and-fixes"
            and item.policy.get("git_action") == "commit"
            and item.input_doc.get("provenance", {}).get("kind") != "review")


def stage_paths(self, item: Item) -> list:
    """The product paths a stage commit takes: what the executor rounds (and the checks) changed and the tree still holds
    as a change. Never the records of the piece (they wait for the final commit, I11), the local artifact folder or the
    runtime artifacts set aside."""
    local = FALLBACK_ARTIFACTS.as_posix() + "/"
    stray = (self._relative(work_source.stray_dir(item)) + "/") if item.artifacts else None
    dirty = set(self._dirty_paths())
    return sorted(path for path in self._changed(item)
                  if path in dirty and not path.startswith(local) and not (stray and path.startswith(stray)))


def stage_commit(self, item: Item, stage: str, review_round: Optional[int] = None, findings=()) -> None:
    """The commit of a stage of a split run: ``implementation`` (the checkpoint after the first green checks, before the
    review, role ``executor``) or ``correction.<n>`` (a green correction round of review round ``n``, role ``fix``, with
    the review and the finding keys it answers). Nothing happens in ``final-only``, and a stage that changed no product path
    commits nothing. The step is closed by its own receipt (``receipts/commit-<stage>.json``); the commit is recorded in
    ``state.commits`` with its parent, which is where the review of the piece starts."""
    if not splitting(self, item):
        return
    key = commit_stages.stage_step(stage)
    closed = done_steps(item.state.get("steps") or {}).get(key)
    if closed:  # a resume: the state may have been lost between the step and the record
        record_commit(self, item, stage, closed["result"])
        return
    paths = stage_paths(self, item)
    if not paths:
        return
    review = f"{self.run_id}/{item.ref}/review.{review_round}" if review_round else None
    trailers = commit_stages.stage_trailers(item, stage, review=review, findings=sorted(findings))
    role = "executor" if stage == "implementation" else "fix"
    result = self._step(item, key, lambda: self._commit(item, paths, role=role, stage=stage, trailers=trailers),
                        verdict=commit_verdict)
    record_commit(self, item, stage, result)


def record_commit(self, item: Item, stage: str, result: dict) -> None:
    """``state.commits`` of the piece gets ``{stage, sha, parent}``, once per stage and commit. A no-op commit has no sha
    and a sha git does not know has no parent: neither is recorded, and the review then starts from HEAD as before."""
    try:
        sha = checks_mod.git(self.project, "rev-parse", "--verify", f"{result.get('sha')}^{{commit}}").strip()
        parent = checks_mod.git(self.project, "rev-parse", "--verify", f"{sha}^").strip()
    except RuntimeError:
        return
    commits = item.state.setdefault("commits", [])
    if any(row["stage"] == stage and row["sha"] == sha for row in commits):
        return
    with self.store.mutating():
        commits.append({"stage": stage, "sha": sha, "parent": parent})
        self._save()


def waiting_questions(self, item: Item, escalations: list) -> list:
    """The ids of the blocking questions of the piece that still wait for an answer and that its escalations name
    (``QUESTION: <id> <text>``, also the advice questions ``orch-advice-<n>``). A denied question (``questions = deny``)
    is a refusal, not a wait."""
    return [name for name, entry in self._questions(item).items()
            if entry["status"] == "open" and entry.get("blocking")
            and any(text.startswith(f"QUESTION: {name} ") for text in escalations)]


def commit_paths(self, item: Item, report: dict) -> list:
    """The paths a commit of the piece takes: its changes, the records of its artifact folder when the source named one, the
    research results the source saved. The records are listed file by file (git: tracked and not ignored ones), never as the
    folder: a commit of the folder would take the runtime artifacts set aside in its ``stray`` subfolder too. The fallback
    artifact folder holds local records and is never committed (the source keeps what lasts at register): neither the
    folder nor a file in it, such as a research result the file source kept there."""
    local = FALLBACK_ARTIFACTS.as_posix() + "/"
    stray = (self._relative(work_source.stray_dir(item)) + "/") if item.artifacts else None
    records = set() if self._local_records(item) else artifact_records(self, item)
    return sorted(path for path in set(report.get("changed_paths", [])) | records | self._research_paths(item)
                  if not path.startswith(local) and not (stray and path.startswith(stray)))


def artifact_records(self, item: Item) -> set:
    """The files of the artifact folder of the piece a commit may take (not the ``stray`` runtime artifacts set aside)."""
    folder = self._relative(item.artifacts)
    stray = self._relative(work_source.stray_dir(item)) + "/"
    listed = checks_mod.git(self.project, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", folder)
    return {path for path in listed.split("\0") if path and not path.startswith(stray)}
