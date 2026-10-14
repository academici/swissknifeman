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
_BLOCK = re.compile(r"(?P<fence>`{3,})(?:json[ \t]+(?=[A-Za-z0-9_-]))?(?P<tag>[A-Za-z0-9_-]*)[ \t]*\n(?P<body>.*?)\n(?P=fence)[ \t]*(?:\n|$)", re.S)

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

A `deviation` issue also carries `class` (`write_set | spec_mismatch | test_env | docs | dependency | environment | other`),
`impact` and `outcome` (`accepted | follow_up | owner_decision`); any issue may add `severity` (`low | medium | high |
critical`), `auto_fixable` (boolean) and `evidence` (a list of `path:line` or `V<n>`).

`status` is `blocked` whenever the work needs something only the owner can give (a decision, a path outside
`scope.write_set`, credentials, an external resource) or an `escalation` condition occurs; then list each missing
thing as an `escalation` issue. Never guess past such a gap. `done_with_deviations` needs at least one `deviation`
issue. Every `checks_run` entry has exactly the keys shown (`id`, `cmd`, `exit`) or, for a manual procedure,
`id`, `procedure`, `verdict` (`pass | fail`); no other keys, no entry for a check that did not run, put notes in
`open_issues`. List in `checks_run` only checks that really ran; the conductor runs every acceptance check again itself.
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


def write_set_block(text: str):
    """``(document, error, shown)``: the JSON object of the last fenced ``write-set`` block of a scout answer (the
    ``json write-set`` form is the same block), and the answer without its ``write-set`` blocks. No fallback to
    another ``json`` block: a hint is only what the scout tagged as one."""
    found = [match for match in _BLOCK.finditer(text or "") if match["tag"] == "write-set"]
    if not found:
        return None, "no fenced `write-set` block in the answer", text
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


def _expected(expected: dict) -> str:
    """The "Expected paths" section: the scout's hint, never a widening of the write set."""
    def lines(rows):
        return "\n".join(f"- `{row}`" for row in rows[:50]) + (f"\n- … {len(rows) - 50} more" if len(rows) > 50 else "")
    parts = ["## Expected paths\n\nThe read-only scout expects the change to touch these. It is a hint: it does not widen "
             "`scope.write_set`, and a path outside the write set stays a deviation."]
    if expected.get("paths"):
        parts.append("Paths:\n" + lines(expected["paths"]))
    if expected.get("tests"):
        parts.append("Tests:\n" + lines(expected["tests"]))
    return "\n\n".join(parts)


def _fence(text: str, tag: str = "") -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    mark = "`" * max(3, longest + 1)
    return f"{mark}{tag}\n{text.rstrip()}\n{mark}"


def _head(role: str, input_doc: dict, roles_dir, skills: list, rules: str = "", skill_texts=None) -> str:
    """Role text and task block, then the repository rules an isolated role still needs and its skills: by name when
    the provider loads skills itself, as text when the role runs isolated (its provider loads none)."""
    manifest, text = render.load_role(role, roles_dir)
    prompt = render.render_prompt(input_doc, manifest, text)
    if rules:
        rules = re.sub(r"\s*<!--.*?-->", "", rules, flags=re.S)  # instruction markers are for generators, not for roles
        prompt += "\n\n## Repository rules\n\n" + rules.rstrip() + "\n"
    texts = dict(skill_texts or {})
    named = [name for name in skills if name not in texts]
    if named:
        prompt += "\n\n## Skills\n\nLoad and apply these skills: " + ", ".join(f"`{name}`" for name in named) + ".\n"
    for name, body in texts.items():
        prompt += f"\n\n## Skill `{name}`\n\n" + body.rstrip() + "\n"
    return prompt


def scout(input_doc: dict, *, item: str, step: str, roles_dir=None, skills=(), skill_texts=None) -> str:
    return _head("context-scout", input_doc, roles_dir, list(skills), skill_texts=skill_texts) + "\n" \
        + _PROGRESS.format(item=item, step=step)


_RUN_CHECKS = """\
## Verification

Run every acceptance check of the input yourself, exactly as written, before you report, and list each in
`checks_run` under its id. The conductor runs them again after your report.
"""


def _conductor_commands(input_doc: dict) -> str:
    """The acceptance commands the conductor itself runs after the report: the executor must not run them (or whole
    suites that contain them); a full run of them by the executor measured 30–50% of its step."""
    commands = [str(check.get("cmd")).strip().splitlines()[0][:200]
                for check in (input_doc.get("acceptance") or {}).get("checks", []) if check.get("cmd")]
    if not commands:
        return ""
    return ("\nThe conductor runs these commands itself right after your report; do not run them, nor the whole suites "
            "they start (run single test files of what you changed instead):\n"
            + "\n".join(f"- `{command}`" for command in commands) + "\n")


def executor(input_doc: dict, *, item: str, step: str, scout_text: str = "", rules=(), correction: str = "",
             role: str = "executor", roles_dir=None, skills=(), targeted_tests: bool = True, repo_rules: str = "",
             skill_texts=None, expected=None) -> str:
    parts = [_head(role, input_doc, roles_dir, list(skills), repo_rules, skill_texts)]
    if scout_text:
        parts.append("## Context map\n\nA read-only scout mapped the context; treat its lines as leads, not facts.\n\n"
                     + _fence(scout_text, "text"))
    if expected and (expected.get("paths") or expected.get("tests")):
        parts.append(_expected(expected))
    if targeted_tests:
        commands = _conductor_commands(input_doc)
        if commands:
            parts.append("## Verification\n" + commands)
    else:
        parts.append(_RUN_CHECKS)
    if rules:
        parts.append("## Run rules\n\n" + "\n".join(f"- {rule}" for rule in rules))
    if correction:
        parts.append("## Correction\n\nYour previous attempt is in the working tree. Make exactly this correction, "
                     "inside the same scope" + (" and re-run the tests of what you touched" if targeted_tests
                                                    else ", then run the acceptance checks again") + ".\n\n" + _fence(correction, "text"))
    parts.append(_PROGRESS.format(item=item, step=step))
    parts.append("## Result\n\n" + _STAGE_REPORT)
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


