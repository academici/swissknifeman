"""The scope of a correction round of review findings: the tree it started from, and what it changed beyond what it was
handed (``CORRECTION_SCOPE_GREW``)."""
from __future__ import annotations

import json

from orch.conductor import checks as checks_mod, scope as scopes
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.policies import routing as route_rules


def baseline_files(self, item: Item, round_no: int) -> None:
    """Keep once, before correction round ``round_no`` of review findings, the changed files of the tree
    (``state.correction_baselines["files-<n>"]``): a replay after the round compares with the tree the round started
    from, not with the corrected one. Not kept when the round is already closed."""
    key = f"files-{round_no}"
    with self.store.mutating():
        baselines = item.state.setdefault("correction_baselines", {})
        if key not in baselines and f"executor.{round_no}" not in done_steps(item.state.get("steps") or {}):
            try:
                files = checks_mod.dirty_files(self.project)
            except (RuntimeError, OSError):
                files = None
            baselines[key] = {"files": files}
            self._save()


def scope(self, item: Item, round_no: int, report: dict, brief: dict, role: str) -> dict:
    """``report`` after the check of a review correction round: the paths the round changed (the tree before it is
    ``correction_baseline_files``) beyond the paths of its findings, the tests of the write set, ``CHANGELOG.md`` and the
    documentation are ``CORRECTION_SCOPE_GREW``. On the executor route that is an accepted ``other`` deviation of the report
    and an info beacon, said once; on the bounded-implementer route the piece is blocked with
    ``CORRECTION_SCOPE_GREW: <paths>``."""
    entry = (item.state.get("correction_baselines") or {}).get(f"files-{round_no}")
    if not entry or entry.get("files") is None or report["status"] == "blocked":
        return report
    if "grew" not in entry:
        try:
            now = checks_mod.dirty_files(self.project)
        except (RuntimeError, OSError):
            return report
        changed = [path for path in scopes.own(checks_mod.changed_files(entry["files"], now),
                                               [*self._not_the_role(item), ".swissknifeman"])
                   if path not in set(item.state.get("source_paths") or [])]
        with self.store.mutating():
            entry["grew"] = route_rules.grown_paths(
                changed, {row["path"] for row in brief["findings"]}, (item.input_doc.get("scope") or {}).get("write_set"))
            entry["said"] = False
            self._save()
    grew = entry["grew"]
    if not grew:
        return report
    text = f"correction round {round_no} changed paths beyond its findings, the tests, CHANGELOG.md and docs: " \
           + ", ".join(grew[:20])
    if not entry.get("said"):
        with self.store.mutating():
            entry["said"] = True
            self._save()
        self.progress.emit("info", item=item.ref, stage=f"executor.{round_no}", role=role, reason_code="CORRECTION_SCOPE_GREW",
                           message=text)
    if role == "bounded-implementer":
        return self._blocked(report, "CORRECTION_SCOPE_GREW", ", ".join(grew[:20]))
    issue = {"text": f"CORRECTION_SCOPE_GREW: {text}", "kind": "deviation", "class": "other", "outcome": "accepted",
             "impact": "the next review round reads these paths", "next": "none", "evidence": list(grew[:20])}
    if any(known.get("text") == issue["text"] for known in report.get("open_issues", [])):
        return report  # settled again on a replay: the report already carries it
    return dict(report, open_issues=[*report.get("open_issues", []), issue])


def settle(self, item: Item, report: dict) -> dict:
    """``report`` with the scope check of every closed review correction round (``executor.<n>`` done, a baseline kept by
    :func:`baseline_files`): the check right after a round is lost when the conductor stops between the saved round and
    the check, and a resume that finds the candidate changed goes on to the next review without it. Called before each
    review round and before the piece finishes; a round that was checked already adds nothing."""
    steps = done_steps(item.state.get("steps") or {})
    for key in sorted((item.state.get("correction_baselines") or {}), key=lambda name: name.rpartition("-")[2].zfill(6)):
        kind, _, number = key.rpartition("-")
        step = steps.get(f"executor.{number}")
        brief = item.directory / "fix-briefs" / f"executor.{number}.json"
        if kind != "files" or step is None or not brief.is_file():
            continue
        report = scope(self, item, int(number), report, json.loads(brief.read_text(encoding="utf-8")),
                       step.get("role") or "executor")
    return report
