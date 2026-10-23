"""The correction packages of a round: what the executor is asked to fix (checks, review, deviation, advice,
an interrupted attempt) and the answers it is given."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Optional

from orch.conductor.prompts.blocks import _fence


def self_check_missing(commands) -> str:
    """The correction of a completion report that does not show the self-check (``RESULT_INCOMPLETE``)."""
    return ("Your report does not show the self-check, or shows a red one without a deviation that names the failure: "
            + ", ".join(f"`{command}`" for command in commands)
            + ". Run each of them on your final tree, fix what goes red inside the scope, and report again with "
              "`self_check` filled. A failure you cannot fix inside the scope is a deviation with the failing test and its "
              "error, not a silent omission.")


def _self_check_again(commands) -> str:
    """The sentence of a correction round that asks for the self-check again."""
    return (" and run the self-check commands again (" + ", ".join(f"`{command}`" for command in commands) + ")"
            if commands else "")


DEVIATION_FIX = "Fix the deviation named in the section above: change only what its evidence names, inside the write set."


def fix_deviation(issues) -> str:
    """The "Fix this deviation" section: the deviations of the last round that the conductor lets the executor fix."""
    lines = []
    for issue in issues:
        lines.append(f"- {issue['text']}\n  Impact: {issue.get('impact', '-')}\n  Evidence: {', '.join(issue.get('evidence') or [])}")
    return ("# Fix this deviation\n\nYou reported the deviation(s) below as `auto_fixable`. Fix them now, inside the write "
            "set, without changing an acceptance check, a public interface or anything that needs a decision of the owner; "
            "the conductor then runs the acceptance checks again. If one cannot be fixed that way, leave it as it is and "
            "report it again.\n\n" + "\n".join(lines))


def _answers(answers) -> str:
    """The "Answers" section: what the owner (or the policy) answered to the questions of earlier rounds."""
    lines = []
    for row in answers:
        value = row["answer"] if isinstance(row["answer"], str) else json.dumps(row["answer"], ensure_ascii=False)
        lines.append(f"- {row['id']}: {row['text']}\n  Answer: {value} (by {row['by']})")
    return ("# Answers\n\nYou asked these questions in an earlier round; they are answered. Go on from the answers, keep "
            "your earlier work in the tree, and do not ask them again.\n\n" + "\n".join(lines))


def _correction(correction: str, targeted_tests: bool, self_check=()) -> str:
    """The correction block of a full prompt and of a resumed one. The text below is the only current assignment;
    product requirements and authority are not restated here because the task still holds them."""
    return ("## Correction\n\nYour previous attempt is in the working tree. The current correction focus below is the "
            "only assignment of this round. Earlier correction instructions are historical and are not a current "
            "assignment. The goal, the scope, the authority and the acceptance contract stay in force. Make exactly "
            "this correction, inside the same scope" + (" and re-run the tests of what you touched"
                                                         + _self_check_again(self_check) if targeted_tests
                       else ", then run the acceptance checks again")
            + (". Do not rerun acceptance checks the conductor owns." if targeted_tests else ".")
            + "\n\n" + _fence(correction, "text"))


ADOPTED = """\
A previous attempt at this piece of work is already in the working tree (these paths are changed: {paths}). Do not
start over: check it against the input, finish what is missing and fix what is wrong, inside the same scope."""


def interrupted_correction(base_head: Optional[str], paths: list) -> str:
    """The executor continues partial work left by an interrupted invocation."""
    head = "Your previous attempt was interrupted before it reported. "
    if not paths:
        since = f" since {base_head}" if base_head else ""
        return (head + f"The working tree shows no change{since}: start the work inside the same scope; check first "
                "whether a part of it is already done (committed or outside the tree).")
    since = f"since {base_head}" if base_head else "(the project is not a git checkout, so no base commit is known)"
    return (head + f"The working tree may hold its partial changes {since}: {', '.join(sorted(paths)[:200])}. "
            "Continue from them inside the same scope; do not redo finished parts.")


_FAILURE_HEADER = re.compile(
    r"^(?:FAIL(?:ED)?(?:[: \[]|$)|ERROR[: \[]|Traceback|AssertionError|\[fail\])", re.I)
_CHILD_LOG = re.compile(r"(?:full output:|child log:)\s*(\S+)")
_NO_DIFF_RULE = (
    "A correction that changes no product file is not accepted as done, and the conductor does not start "
    "acceptance again, unless this report records a legitimate no-diff cause with evidence: an environment fix "
    "(`open_issues` class `environment` or `test_env`, with `evidence`) or a confirmed nondeterministic failure "
    "(the issue text says nondeterministic and `evidence` names the proof). One such proof is accepted for the "
    "same red checks. A repeat with no product change is not fixed.")


def _failure_excerpt(log) -> str:
    """A bounded hint from the first failure header; its full path remains authoritative."""
    text, _children = _failure_report(log, headers=1, total=1600)
    return text


def _failure_report(log, *, headers: int = 40, total: int = 8000) -> tuple:
    """A bounded sample of failure headers (plus one following line) and child-log paths.
    The full log stays the authority; a tail does not replace these headers."""
    found, children = [], []
    try:
        with Path(log).open(encoding="utf-8", errors="replace") as stream:
            pending = None
            for _ in range(20000):
                line = stream.readline(2048)
                if not line:
                    break
                for match in _CHILD_LOG.finditer(line):
                    child = match.group(1).rstrip(".,);")
                    if child not in children:
                        children.append(child)
                if _FAILURE_HEADER.match(line):
                    if pending is not None:
                        found.append(pending)
                    pending = line.rstrip("\n")[:500]
                    if len(found) >= headers:
                        pending = None
                        break
                elif pending is not None:
                    extra = line.rstrip("\n")[:300]
                    if extra:
                        pending = pending + "\n" + extra
                    found.append(pending)
                    pending = None
                    if len(found) >= headers:
                        break
            if pending is not None and len(found) < headers:
                found.append(pending)
    except OSError:
        return "", []
    text = "\n".join(found)
    if len(text) > total:
        text = text[:total]
    return text, children[:20]


def _historical_causes(historical) -> str:
    if not historical:
        return ""
    lines = ["## Historical causes", "",
             "These causes were addressed in an earlier acceptance. They are not current work. Do not reopen them "
             "unless a current failure shows the same cause is still red.", ""]
    for row in historical:
        cmd = row.get("cmd") or row.get("procedure") or "-"
        lines.append(f"- {row.get('id', '-')} `{cmd}`: addressed; the latest completed non-skipped result was green.")
    return "\n".join(lines)


def check_correction(failed: list, *, historical=None, stage: str = "checks") -> str:
    """The current correction focus: latest red checks, every failure header, full and child logs.

    ``historical`` lists earlier red checks that a later acceptance showed green. They are marked historical
    and are not an assignment. Product requirements are not rewritten here."""
    lines = [
        "## Current correction focus",
        "",
        "This section is the only current correction. It comes from the latest acceptance. "
        "Product requirements, scope, authority and the acceptance contract are unchanged. "
        "Diagnose only the failures below. Review findings appended in this same round are current too. "
        "Follow the configured acceptance owner; diagnose with the exact new or failed cases named here.",
        "",
        _NO_DIFF_RULE,
        "",
        f"Stage `{stage}`. Status: red.",
        "",
        "These acceptance checks are red on your candidate:",
        "",
    ]
    for row in failed:
        lines.append(f"{row['id']}: `{row.get('cmd') or row.get('procedure')}` → "
                     f"{row.get('exit', row.get('verdict'))}")
        if row.get("log"):
            lines.append(f"Full check log: `{row['log']}`. Read the failing section; the tail may omit it.")
            excerpt, children = _failure_report(row["log"])
            if excerpt:
                lines.append("Failure headers (bounded sample: at most 40 headers, 20000 reads and 8000 characters; "
                             "the full log is authoritative and may contain further failures):\n" + excerpt)
            for child in children:
                lines.append(f"Child log: `{child}`")
        if row.get("tail"):
            lines.append(row["tail"])
    older = _historical_causes(historical or [])
    return "\n".join(lines) + ("\n\n" + older if older else "")


def review_correction(findings: dict, triage: dict) -> str:
    """Correction package of the confirmed findings: the finding, its reproduction and the fix to make."""
    by_id = {item["id"]: item for item in findings.get("findings", [])}
    lines = []
    for entry in triage.get("confirmed", []):
        finding = by_id.get(entry["finding"], {})
        repro = entry["reproduction"]
        lines.append(f"{entry['finding']} ({finding.get('severity', '-')}, {finding.get('location', '-')}): "
                     f"{finding.get('failure_scenario', '')}\n  reproduced: `{repro['cmd']}` → exit {repro['exit']}: "
                     f"{repro['observed']}\n  fix: {entry['fix']}")
    return "The review found these defects and the triage reproduced each one:\n\n" + "\n".join(lines)


def evidence(title: str, text: str, tag: str = "") -> str:
    """One piece of local evidence for the advisor: a titled, fenced block."""
    return f"## {title}\n\n" + _fence(text, tag)


def advice_text(advice: dict, option: dict, *, by: str) -> str:
    """The advice as the role that acts on it must read it: the chosen option, who chose it, and the reasons both ways.
    It is guidance for the work inside the write set; it widens no scope and changes no acceptance check."""
    lines = [f"Chosen way: {option['id']} — {option['text']} (chosen by {by}; the advisor's confidence is "
             f"{advice['confidence']})"]
    for title, key in (("For", "pros"), ("Against", "cons")):
        if option.get(key):
            lines.append(f"{title}: " + "; ".join(option[key]))
    if advice.get("sources"):
        lines.append("Sources: " + ", ".join(advice["sources"]))
    return "\n".join(lines)


def advice_correction(advice: dict, option: dict, *, by: str, problem: str) -> str:
    """Correction package of red checks the advisor advised on, to follow the chosen way."""
    return (problem.rstrip() + "\n\n# Advice\n\nThe correction allowance is spent; an advisor read the problem and one more "
            "correction round is made by this advice. It does not widen `scope.write_set` or change an acceptance check; "
            "if the way needs either, stop and report it.\n\n" + advice_text(advice, option, by=by))


def advice_for_triage(advice: dict, option: dict, *, by: str) -> str:
    """The "Advice" section of a repeated triage: the disagreement between the reviewer and the first triage, advised on."""
    return ("## Advice\n\nThe first triage rejected a Major or Blocker finding the reviewer raised. An advisor read both "
            "sides. Weigh it, reproduce again what it points at, and triage every finding again; the advice is a lead, "
            "not a verdict.\n\n" + advice_text(advice, option, by=by))
