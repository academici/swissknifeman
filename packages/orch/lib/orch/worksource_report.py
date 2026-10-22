"""The register-report of a work source: the report a ``register`` request carries (``work-source/v1``
``register-report``).

The schema closes the fields; ``report_semantics`` keeps the rules a JSON Schema cannot state, the same ones the
``check_report`` of the planner bridge applies: a ``checks_run`` id appears once, and a text keeps a character once
Unicode whitespace is stripped (the schema pattern ``\\S`` only knows ASCII whitespace). The conductor checks the body
before it writes ``register-report.json`` and the file source before it records it; both use ``report_problems``.
``refusal_code`` names the refusal the plan source gives the same report: ``REGISTER_UNCLASSIFIED`` for an issue that
is not an object with a text and a known kind, ``REGISTER_REPORT_INVALID`` for anything else.
"""
from __future__ import annotations

import re

from orch.worksource import REPORT_KIND, problems

ISSUE_KINDS = ("pending", "deviation", "blocker", "difficulty", "assumption", "note", "escalation")
_TEXT_LISTS = ("changed_paths", "evidence")
_ISSUE_TEXTS = ("text", "impact", "next")
_ISSUE_AT = re.compile(r"^/open_issues/([0-9]+)(?:/|:)")


def _blank(value) -> bool:
    return isinstance(value, str) and not value.strip()


def report_semantics(body) -> list[str]:
    """``pointer: message`` lines of the rules the schema does not express; empty when there are none (a body of the
    wrong shape is the schema's to report)."""
    if not isinstance(body, dict):
        return []
    found = []
    if _blank(body.get("summary")):
        found.append("/summary: is blank")
    for field in _TEXT_LISTS:
        values = body.get(field)
        for index, value in enumerate(values if isinstance(values, list) else []):
            if _blank(value):
                found.append(f"/{field}/{index}: is blank")
    seen = set()
    checks = body.get("checks_run")
    for index, check in enumerate(checks if isinstance(checks, list) else []):
        if not isinstance(check, dict):
            continue
        for key in ("cmd", "procedure"):
            if _blank(check.get(key)):
                found.append(f"/checks_run/{index}/{key}: is blank")
        if isinstance(check.get("id"), str):
            if check["id"] in seen:
                found.append(f"/checks_run/{index}/id: repeats {check['id']}")
            seen.add(check["id"])
    issues = body.get("open_issues")
    for index, issue in enumerate(issues if isinstance(issues, list) else []):
        if not isinstance(issue, dict):
            continue
        for key in _ISSUE_TEXTS:
            if _blank(issue.get(key)):
                found.append(f"/open_issues/{index}/{key}: is blank")
        rows = issue.get("evidence")
        for row, value in enumerate(rows if isinstance(rows, list) else []):
            if _blank(value):
                found.append(f"/open_issues/{index}/evidence/{row}: is blank")
    return found


def report_problems(body) -> list[str]:
    """Every problem of ``body`` as a register-report: the schema first, then ``report_semantics``."""
    return problems(body, REPORT_KIND) + report_semantics(body)


def _unclassified(issue) -> bool:
    return not isinstance(issue, dict) or not isinstance(issue.get("text"), str) or not issue["text"].strip() \
        or issue.get("kind") not in ISSUE_KINDS


def refusal_code(body, found: list[str]) -> str:
    """The code of a refusal of ``body`` with the problems ``found``, as the plan source orders it: a problem of the
    report itself comes first (``REGISTER_REPORT_INVALID``); otherwise the first issue with a problem decides, and an
    issue that is not an object with a text and a known kind is ``REGISTER_UNCLASSIFIED``."""
    issues = body.get("open_issues") if isinstance(body, dict) else None
    places = [_ISSUE_AT.match(line) for line in found]
    if not found or not isinstance(issues, list) or not all(places):
        return "REGISTER_REPORT_INVALID"
    first = min(int(place.group(1)) for place in places)
    return "REGISTER_UNCLASSIFIED" if _unclassified(issues[first]) else "REGISTER_REPORT_INVALID"
