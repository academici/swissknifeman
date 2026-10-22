"""What a role result means, apart from its form: the outcome of a result and the drift between two readings of it.

Healing and the report-fixer may change the form of a result, never its meaning, and its meaning may only move toward
caution (I9). ``outcome_key`` reduces a document to the fields that carry the meaning; ``drift`` says which of them got
better, shrank or were lost between two documents. Both are pure and read raw documents too (a missing or odd field is
skipped, never an error): they compare what a role said with what the conductor or the fixer made of it.
"""
from __future__ import annotations

import re

# More is more cautious: a repair may move a document up these orders, never down.
STATUS_RANK = {"done": 0, "done_with_deviations": 1, "done_pending_checks": 2, "blocked": 3}
VERDICT_RANK = {"GREEN": 0, "ATTENTION": 1, "RED": 2}
SEVERITY_RANK = {"Nit": 0, "Minor": 1, "Major": 2, "Blocker": 3}

ISSUE_COUNTS = ("escalation", "blocker", "pending", "deviation")
_CHECK_ID = re.compile(r"V[0-9]+")


def _name(rank: dict, value):
    """The key of ``rank`` that ``value`` spells (ignoring case, spaces and dashes), else None."""
    if not isinstance(value, str):
        return None
    key = re.sub(r"[\s-]+", "_", value.strip()).lower()
    return next((name for name in rank if name.lower() == key), None)


def _items(doc: dict, key: str) -> list:
    value = doc.get(key) if isinstance(doc, dict) else None
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def place(location) -> str:
    """The normalized place of a finding: no surrounding blanks, ``/`` for ``\\``, no leading ``./``; ``-`` when empty."""
    text = str(location if location is not None else "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text or "-"


def _words(value) -> str:
    """The identity text of a free-text field: blanks collapsed, case ignored; empty when it is not a string."""
    return re.sub(r"\s+", " ", value).strip().casefold() if isinstance(value, str) else ""


def _check_result(row: dict):
    """The result of a check row: its exit (a command check) or its verdict (a manual one) as one comparable value.
    ``pass`` and ``fail`` stand for exit 0 and 1; a value that spells nothing is kept as it was written."""
    value = row.get("exit") if "exit" in row else row.get("verdict")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"-?[0-9]+", text):
            return int(text)
        word = _name({"pass": 0, "fail": 1}, text)
        return {"pass": 0, "fail": 1}[word] if word else text
    return repr(value)


def outcome_key(kind: str, doc: dict) -> dict:
    """The fields of ``doc`` that carry its meaning, by kind (``stage-report``, ``review-findings``, ``triage-result``);
    an empty dict for any other kind. A stage-report: the rank of its status, the counts of its escalations, blockers,
    pending issues and deviations (and how many deviations are accepted, per deviation text, impact and class; one
    with none of the three is told apart only by its place among such ones), the blocking flag of each question by id and
    the result of each check row by id. A review: the rank of its verdict and, per finding (its normalized place and
    failure scenario, never its id or severity: the conductor renumbers ids and a repair may move severities), the
    severity ranks of the findings with that content from the highest down.
    A triage: the finding ids it confirmed and the ones it rejected."""
    if not isinstance(doc, dict):
        return {}
    if kind == "stage-report":
        issues = _items(doc, "open_issues")
        counts = {name: sum(1 for issue in issues if _name({name: 0}, issue.get("kind")) == name) for name in ISSUE_COUNTS}
        deviations: dict = {}  # per deviation content: how many are accepted (a deviation has no id; its content is its identity)
        bare = 0
        for issue in issues:
            if _name({"deviation": 0}, issue.get("kind")):
                accepted_here = 1 if _name({"accepted": 0}, issue.get("outcome")) else 0
                name = tuple(_words(issue.get(field)) for field in ("text", "impact", "class"))
                if not any(name):  # no content to tell it from another: only its place among such ones, never a shared identity
                    bare += 1
                    name = (f"(no content) #{bare}", "", "")
                deviations[name] = deviations.get(name, 0) + accepted_here
        questions = {str(row.get("id")): row.get("blocking") is True for row in _items(doc, "questions") if "id" in row}
        checks: dict = {}
        for row in _items(doc, "checks_run"):
            if _CHECK_ID.fullmatch(str(row.get("id", ""))):
                checks.setdefault(row["id"], []).append(_check_result(row))
        status = _name(STATUS_RANK, doc.get("status"))
        return {"status": status, "status_rank": STATUS_RANK.get(status), "issue_counts": counts,
                "deviations_accepted": sum(deviations.values()), "deviation_accepted": deviations, "questions": questions,
                "check_rows": {name: sorted(rows, key=str) for name, rows in checks.items()}}
    if kind == "review-findings":
        places: dict = {}
        for row in _items(doc, "findings"):
            severity = _name(SEVERITY_RANK, row.get("severity"))
            identity = (place(row.get("location")), _words(row.get("failure_scenario")))
            places.setdefault(identity, []).append(SEVERITY_RANK.get(severity, -1))
        verdict = _name(VERDICT_RANK, doc.get("verdict"))
        return {"verdict": verdict, "verdict_rank": VERDICT_RANK.get(verdict),
                "findings": {name: sorted(ranks, reverse=True) for name, ranks in places.items()}}
    if kind == "triage-result":
        return {key: sorted({str(row.get("finding")) for row in _items(doc, key) if row.get("finding")})
                for key in ("confirmed", "rejected")}
    return {}


