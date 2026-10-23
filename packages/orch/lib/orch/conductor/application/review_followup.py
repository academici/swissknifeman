"""Deliver a group review's durable backlog in bounded executor assignments."""
from __future__ import annotations

import json
from pathlib import Path

from orch.contracts import canonical_digest
from orch.conductor import contract, prompts
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import write_json


def load(self, entry: dict, path: Path | None = None) -> dict:
    """Validate both the file contract and its binding to the follow-up input."""
    path = path or self.project / entry["path"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Stop("RECORD_INVALID", f"cannot read follow-up fix-brief {path}: {error}") from None
    problems = contract.problems(doc, "fix-brief")
    if problems or canonical_digest(doc) != entry["digest"]:
        raise Stop("RECORD_INVALID", f"invalid follow-up fix-brief {path}: "
                   + "; ".join(problems or ["digest differs from the execution-input"]))
    return doc


def correct(self, item, report: dict, rows: list, round_no: int, scout_text: str) -> tuple:
    """Replay saved assignments, then consume the remaining briefs within the correction allowance.

    The input owns the immutable queue; item state records each assigned executor number before it starts.
    Unassigned findings remain durable when a limit blocks completion, so settle cannot close the group.
    """
    provenance = item.input_doc.get("provenance", {})
    backlog = provenance.get("fix_briefs", []) if provenance.get("kind") == "review_followup" else []
    if not backlog:
        return rows, report, round_no
    assigned = item.state.setdefault("followup_corrections", [])
    for index, entry in enumerate(backlog):
        replayed = index < len(assigned)
        number = assigned[index] if replayed else round_no + 1
        path = item.directory / "fix-briefs" / f"executor.{number}.json"
        doc = load(self, entry, path if replayed and path.exists() else None)
        if not replayed:
            why = self._allowance(item, "corrections", self._piece_count(item.state, "corrections_at"), False)
            if why:
                debt = []
                for pending in backlog[index:]:
                    found = load(self, pending)
                    debt.extend(f"{row['id']} [{row['key']}] ({row['location']}); full: {pending['path']}"
                                for row in found["findings"])
                message = "Unresolved group review findings: " + "; ".join(debt) + "; " + why
                self._plan_note(item, message)
                return rows, self._blocked(report, "REVIEW_LIMIT", message), round_no
            assigned.append(number)
            item.state["corrections_used"] = self._piece_count(item.state, "corrections_at")
            self._save()
        write_json(path, doc)
        report = self._execute(item, number, scout_text, prompts.review_correction(doc))
        if report["status"] == "blocked":
            return rows, report, number
        rows = self._run_checks(item, number, report)
        rows, report, round_no = self._green(item, rows, report, number, scout_text)
        if report["status"] == "blocked":
            return rows, report, round_no
    return rows, report, round_no
