"""Decisions of a piece (P7.6): the answers of its questions become accepted decisions of the work source after register,
and a later run of the same piece answers the same question from them. Both sides use the key of a question
(:func:`orch.conductor.questions.question_key`): the same meaning of the same piece, never only the same id."""
from __future__ import annotations

from orch.conductor import questions as questions_mod
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure import clock


def reuse_decisions(self, item: Item, key: str, waiting: list) -> list:
    """The questions of ``waiting`` that an accepted decision of the input already answers (``QUESTION_REUSED``): the same
    question of the same piece (``question_key`` and the full ``question_digest``) and a value this question can take.
    approval and credential are never reused. A decision that names the question but does not fit it is
    ``QUESTION_REUSE_REFUSED`` (``key``, ``digest`` or ``value``) and the question goes the ordinary way."""
    decisions = item.input_doc.get("decisions") or []
    if not decisions:
        return waiting
    left, now = [], clock.utc_now()
    for entry in waiting:
        if entry.get("auto_answered"):  # a question answered by a decision, a policy or the advisor once goes to a person
            left.append(entry)
            continue
        found, value, refused = questions_mod.reusable(item.ref, entry, decisions)
        if found is None:
            if refused:
                self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_REUSE_REFUSED",
                                   message=f"a decision names question {entry['id']} but is not used (reason: {refused})")
            left.append(entry)
            continue
        entry["resolution"] = {"value": value, "by": f"decision:{found['ref']}", "at": now}
        entry["status"], entry["auto_answered"], entry["applied_at"] = "applied", True, now
        entry["question_key"] = questions_mod.question_key(item.ref, entry)
        entry["question_digest"] = questions_mod.question_digest(item.ref, entry)
        self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_REUSED",
                           message=f"question {entry['id']} answered by the accepted decision {found['ref']}")
    return left


def decision_requests(self, item: Item) -> list:
    """The ``source decision`` requests of a registered piece: every question answered by a person, the advisor or the
    panel (not by policy defaults, not by an earlier decision) and every advice the conductor applied on its own
    (``advice_applied``). approval and credential are never recorded."""
    found = []
    where = [self._relative(item.directory / questions_mod.FILE)]
    for entry in self._questions(item).values():
        resolution = entry.get("resolution")
        if (entry["status"] != "applied" or not resolution or entry["kind"] not in questions_mod.REUSABLE_KINDS
                or resolution["by"] == "policy" or str(resolution["by"]).startswith("decision:")):
            continue
        by = resolution["by"]
        authority = by if by in ("advisor", "panel") else "owner"
        advice = entry.get("advice") or {}
        question = {key: entry[key] for key in ("id", "revision", "kind", "text", "options", "answer_schema") if key in entry}
        rationale = (f"{authority.capitalize()} recommends {advice.get('recommendation')} ({advice.get('confidence')} "
                     f"confidence): {advice.get('file')}" if authority != "owner" and advice
                     else f"Answered by {by}: {questions_mod.decision_text(entry)}")
        found.append((question, resolution, authority, rationale, where + ([advice["file"]] if advice.get("file") else [])))
    for applied in item.state.get("advice_applied") or []:
        question = {"id": f"advice-{applied['number']}", "revision": 1, "kind": "decision", "text": applied["problem"],
                    "options": applied["options"]}
        resolution = {"value": applied["recommendation"], "by": applied["by"], "at": applied["at"]}
        found.append((question, resolution, applied["by"],
                      f"{applied['by'].capitalize()} recommends {applied['recommendation']} ({applied['confidence']} "
                      f"confidence): {applied['file']}", [applied["file"]]))
    return [{"question": question, "question_key": questions_mod.question_key(item.ref, question),
             "question_digest": questions_mod.question_digest(item.ref, question),
             "resolution": {key: value for key, value in resolution.items() if key in ("value", "by", "at")},
             "authority": authority, "rationale": rationale, "evidence": evidence}
            for question, resolution, authority, rationale, evidence in found]


def record_decisions(self, item: Item) -> None:
    """After a successful register: each answer becomes an accepted decision of the piece in the work source. A source
    that cannot take it is the info ``DECISION_NOT_RECORDED`` (in ``_record_decision``); the piece and the run do not
    change. Never earlier: the decision is part of the input of the piece and would make an answer that waits stale."""
    for request in decision_requests(self, item):
        self._record_decision(item, request)
