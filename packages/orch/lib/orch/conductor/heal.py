"""Healing of role results: the form of a closed result is mended by rule before it is validated.

A role result is data for people and for the work source; its strict schema is there to catch wrong meaning, not a
wrong form. Repeating a role because of a form costs a whole run of it (10 to 30 minutes for an executor), so every
mismatch that has exactly one honest reading is mended here, and every mend is said: ``heal`` returns the notes, and a
stage-report carries them as a ``note`` issue.

The law of the mend (I9): it keeps the meaning of the result or moves it toward caution, never away from it. The orders
are ``done`` > ``done_with_deviations`` > ``done_pending_checks`` > ``blocked`` for a status and ``GREEN`` > ``ATTENTION``
> ``RED`` for a verdict (``domain.semantics``). So a mend never raises a status or a verdict, never drops an issue, a
finding, a question or a check row, never lowers a severity, never turns an escalation or a blocker into another kind
and never sets a deviation outcome to ``accepted`` by itself. What a report names impossibly is completed on the
cautious side: a ``done_with_deviations`` without a deviation gets a follow-up deviation, a ``done_pending_checks``
without a pending issue gets one (the conductor checks then decide), an escalation in a report that is not ``blocked``
makes it ``blocked``. ``changed_paths`` are not touched (the conductor reads them from git), no check, verdict or
finding is invented, a verdict ``ATTENTION`` or ``RED`` without findings is not made ``GREEN``, and a triage that
leaves a finding out is not completed — those go to the repair and, failing that, to a repeat of the role. The repair
is held to the same law: ``domain.semantics.drift`` compares its block with this mend of the role's own block.
"""
from __future__ import annotations

import re

from orch.conductor.domain.semantics import STATUS_RANK, VERDICT_RANK

CHECK_ID = re.compile(r"V[0-9]+")
FINDING_ID = re.compile(r"F[0-9]+")
ISSUE_KINDS = ("pending", "deviation", "blocker", "difficulty", "assumption", "note", "escalation")
DEVIATION_CLASSES = ("write_set", "spec_mismatch", "test_env", "docs", "dependency", "environment", "other")
DEVIATION_OUTCOMES = ("accepted", "follow_up", "owner_decision")
ISSUE_SEVERITIES = ("low", "medium", "high", "critical")
ISSUE_FIELDS = ("text", "kind", "impact", "next", "class", "severity", "outcome", "auto_fixable", "evidence")
NO_IMPACT = "not stated by the executor"
STATUSES = tuple(STATUS_RANK)
VERDICTS = tuple(VERDICT_RANK)
SEVERITIES = ("Blocker", "Major", "Minor", "Nit")
CONFIDENCES = ("high", "medium", "low")


def heal(kind: str, doc: dict) -> tuple:
    """``(document, notes)``: ``doc`` with its form mended and what was mended; ``doc`` itself is not changed."""
    if not isinstance(doc, dict):
        return doc, []
    healer = {"stage-report": _stage_report, "review-findings": _review_findings,
              "triage-result": _triage_result}.get(kind)
    if healer is None:
        return doc, []
    notes: list = []
    return healer(dict(doc), notes), notes


def _word(value, allowed):
    """``value`` matched to one of ``allowed`` ignoring case, spaces and dashes; None when nothing matches."""
    if not isinstance(value, str):
        return None
    key = re.sub(r"[\s-]+", "_", value.strip()).lower()
    return next((option for option in allowed if option.lower() == key), None)


def _int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        return int(value.strip())
    return None


def _list(doc: dict, key: str, notes: list) -> list:
    value = doc.get(key)
    if value is None:
        notes.append(f"{key} was missing; an empty list is assumed")
        return []
    if isinstance(value, str):
        notes.append(f"{key} was one string; it is read as a list of one")
        return [value] if value.strip() else []
    return list(value) if isinstance(value, list) else value


# ------------------------------------------------------------------ stage-report

def _issue(raw, notes: list):
    if isinstance(raw, str) and raw.strip():
        notes.append("an open issue was a plain string; it is kept as a note")
        return {"text": raw.strip(), "kind": "note"}
    if not isinstance(raw, dict):
        return raw
    issue = {key: value for key, value in raw.items() if key in ISSUE_FIELDS}
    dropped = sorted(set(raw) - set(issue))
    if dropped:
        extra = "; ".join(f"{key}: {raw[key]}" for key in dropped if raw[key] not in (None, ""))
        if extra and isinstance(issue.get("text"), str):
            issue["text"] = f"{issue['text']} ({extra})"
        notes.append(f"open issue keys {', '.join(dropped)} folded into its text")
    kind = _word(issue.get("kind"), ISSUE_KINDS)
    if kind and kind != issue.get("kind"):
        issue["kind"] = kind
    for key in ("impact", "next"):
        if key in issue and (not isinstance(issue[key], str) or not issue[key].strip()):
            issue.pop(key)
    _deviation_fields(issue, notes)
    return issue


