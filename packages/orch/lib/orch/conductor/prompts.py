"""Prompts of the roles the conductor starts, and the closed result each one returns.

A prompt is the role text and the task block of ``render.render_prompt`` (the execution-input only: the role never
sees the plan or the plan command line), followed by the conductor frame: the scout context, the run rules, a
correction package, the candidate under review, and the result block the role must end with. Every role prints the
same progress lines as the conductor (``[orch] <UTC time> <item> <step> <what>``) before each major step.
"""
from __future__ import annotations

import json
import re

from orch import render

RESULT_KINDS = {"executor": "stage-report", "bounded-implementer": "stage-report", "reviewer": "review-findings",
                "triager": "triage-result"}
_BLOCK = re.compile(r"(?P<fence>`{3,})(?P<tag>[A-Za-z0-9_-]*)[ \t]*\n(?P<body>.*?)\n(?P=fence)[ \t]*(?:\n|$)", re.S)

_STAGE_REPORT = """\
End your answer with exactly one fenced block tagged `stage-report` holding one JSON object and nothing else:

```stage-report
{"status": "done | done_with_deviations | blocked",
 "summary": "what changed and why",
 "changed_paths": ["repository-relative path"],
 "checks_run": [{"id": "V1", "cmd": "the command as written", "exit": 0}],
 "evidence": ["repository-relative path of an output file"],
 "open_issues": [{"text": "…", "kind": "pending | deviation | blocker | difficulty | assumption | note | escalation", "impact": "…", "next": "…"}]}
```

`status` is `blocked` whenever the work needs something only the owner can give (a decision, a path outside
`scope.write_set`, credentials, an external resource) or an `escalation` condition occurs; then list each missing
thing as an `escalation` issue. Never guess past such a gap. `done_with_deviations` needs at least one `deviation`
issue. List in `checks_run` only checks that really ran; the conductor runs every acceptance check again itself.
"""

_REVIEW_FINDINGS = """\
End your answer with exactly one fenced block tagged `review-findings` holding one JSON object and nothing else:

```review-findings
{"verdict": "GREEN | ATTENTION | RED",
 "findings": [{"id": "F1", "severity": "Blocker | Major | Minor | Nit", "confidence": "high | medium | low",
               "location": "path:line", "failure_scenario": "concrete inputs or state and the wrong outcome",
               "basis": "correctness | security | performance | project rule | input contract",
               "reproduction": "command or steps that show it, when you ran any"}],
 "questions": ["an uncertainty, asked as a question"],
 "residual_risk": "material risk when there are no findings"}
```
"""

_TRIAGE_RESULT = """\
End your answer with exactly one fenced block tagged `triage-result` holding one JSON object and nothing else.
Every finding id of the round appears exactly once, in `confirmed` or in `rejected`:

```triage-result
{"confirmed": [{"finding": "F1", "reproduction": {"cmd": "…", "exit": 1, "observed": "…"},
                "fix": "what to change inside the scope and the regression check that proves it"}],
 "rejected": [{"finding": "F2", "reason": "why it does not hold", "reproduction": {"cmd": "…", "exit": 0, "observed": "…"}}]}
```
"""

_PROGRESS = """\
## Progress lines

Before each major step print one line to your output: `[orch] <UTC time> {item} {step} <what you start or finish>`.
"""


def json_block(text: str, tag: str):
    """``(document, error)``: the JSON object of the last fenced block tagged ``tag`` (else the last ``json`` block)."""
    blocks = list(_BLOCK.finditer(text or ""))
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