def _severity_name(rank: int) -> str:
    return next((name for name, number in SEVERITY_RANK.items() if number == rank), "?")


def drift(kind: str, before: dict, after: dict) -> list:
    """What got better, shrank or was lost from ``before`` to ``after``, as lines like ``/status: blocked -> done``;
    empty when ``after`` means the same as ``before`` or is more cautious. A field ``before`` does not state (an unknown
    status) has nothing to compare and is not drift."""
    old, new = outcome_key(kind, before), outcome_key(kind, after)
    found: list = []
    if not old or not new:
        return found
    if kind == "stage-report":
        if old.get("status_rank") is not None and (new.get("status_rank") is None
                                                   or new["status_rank"] < old["status_rank"]):
            found.append(f"/status: {old['status']} -> {new.get('status')}")
        for name in ISSUE_COUNTS:
            if new["issue_counts"][name] < old["issue_counts"][name]:
                found.append(f"/open_issues: {name} {old['issue_counts'][name]} -> {new['issue_counts'][name]}")
        if new["deviations_accepted"] > old["deviations_accepted"]:
            found.append(f"/open_issues: deviations accepted {old['deviations_accepted']} -> {new['deviations_accepted']}")
        else:  # the total holds, but one deviation may have been accepted while another was turned to a follow-up;
            # a deviation (text, impact, class) the old report does not have counts as 0 accepted before
            texts = [name[0] for name in new["deviation_accepted"]]
            for name, count in new["deviation_accepted"].items():
                if count > old["deviation_accepted"].get(name, 0):
                    text, impact, kind = name
                    shared = f" (impact: {impact or '-'}, class: {kind or '-'})" if texts.count(text) > 1 else ""
                    found.append(f"/open_issues: deviation accepted: {text or impact or kind or '(no text)'}{shared}")
        for name, blocking in old["questions"].items():
            if name not in new["questions"]:
                found.append(f"/questions: {name} lost")
            elif blocking and not new["questions"][name]:
                found.append(f"/questions: {name} blocking true -> false")
        for name, rows in old["check_rows"].items():
            if name not in new["check_rows"]:
                found.append(f"/checks_run: {name} lost")
            elif new["check_rows"][name] != rows:
                found.append(f"/checks_run: {name} result {', '.join(map(str, rows))} -> "
                             f"{', '.join(map(str, new['check_rows'][name]))}")
    elif kind == "review-findings":
        if old.get("verdict_rank") is not None and (new.get("verdict_rank") is None
                                                    or new["verdict_rank"] < old["verdict_rank"]):
            found.append(f"/verdict: {old['verdict']} -> {new.get('verdict')}")
        for identity, ranks in old["findings"].items():
            name, later = identity[0], new["findings"].get(identity, [])
            if len(later) < len(ranks):
                found.append(f"finding lost at {name}")
                continue
            lowered = next((i for i, rank in enumerate(ranks) if later[i] < rank), None)
            if lowered is not None:
                found.append(f"severity lowered at {name}: {_severity_name(ranks[lowered])} -> "
                             f"{_severity_name(later[lowered])}")
    elif kind == "triage-result":
        for name in old["confirmed"]:
            if name in new["rejected"]:
                found.append(f"finding {name} confirmed -> rejected")
            elif name not in new["confirmed"]:
                found.append(f"finding {name} confirmed -> lost")
    return found
