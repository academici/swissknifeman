"""The end of a piece: the report it registers (git paths, deviations, notes, assumptions), the registration and the
commit through the work source."""
from __future__ import annotations

from typing import Optional

from orch.conductor import questions as questions_mod
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure.files import write_json


def finish(self, item: Item, report: dict, rows: Optional[list]) -> str:
    changed = self._changed(item)
    if changed or any("changed" in (step.get("result") or {}) for key, step in item.state.get("steps", {}).items()
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
    write_json(item.artifacts / "stage-report.json", report)
    body = {key: value for key, value in report.items() if key not in ("status", "questions", "review_recommendation")}
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
        paths = sorted(set(report.get("changed_paths", [])) | {self._relative(item.artifacts) + "/"}
                       | self._research_paths(item))
        self._step(item, "commit", lambda: self._commit(item, paths),
                   verdict=lambda result: f"{result['outcome']} {result.get('sha') or ''}".strip())
    return status