def _deviation_fields(issue: dict, notes: list) -> None:
    """The class, severity, outcome, auto_fixable and evidence of an issue mended; a deviation gets what it lacks.

    A word that matches no option is not guessed: it is folded into the text and the field takes its default
    (a deviation) or is dropped (any other kind). The defaults are the cautious reading: ``other``, ``follow_up``
    (the conductor never accepts a deviation on the executor's silence), and an impact that says nobody stated it.
    """
    folded = []
    for key, allowed in (("class", DEVIATION_CLASSES), ("severity", ISSUE_SEVERITIES), ("outcome", DEVIATION_OUTCOMES)):
        if key not in issue:
            continue
        word = _word(issue[key], allowed)
        if word:
            issue[key] = word
        else:
            folded.append(f"{key}: {issue.pop(key)}")
    if "auto_fixable" in issue and not isinstance(issue["auto_fixable"], bool):
        word = _word(issue["auto_fixable"], ("true", "false"))
        if word:
            issue["auto_fixable"] = word == "true"
        else:
            folded.append(f"auto_fixable: {issue.pop('auto_fixable')}")
    if "evidence" in issue:
        value = issue["evidence"]
        rows = [value] if isinstance(value, str) else value
        if isinstance(rows, list) and all(isinstance(row, str) and row.strip() for row in rows) and rows:
            issue["evidence"] = [row.strip() for row in rows]
        else:
            folded.append(f"evidence: {issue.pop('evidence')}")
    if folded and isinstance(issue.get("text"), str):
        issue["text"] = f"{issue['text']} ({'; '.join(folded)})"
        notes.append("open issue values " + ", ".join(entry.split(":")[0] for entry in folded) + " matched no option "
                     "and were folded into its text")
    if issue.get("kind") != "deviation":
        return
    filled = []
    for key, default in (("class", "other"), ("outcome", "follow_up"), ("impact", NO_IMPACT)):
        if key not in issue:
            issue[key] = default
            filled.append(key)
    if filled:
        notes.append(f"a deviation lacked {', '.join(filled)}; the defaults are other, follow_up and "
                     f"'{NO_IMPACT}'")


def _check_row(raw, notes: list):
    """``(row, foreign)``: a checks_run row in one of its two shapes, or the row of a command outside the checks."""
    if not isinstance(raw, dict):
        return raw, None
    if not CHECK_ID.fullmatch(str(raw.get("id", ""))):
        return None, raw
    if raw.get("cmd") or "exit" in raw:
        row = {"id": raw["id"], "cmd": raw.get("cmd") or raw.get("command") or "-", "exit": raw.get("exit")}
        code = _int(row["exit"])
        if code is None and isinstance(raw.get("verdict"), str):
            code = 0 if _word(raw["verdict"], ("pass",)) else (1 if _word(raw["verdict"], ("fail",)) else None)
        if code is not None:
            row["exit"] = code
    else:
        row = {"id": raw["id"], "procedure": raw.get("procedure") or "-", "verdict": raw.get("verdict")}
        verdict = _word(row["verdict"], ("pass", "fail"))
        if verdict:
            row["verdict"] = verdict
    if set(raw) - set(row) - {"command"}:
        notes.append(f"checks_run {raw['id']}: keys {', '.join(sorted(set(raw) - set(row) - {'command'}))} dropped")
    return row, None


def _stage_report(doc: dict, notes: list) -> dict:
    status = _word(doc.get("status"), STATUSES)
    if status and status != doc.get("status"):
        doc["status"] = status
    for key in ("changed_paths", "evidence", "checks_run", "open_issues"):
        doc[key] = _list(doc, key, notes)
    if not isinstance(doc.get("summary"), str) or not doc["summary"].strip():
        doc["summary"] = "(the role gave no summary)"
        notes.append("summary was empty")
    issues = [_issue(raw, notes) for raw in doc["open_issues"]]
    rows, foreign = [], []
    for raw in doc["checks_run"]:
        row, other = _check_row(raw, notes)
        if other is not None:
            foreign.append(other)
        elif row is not None:
            rows.append(row)
    if foreign:
        cmds = "; ".join(f"{row.get('id')}: {row.get('cmd') or row.get('procedure') or '-'} → "
                         f"{row.get('exit', row.get('verdict', '-'))}" for row in foreign)
        issues.append({"text": f"commands the executor ran outside the acceptance checks: {cmds}"[:900], "kind": "note",
                       "impact": "none", "next": "none"})
    doc["checks_run"] = rows
    kinds = {issue.get("kind") for issue in issues if isinstance(issue, dict)}
    if doc.get("status") == "done_with_deviations" and "deviation" not in kinds:
        issues.append({"text": "the executor reported done_with_deviations without naming the deviation",
                       "kind": "deviation", "class": "other", "outcome": "follow_up", "impact": NO_IMPACT})
        notes.append("status done_with_deviations named no deviation issue; a follow-up deviation says so")
    if doc.get("status") == "done_pending_checks" and "pending" not in kinds:
        issues.append({"text": "the executor named no pending check; the conductor checks decide", "kind": "pending"})
        notes.append("status done_pending_checks named no pending issue; a pending issue says so")
    if doc.get("status") != "blocked" and "escalation" in kinds:
        doc["status"] = "blocked"
        notes.append("an escalation was reported; the report is blocked for the owner")
    if doc.get("status") == "blocked" and "escalation" not in kinds:
        blocker = next((issue for issue in issues if isinstance(issue, dict) and issue.get("kind") == "blocker"), None)
        if blocker is not None:  # the blocker stays; the owner is escalated with its words
            issues.append({**{key: blocker[key] for key in ("impact", "next") if isinstance(blocker.get(key), str)},
                           "text": str(blocker.get("text") or doc["summary"])[:900], "kind": "escalation"})
            notes.append("a blocked report named its gap as a blocker; the blocker is kept and escalated to the owner")
        else:
            issues.append({"text": f"the executor reported blocked without naming the gap; its summary: {doc['summary']}"[:900],
                           "kind": "escalation", "next": "the owner reads the summary and the stream of the step"})
            notes.append("a blocked report named no escalation; one is made from its summary")
    doc["open_issues"] = issues
    return doc