def _fence(text: str, tag: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    mark = "`" * max(3, longest + 1)
    return f"{mark}{tag}\n{text.rstrip()}\n{mark}"


def _head(role: str, input_doc: dict, roles_dir, skills: list) -> str:
    manifest, text = render.load_role(role, roles_dir)
    prompt = render.render_prompt(input_doc, manifest, text)
    if skills:
        prompt += "\n\n## Skills\n\nLoad and apply these skills: " + ", ".join(f"`{name}`" for name in skills) + ".\n"
    return prompt


def scout(input_doc: dict, *, item: str, step: str, roles_dir=None, skills=()) -> str:
    return _head("context-scout", input_doc, roles_dir, list(skills)) + "\n" + _PROGRESS.format(item=item, step=step)


def executor(input_doc: dict, *, item: str, step: str, scout_text: str = "", rules=(), correction: str = "",
             role: str = "executor", roles_dir=None, skills=()) -> str:
    parts = [_head(role, input_doc, roles_dir, list(skills))]
    if scout_text:
        parts.append("## Context map\n\nA read-only scout mapped the context; treat its lines as leads, not facts.\n\n"
                     + _fence(scout_text, "text"))
    if rules:
        parts.append("## Run rules\n\n" + "\n".join(f"- {rule}" for rule in rules))
    if correction:
        parts.append("## Correction\n\nYour previous attempt is in the working tree. Make exactly this correction, "
                     "inside the same scope, then run the acceptance checks again.\n\n" + _fence(correction, "text"))
    parts.append(_PROGRESS.format(item=item, step=step))
    parts.append("## Result\n\n" + _STAGE_REPORT)
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


def reviewer(input_doc: dict, *, item: str, step: str, base: str, diff: str, checks: list, round_no: int,
             roles_dir=None, skills=()) -> str:
    summary = "\n".join(f"- {row['id']}: {row.get('verdict') or row.get('exit')}" for row in checks) or "- none"
    parts = [_head("reviewer", input_doc, roles_dir, list(skills)),
             f"## Candidate (review round {round_no})\n\nBase revision `{base}`; the candidate is the working tree "
             "(uncommitted changes, untracked files included). Read files as you need; do not change anything.",
             "Acceptance checks run by the conductor on this candidate:\n\n" + summary,
             "Diff against the base:\n\n" + _fence(diff or "(no tracked changes; see the untracked files)", "diff"),
             _PROGRESS.format(item=item, step=step),
             "## Result\n\n" + _REVIEW_FINDINGS]
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


def triager(input_doc: dict, *, item: str, step: str, base: str, findings: dict, roles_dir=None, skills=()) -> str:
    parts = [_head("triager", input_doc, roles_dir, list(skills)),
             f"## Candidate\n\nBase revision `{base}`; the candidate is the working tree. Scratch files go to a "
             "temporary directory outside the repository.",
             "## Review findings\n\n" + _fence(json.dumps(findings, ensure_ascii=False, indent=2), "json"),
             _PROGRESS.format(item=item, step=step),
             "## Result\n\n" + _TRIAGE_RESULT]
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


def closer(*, item: str, step: str, command: str) -> str:
    """The closing prompt: the registrar records the result with one command the conductor built, nothing else."""
    parts = [
        "# Closing: record the result of " + item,
        "You are the registrar of a conductor run. The work, its checks and its review are finished and closed; you "
        "only record the result in the work source. You never judge, repair or extend the work, never change a file "
        "and never commit.",
        "## Do exactly this\n\nRun this command once with Bash. Copy it character for character: change no argument, "
        "add none, and run nothing else (every other command is denied).\n\n" + _fence(command, "sh"),
        _PROGRESS.format(item=item, step=step),
        "## Result\n\nAnswer with the standard output of the command in one fenced `json` block, then one last line: "
        "`RECORDED` when the command exited 0, else `REFUSED: <the CODE: message line of its standard error>`. If it "
        "failed, do not run it again and do not look for another way.",
    ]
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


def check_correction(failed: list) -> str:
    """Correction package of red acceptance checks: each command, its exit and the tail of its output."""
    lines = []
    for row in failed:
        lines.append(f"{row['id']}: `{row.get('cmd') or row.get('procedure')}` → "
                     f"{row.get('exit', row.get('verdict'))}")
        if row.get("tail"):
            lines.append(row["tail"])
    return "These acceptance checks are red on your candidate:\n\n" + "\n".join(lines)


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
