"""The end of a piece: the report it registers (git paths, deviations, notes, assumptions), the registration and the
commit through the work source."""
from __future__ import annotations

import re

from typing import Optional

from orch.conductor import checks as checks_mod, questions as questions_mod
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.infrastructure.files import write_json
from orch.conductor.infrastructure import work_source
from orch.conductor.infrastructure.work_source import FALLBACK_ARTIFACTS


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
        codes = [issue["text"].split(":", 1)[0] for issue in report.get("open_issues", [])
                 if issue["kind"] == "escalation" and re.match(r"^[A-Z][A-Z0-9_]*:", issue["text"])]
        self._beacon_event("orch.work.blocked", item, {"code": codes[0] if codes else "BLOCKED"})
    # the self-check claim stays with the stage-report of the run; the planner's register-report does not carry it
    body = {key: value for key, value in report.items()
            if key not in ("status", "questions", "review_recommendation", "self_check")}
    if status != "blocked":
        body["open_issues"] = [issue for issue in body["open_issues"] if issue["kind"] != "escalation"]
    else:  # a blocked registration takes no deviation issue (the register verb pairs it with done_with_deviations)
        body["open_issues"] = [dict(issue, kind="difficulty", text=f"deviation: {issue['text']}")
                               if issue["kind"] == "deviation" else issue for issue in body["open_issues"]]
    report_path = write_json(item.directory / "register-report.json", body)
    evidence = {row["id"]: row["evidence"] for row in rows or [] if row.get("evidence") and row["kind"] == "acceptance"}
    executor = self._actor(item.routes["executor"])
    registrar = self.conductor.get("registrar") or "orch/conductor"

    args = self._register_args(item, report_path, status, registrar, self.label(executor), evidence)
    closed = self._close(item, args) if self._closer_named(item) else None

    def said(result: dict) -> str:
        by_closer = closed is not None and closed["by"] == "closer" and result["outcome"] == "no-op"
        note = " (recorded by the closer)" if by_closer else ""
        return f"{result['outcome']} gate {result['gate']}{note}"

    self._step(item, "register", lambda: self._register(item, args), role="registrar", route=registrar, verdict=said)
    # A blocked piece is committed only under on_blocked = "report" and only when it changed nothing: then its
    # records (artifacts, the source's state) are all there is, and the next piece starts on a clean tree.
    records_only = status == "blocked" and item.options["on_blocked"] == "report" \
        and not report.get("changed_paths")
    if status == "blocked" and not records_only:
        item.state["partial"] = bool(report.get("changed_paths"))
    if (status != "blocked" or records_only) and item.policy.get("git_action") == "commit":
        paths = commit_paths(self, item, report)
        self._step(item, "commit", lambda: self._commit(item, paths),
                   verdict=lambda result: " ".join(part for part in (result["outcome"], result.get("sha"),
                                                                     result.get("message")) if part))
    return status


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