# ------------------------------------------------------------------ review-findings

def _review_findings(doc: dict, notes: list) -> dict:
    verdict = _word(doc.get("verdict"), VERDICTS)
    if verdict and verdict != doc.get("verdict"):
        doc["verdict"] = verdict
    doc["findings"] = _list(doc, "findings", notes)
    for key in ("questions",):
        if key in doc:
            doc[key] = [item for item in _list(doc, key, notes) if isinstance(item, str) and item.strip()]
    if "residual_risk" in doc and not isinstance(doc["residual_risk"], str):
        doc["residual_risk"] = str(doc["residual_risk"] or "")
    seen, findings = set(), []
    for number, raw in enumerate(doc["findings"], start=1):
        if not isinstance(raw, dict):
            findings.append(raw)
            continue
        finding = dict(raw)
        if not FINDING_ID.fullmatch(str(finding.get("id", ""))) or finding["id"] in seen:
            fresh = next(f"F{n}" for n in range(number, number + 1000) if f"F{n}" not in seen
                         and all(str(other.get("id")) != f"F{n}" for other in doc["findings"] if isinstance(other, dict)))
            notes.append(f"finding id {finding.get('id')!r} is not unique or not F<number>; it is {fresh}")
            finding["id"] = fresh
        seen.add(finding["id"])
        for key, allowed in (("severity", SEVERITIES), ("confidence", CONFIDENCES)):
            word = _word(finding.get(key), allowed)
            if word:
                finding[key] = word
        if finding.get("confidence") not in CONFIDENCES:
            finding["confidence"] = "medium"
            notes.append(f"finding {finding['id']} had no known confidence; medium is assumed")
        if not finding.get("basis"):
            finding["basis"] = "correctness"
            notes.append(f"finding {finding['id']} had no basis; correctness is assumed")
        if "reproduction" in finding and not (isinstance(finding["reproduction"], str) and finding["reproduction"].strip()):
            finding.pop("reproduction")
        findings.append(finding)
    doc["findings"] = findings
    severe = any(isinstance(item, dict) and item.get("severity") in ("Blocker", "Major") for item in findings)
    if doc.get("verdict") == "GREEN" and severe:
        doc["verdict"] = "RED" if any(isinstance(item, dict) and item.get("severity") == "Blocker" for item in findings) \
            else "ATTENTION"
        notes.append(f"verdict GREEN with a Blocker or Major finding; the findings win: {doc['verdict']}")
    return doc  # an ATTENTION or RED without findings is not mended into GREEN: the repair or a repeat says why


# ------------------------------------------------------------------ triage-result

def _triage_result(doc: dict, notes: list) -> dict:
    for key in ("confirmed", "rejected"):
        doc[key] = _list(doc, key, notes)
    for key in ("confirmed", "rejected"):
        entries = []
        for raw in doc[key]:
            if not isinstance(raw, dict):
                entries.append(raw)
                continue
            entry = dict(raw)
            repro = entry.get("reproduction")
            if isinstance(repro, dict):
                repro = dict(repro)
                code = _int(repro.get("exit"))
                if code is not None:
                    repro["exit"] = code
                if not repro.get("observed"):
                    repro["observed"] = "(not described)"
                    notes.append(f"{key} {entry.get('finding')}: reproduction without an observation")
                entry["reproduction"] = repro
            elif key == "rejected" and repro is None:
                entry.pop("reproduction", None)
            entries.append(entry)
        doc[key] = entries
    return doc
