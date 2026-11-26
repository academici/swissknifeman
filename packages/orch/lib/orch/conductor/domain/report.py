"""The closed result of a role and the report a piece registers: the result block of an answer, what a closed report
cannot say, the escalation that blocks a report and the plan notes it carries."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional

from orch.conductor.domain.item import done_steps

_FENCE_BLOCK = re.compile(r"(?P<fence>`{3,})(?:json[ \t]+(?=[A-Za-z0-9_-]))?(?P<tag>[A-Za-z0-9_-]*)[ \t]*\n(?P<body>.*?)\n[ \t]*(?P=fence)[ \t]*(?:\n|$)", re.S)
_EVIDENCE_CHECK = re.compile(r"^V[0-9]+$")


def finding_key(finding: dict) -> str:
    """Identity of an exact repeated finding, independent of line numbers and numeric examples."""
    path = finding.get("location", "").split(":", 1)[0]
    scenario = " ".join(re.sub(r"\d+", "", finding.get("failure_scenario", "").lower()).split())[:160]
    text = f"{path}\n{finding.get('basis', '').lower()}\n{scenario}"
    return "fk-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def json_block(text: str, tag: str):
    """``(document, error)``: the JSON object of the last fenced block tagged ``tag`` (else the last ``json`` block)."""
    blocks = list(_FENCE_BLOCK.finditer(text or ""))
    chosen = [match for match in blocks if match["tag"] == tag] or [match for match in blocks if match["tag"] == "json"]
    if not chosen:
        return None, f"no fenced `{tag}` block in the answer"
    try:
        doc = json.loads(chosen[-1]["body"])
    except ValueError as error:
        return None, f"the `{tag}` block is not JSON: {error}"
    if not isinstance(doc, dict):
        return None, f"the `{tag}` block is not a JSON object"
    return doc, None


NO_WRITE_SET = "no fenced `write-set` block in the answer"


def write_set_block(text: str):
    """``(document, error, shown)``: the JSON object of the last fenced ``write-set`` block of a scout answer (the
    ``json write-set`` form is the same block), and the answer without its ``write-set`` blocks. No fallback to
    another ``json`` block: a hint is only what the scout tagged as one."""
    found = [match for match in _FENCE_BLOCK.finditer(text or "") if match["tag"] == "write-set"]
    if not found:
        return None, NO_WRITE_SET, text
    shown = text
    for match in reversed(found):
        shown = shown[:match.start()] + shown[match.end():]
    try:
        doc = json.loads(found[-1]["body"])
    except ValueError as error:
        return None, f"the `write-set` block is not JSON: {error}", shown.rstrip() + "\n"
    if not isinstance(doc, dict):
        return None, "the `write-set` block is not a JSON object", shown.rstrip() + "\n"
    return doc, None, shown.rstrip() + "\n"


def evidence_paths(evidence: list) -> list:
    """The repository paths an issue names as evidence: ``path:line`` and ``path:line-line`` lose their lines; a check
    id (``V1``) is not a path."""
    return [re.sub(r":[0-9]+(?:-[0-9]+)?$", "", text) for text in evidence
            if isinstance(text, str) and text and not _EVIDENCE_CHECK.match(text)]


def continued(steps: dict) -> set:
    """The executor rounds that a later round of the same number continued after a policy answer (``executor.1`` by
    ``executor.1-q1``, that by ``executor.1-q2``): they reported ``blocked`` but are not where the piece stopped."""
    found = set()
    for key in done_steps(steps):
        match = re.fullmatch(r"(executor\.[0-9]+)(?:-q([0-9]+))?", key)
        if match and match.group(2):
            number = int(match.group(2))
            found.add(match.group(1) if number == 1 else f"{match.group(1)}-q{number - 1}")
    return found


def report_problems(report: dict) -> list:
    """What the closed stage-report cannot say: deviations without a deviation issue, a blocked report without an
    escalation, an escalation in a report that is not blocked."""
    kinds = {issue["kind"] for issue in report.get("open_issues", [])}
    issues = []
    if report["status"] == "done_with_deviations" and "deviation" not in kinds:
        issues.append("/status: done_with_deviations needs a deviation issue")
    if report["status"] == "done_pending_checks" and "pending" not in kinds:
        issues.append("/status: done_pending_checks needs a pending issue naming the checks that could not run")
    if report["status"] == "blocked" and "escalation" not in kinds:
        issues.append("/status: blocked needs an escalation issue naming what is missing")
    if report["status"] != "blocked" and "escalation" in kinds:
        issues.append("/open_issues: an escalation belongs to a blocked report")
    if report["status"] != "blocked" and any(question["blocking"] for question in report.get("questions", [])):
        issues.append("/questions: a blocking question belongs to a blocked report")
    ids = [question["id"] for question in report.get("questions", [])]
    issues += [f"/questions: id {name} repeats" for name in sorted(set(ids)) if ids.count(name) > 1]
    return issues


def findings_problems(findings: dict) -> list:
    ids = [item["id"] for item in findings.get("findings", [])]
    issues = [f"/findings: id {name} repeats" for name in sorted(set(ids)) if ids.count(name) > 1]
    if findings["verdict"] == "GREEN" and any(item["severity"] in ("Blocker", "Major") for item in findings["findings"]):
        issues.append("/verdict: GREEN with a Blocker or Major finding")
    if findings["verdict"] != "GREEN" and not findings["findings"]:
        issues.append(f"/verdict: {findings['verdict']} without findings")
    return issues


ESCALATION_CODES = {"environment": "ENVIRONMENT_BLOCKED", "pre_existing_red": "PRE_EXISTING_RED",
                    "scope": "SCOPE_EXPANSION", "authority": "AUTHORITY_REQUIRED"}  # ``decision`` is a question, not a code
ENVIRONMENT_HINT = ("run orch.py doctor, check the sandbox settings, and grant a path outside the project with "
                    "--allow-path")
_CODED = re.compile(r"^[A-Z][A-Z0-9_]*:")


def is_coded(text: str) -> bool:
    return bool(_CODED.match(text or ""))


def escalation_code(issue: dict) -> Optional[str]:
    """The code of an escalation issue: the ``CODE:`` its text starts with, else the code of its ``escalation_class``."""
    if issue.get("kind") != "escalation":
        return None
    text = issue.get("text") or ""
    return text.split(":", 1)[0] if is_coded(text) else ESCALATION_CODES.get(str(issue.get("escalation_class") or ""))


def blocked(report: dict, code: str, text: str) -> dict:
    """``report`` turned blocked, with an escalation ``<code>: <text>`` for the owner."""
    found = dict(report)
    found["status"] = "blocked"
    found["open_issues"] = list(report.get("open_issues", [])) + [
        {"text": f"{code}: {text}", "kind": "escalation", "next": "the owner decides how to go on"}]
    return found


def severity_of(findings: dict, finding_id: str) -> str:
    found = next((entry for entry in findings.get("findings", []) if entry.get("id") == finding_id), {})
    return str(found.get("severity", "")).lower()


def place(findings: dict, finding_id: str) -> str:
    found = next((entry for entry in findings.get("findings", []) if entry.get("id") == finding_id), {})
    return f"{found.get('location', '-')}|{str(found.get('failure_scenario', ''))[:80]}"


def notes(item) -> list:
    """The plan notes the registration of the piece carries (``deferred_minors`` in runs before the rename)."""
    if "plan_notes" not in item.state and "deferred_minors" in item.state:
        item.state["plan_notes"] = item.state.pop("deferred_minors")
    return item.state.setdefault("plan_notes", [])


def plan_note(item, text: str) -> None:
    note = {"text": text, "kind": "note", "impact": "the run of this piece went its own way here",
            "next": "a reviewer of the phase may look at it"}
    found = notes(item)
    if note not in found:
        found.append(note)
