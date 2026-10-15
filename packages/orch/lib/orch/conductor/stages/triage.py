"""The triage of review findings: confirmed or rejected, which confirmed ones are corrected now, and the plan notes of
the others."""
from __future__ import annotations

from orch.conductor import checks as checks_mod, contract, options as opts, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain.report import notes


def role(self, item: Item) -> str:
    triage = (item.policy.get("review") or {}).get("triage") or {}
    return triage.get("role") or "triager"


def triage(self, item: Item, number: int, findings: dict, advice: str = "") -> dict:
    """The triage of review round ``number``; with ``advice`` the repeated triage of the findings the advisor read
    (``triage.<n>-a``), which then stands for the round."""
    role = self._triage_role(item)
    route = item.routes[role]
    key = f"triage.{number}" + ("-a" if advice else "")

    def run() -> dict:
        base = checks_mod.head(self.project)  # not the claim-time base: commits made meanwhile are not the candidate
        prompt = prompts.triager(item.input_doc, item=item.ref, step=key, base=base, findings=findings,
                                 roles_dir=self.roles_dir, skills=self._skills(item, role),
                                 repo_rules=self._repo_rules(item, role), skill_texts=self._skill_texts(item, role),
                                 advice=advice)
        triage, meta = self._role(item, key, role, prompt, "triage-result",
                                  extra=lambda doc: contract.triage_problems(findings, doc))
        return {"triage": triage, **meta}

    found = self._step(item, key, run, role=role, route=self.label(route),
                       verdict=lambda result: f"confirmed {len(result['triage']['confirmed'])}, "
                                              f"rejected {len(result['triage']['rejected'])}")
    self._verdict_file(item)
    self._note_rejected(item, findings, found["triage"])
    return found["triage"]


def split_confirmed(item: Item, findings: dict, triage: dict) -> tuple:
    """``(corrected, deferred)`` confirmed entries by ``review.correct_min_severity``: only the first go to a
    correction and make a new audit necessary."""
    ranks = {name.lower(): rank for rank, name in enumerate(opts.SEVERITIES)}
    floor = ranks[item.options["review"]["correct_min_severity"].lower()]
    severity = {found.get("id"): ranks.get(str(found.get("severity", "")).lower(), 0)
                for found in findings["findings"]}
    corrected = [entry for entry in triage["confirmed"] if severity.get(entry["finding"], 0) <= floor]
    deferred = [entry for entry in triage["confirmed"] if severity.get(entry["finding"], 0) > floor]
    return corrected, deferred


def note_rejected(item: Item, findings: dict, triage: dict) -> None:
    """A rejected finding at or above ``review.correct_min_severity`` is never lost: the reason travels as a plan
    note, because a single triager may reject a real defect as "outside the write set" and nobody picks it up."""
    ranks = {name.lower(): rank for rank, name in enumerate(opts.SEVERITIES)}
    floor = ranks[item.options["review"]["correct_min_severity"].lower()]
    by_id = {found.get("id"): found for found in findings["findings"]}
    deferred = notes(item)
    for entry in triage["rejected"]:
        found = by_id.get(entry["finding"], {})
        if ranks.get(str(found.get("severity", "")).lower(), len(ranks)) > floor:
            continue
        note = {"text": f"rejected {str(found.get('severity')).lower()} finding {found.get('location', '-')}: "
                        f"{found.get('failure_scenario', '')} Triage reason: {entry.get('reason', '-')}",
                "kind": "note", "impact": "a real defect rejected as outside this item stays open until someone owns it",
                "next": "the reviewer of the phase checks the rejection; a real defect gets an owner item"}
        if note not in deferred:
            deferred.append(note)


def defer_minor(item: Item, findings: dict, minor: list) -> None:
    """Confirmed minor findings are not corrected now: they travel as plan notes for the cleanup of the phase."""
    by_id = {found.get("id"): found for found in findings["findings"]}
    deferred = notes(item)
    for entry in minor:
        found = by_id.get(entry["finding"], {})
        note = ({"text": f"deferred {str(found.get('severity', 'Minor')).lower()} finding "
                                 f"{found.get('location', '-')}: {found.get('failure_scenario', '')}",
                         "kind": "note", "impact": "none for the acceptance; found by the review of this item",
                 "next": f"fix at the cleanup of the phase; fix idea: {entry.get('fix', '-')}"})
        if note not in deferred:  # a resumed run walks the closed rounds again
            deferred.append(note)