_PRE_FINAL = """\
## Pre-final audit

The defects of an earlier review round were corrected in this candidate. This audit only confirms that nothing
important is left: report findings of severity {floor} or higher only (severities, most severe first: Blocker, Major,
Minor, Nit; a Major defect breaks an acceptance check, the contract of the input, or other code). Do not look for
lower findings and do not report them. If there is no such finding, the verdict is GREEN.
"""


def _corrected_scope(corrected) -> str:
    lines = [f"- {item.get('id')} ({item.get('severity', '-')}, {item.get('location', '-')}): "
             f"{item.get('failure_scenario', '')[:300]} — correction asked: {item.get('fix', '')[:300]}" for item in corrected]
    return ("## Scope of this round\n\nThe whole change was reviewed in the previous round. Do not audit it again. Check, in this "
            "order: (1) each defect below is really fixed (read the files at the given locations); (2) the correction "
            "introduced no new defect of the severity floor in the lines it touched.\n\n" + "\n".join(lines))


def reviewer(input_doc: dict, *, item: str, step: str, base: str, diff: str, checks: list, round_no: int,
             roles_dir=None, skills=(), pre_final: bool = False, min_severity: str = "Major",
             checks_pending: bool = False, corrected=(), outside=(), repo_rules: str = "", skill_texts=None) -> str:
    summary = "\n".join(f"- {row['id']}: {row.get('verdict') or row.get('exit')}" for row in checks) or "- none"
    parts = [_head("reviewer", input_doc, roles_dir, list(skills), repo_rules, skill_texts),
             f"## Candidate (review round {round_no})\n\nBase revision `{base}`; the candidate is the working tree "
             "(uncommitted changes, untracked files included). Read files as you need; do not change anything.",
             *([_PRE_FINAL.format(floor=min_severity)] if pre_final else []),
             *([_corrected_scope(corrected)] if corrected else []),
             *([_outside_scope(outside)] if outside else []),
             ("Acceptance checks run by the conductor on this candidate:\n\n" + summary) if not checks_pending else
             "The conductor runs the acceptance checks on this candidate at the same time; their result is not known yet "
             "and is not your concern: review the candidate itself.",
             "Diff against the base:\n\n" + _fence(diff or "(no tracked changes; see the untracked files)", "diff"),
             _PROGRESS.format(item=item, step=step),
             "## Result\n\n" + _REVIEW_FINDINGS]
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


def _outside_scope(outside) -> str:
    return ("## Changed outside the write set\n\nThe executor changed these paths, which `scope.write_set` does not own. "
            "Judge whether each change is needed by the goal; an unneeded or harmful one is a finding (basis: input "
            "contract):\n\n" + "\n".join(f"- `{path}`" for path in outside))


def triager(input_doc: dict, *, item: str, step: str, base: str, findings: dict, roles_dir=None, skills=(),
            repo_rules: str = "", skill_texts=None) -> str:
    parts = [_head("triager", input_doc, roles_dir, list(skills), repo_rules, skill_texts),
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


CONTRACT_TEXT = {"stage-report": _STAGE_REPORT, "review-findings": _REVIEW_FINDINGS, "triage-result": _TRIAGE_RESULT}


def report_fixer(*, kind: str, problem: str, answer: str, item: str, step: str, limit: int = 40_000) -> str:
    """The repair prompt: rewrite only the closed block of a role's answer so that it fits the contract."""
    shown = answer if len(answer) <= limit else "[… the start of the answer is cut …]\n" + answer[-limit:]
    parts = [
        f"# Repair: the `{kind}` block of {item} {step}",
        "A role finished its work and ended its answer with a result block that does not fit the contract. You do not "
        "redo, judge or extend the work, read no file and run nothing. You rewrite that one block from the facts the "
        "answer states.",
        "## Rules\n\n- Keep every fact of the answer: statuses, paths, check ids and exits, verdicts, findings, reasons.\n"
        "- Never invent a check, an exit, a verdict, a path, a finding or a reproduction the answer does not give; when "
        "a required fact is missing, use the closest honest statement of the answer (for example an issue that says "
        "what is missing).\n- Never raise a status: a blocked answer stays blocked.\n"
        "- Change only what the problem below names, plus what the contract needs for the block to be valid.",
        "## The problem\n\n" + _fence(problem, "text"),
        "## The contract\n\n" + CONTRACT_TEXT[kind],
        "## The answer\n\n" + _fence(shown, "text"),
        "## Result\n\nAnswer with exactly one fenced block tagged `" + kind + "` holding the corrected JSON object, and "
        "nothing else.",
    ]
    return "\n\n".join(part.rstrip() for part in parts) + "\n"


ADOPTED = """\
A previous attempt at this piece of work is already in the working tree (these paths are changed: {paths}). Do not
start over: check it against the input, finish what is missing and fix what is wrong, inside the same scope."""


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
