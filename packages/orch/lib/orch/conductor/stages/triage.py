"""The triage of review findings: confirmed or rejected, which confirmed ones are corrected now, and the plan notes of
the others."""
from __future__ import annotations

import shlex

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
                                 roles_dir=self.roles_dir, stub=self._stub(role, route), skills=self._skills(item, role),
                                 repo_rules=self._repo_rules(item, role), skill_texts=self._skill_texts(item, role),
                                 advice=advice)
        triage, meta = self._role(item, key, role, prompt, "triage-result",
                                  extra=lambda doc: contract.triage_problems(findings, doc))
        triage, verified = verify_rejections(self, item, key, findings, triage)
        return {"triage": triage, "verified": verified, **meta}

    found = self._step(item, key, run, role=role, route=self.label(route),
                       verdict=lambda result: f"confirmed {len(result['triage']['confirmed'])}, "
                                              f"rejected {len(result['triage']['rejected'])}")
    self._verdict_file(item)
    self._note_rejected(item, findings, found["triage"])
    return found["triage"]


def is_trivial_reproduction(cmd) -> bool:
    """A command that proves nothing: it cannot fail for a defect, so it cannot show that a finding does not hold. Only
    a standalone ``true``, ``:``, ``exit 0``, ``echo …`` or ``printf …`` (one optional trailing ``;``) is trivial. Anything
    with a shell operator (``;`` ``&`` ``|`` ``<`` ``>`` ``(`` ``)``), a command substitution, a second line or text the
    shell would not read the same way is not: it reaches the guarded rerun, which is the safe side."""
    if not isinstance(cmd, str) or "\n" in cmd or "\r" in cmd or "$(" in cmd or "`" in cmd:
        return False
    try:
        words = list(shlex.shlex(cmd, posix=True, punctuation_chars=True))
    except ValueError:
        return False
    if words and words[-1] == ";":
        words.pop()
    if not words or any(word and set(word) <= set(";&|<>()") for word in words):
        return False
    return words in (["true"], [":"], ["exit", "0"]) or words[0] in ("echo", "printf")


CHECKED_SEVERITIES = ("Blocker", "Major")


def verify_rejections(self, item: Item, key: str, findings: dict, triage: dict) -> tuple:
    """``(triage, verified)``: a rejected Blocker or Major finding stands rejected only when the conductor itself reran
    its reproduction read-only (``checks.run_reproduction``, I12) and saw the exit the triager reported. A trivial command,
    another exit, or a rerun that could not be made (the guard is unavailable, a timeout) restores the finding as
    confirmed (beacons ``TRIAGE_REPRO_TRIVIAL``, ``TRIAGE_REPRO_MISMATCH``, ``TRIAGE_REPRO_UNVERIFIED``): a cheap triager
    must not remove a real defect without proof. ``verified`` is ``[{finding, outcome: kept|restored, reason}]``; confirmed
    and Minor findings are not checked."""
    by_id = {found.get("id"): found for found in findings["findings"]}
    kept, restored, verified = [], [], []
    for entry in triage["rejected"]:
        found = by_id.get(entry["finding"], {})
        repro = entry.get("reproduction")
        if found.get("severity") not in CHECKED_SEVERITIES or not repro:
            kept.append(entry)
            continue
        name, reported = entry["finding"], repro["exit"]
        code, observed = "", reported
        if is_trivial_reproduction(repro["cmd"]):
            code, why = "TRIAGE_REPRO_TRIVIAL", f"the command {repro['cmd']!r} proves nothing"
        else:
            ran = checks_mod.run_reproduction(
                repro["cmd"], project=self.project, log=item.directory / "triage" / key.split(".", 1)[1] / f"{name}.log",
                timeout_s=item.options["limits"].get("triage_repro_timeout_s", opts.DEFAULT_LIMITS["triage_repro_timeout_s"]))
            if ran["guard"] != "protect":
                code, why = "TRIAGE_REPRO_UNVERIFIED", f"the rerun was not made read-only ({ran['guard']}; log {ran['log']})"
            elif ran["exit"] != reported:
                code, observed = "TRIAGE_REPRO_MISMATCH", ran["exit"]
                why = f"reported exit {reported}, the conductor observed {ran['exit']}"
        if not code:
            kept.append(entry)
            verified.append({"finding": name, "outcome": "kept", "reason": f"the conductor observed the reported exit {reported}"})
            continue
        self.progress.emit("info", item=item.ref, stage=key, reason_code=code, message=f"{name}: {why}")
        verified.append({"finding": name, "outcome": "restored", "reason": why})
        restored.append({"finding": name, "reproduction": {"cmd": repro["cmd"], "exit": observed,
                                                           "observed": f"the conductor reran the rejection: {why}"},
                         "fix": f"{found.get('failure_scenario') or entry['reason']}; fix as the reviewer described"})
    if not restored:
        return triage, verified
    triage = {"confirmed": [*triage["confirmed"], *restored], "rejected": kept}
    issues = contract.problems(triage, "triage-result") + contract.triage_problems(findings, triage)
    if issues:
        raise ValueError(f"the triage after the reproduction check is outside its contract: {'; '.join(issues[:3])}")
    return triage, verified


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
