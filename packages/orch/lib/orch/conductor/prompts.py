"""Prompts of the roles the conductor starts, and the closed result each one returns.

A prompt is the role text and the task block of ``render.render_prompt`` (the execution-input only: the role never
sees the plan or the plan command line), followed by the conductor frame: the scout context, the run rules, a
correction package, the candidate under review, and the result block the role must end with. Every role prints the
same progress lines as the conductor (``[orch] <UTC time> <item> <step> <what>``) before each major step.

Every builder returns the prompt as a list of ``Block(kind, origin, text)``; ``render`` joins them into the prompt byte for
byte (a separator belongs to the block it follows), and ``manifest`` says what each block is and where it came from.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
from typing import Optional

from aicore.content.budget import estimate_tokens
from aicore.util.digest import sha256_hex

from orch import render as role_render

KINDS = ("role_text", "input", "repository_rules", "skill", "skill_names", "context_map", "verification", "run_rules",
         "correction", "answers", "progress", "result_contract", "expected_paths", "candidate", "review_scope", "diff",
         "findings", "instruction")
CONDUCTOR = "conductor"

# Budget classes of the blocks (knowledge/p9-prompt#budgets). Only the measure and a beacon: nothing is cut. The kinds the
# design does not list belong to the frame or the task material of their role (progress, candidate, review_scope, diff,
# findings, instruction), so they count as core; ``retrieval`` has no block yet.
BUDGET_CLASSES = {
    "core": ("role_text", "input", "verification", "result_contract", "answers", "correction", "progress", "candidate",
             "review_scope", "diff", "findings", "instruction"),
    "supporting": ("repository_rules", "skill", "skill_names", "context_map", "expected_paths", "focus", "run_rules"),
    "retrieval": (),
}
BUDGET_LIMITS = {"core": "prompt_core_tokens", "supporting": "prompt_supporting_tokens",
                 "retrieval": "prompt_retrieval_tokens"}  # the ``limits`` keys of the run options

RESULT_KINDS = {"executor": "stage-report", "bounded-implementer": "stage-report", "reviewer": "review-findings",
                "triager": "triage-result", "researcher": "research-result"}
_FENCE_BLOCK = re.compile(r"(?P<fence>`{3,})(?:json[ \t]+(?=[A-Za-z0-9_-]))?(?P<tag>[A-Za-z0-9_-]*)[ \t]*\n(?P<body>.*?)\n(?P=fence)[ \t]*(?:\n|$)", re.S)

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

Ask a question only when the work cannot go on without a decision, an approval or a credential that only the owner can
give, and the input does not answer it. Put it in `questions`: `[{"id": "Q1", "revision": 1, "kind": "clarification |
decision | approval | credential", "text": "…", "options": [{"id": "a", "label": "…"}], "default": "…", "blocking":
true, "risk": "low | medium | high"}]`. A blocking question needs `status` `blocked` (and an `escalation` issue); a
question with `"blocking": false` names what you `assumed` and you go on with it. `default` is only your proposal.

Optionally give your own advice on a review of the piece in `review_recommendation`: `{"recommended": true, "reason_codes":
["scope_expanded | public_api_changed | schema_changed | shared_module_changed | security_touched | low_confidence |
other"], "focus": ["what a reviewer should look at first"], "suggested_model_class": "economy | implementation |
frontier"}`. It is advice only: the conductor decides about a review itself; omit it when you have no basis for it.

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

_RESEARCH_RESULT = """\
End your answer with exactly one fenced block tagged `research-result` holding one JSON object and nothing else.
A claim without a source is not a claim: it goes to `unknowns`:

```research-result
{"query": "the question as asked",
 "claims": [{"text": "a statement a source supports", "sources": ["https://… or repository/path"]}],
 "contradictions": ["source A says …, source B says …"],
 "unknowns": ["what no source answered"],
 "sources_used": ["id of a source you asked"]}
```
"""

_PROGRESS = """\
## Progress lines

Before each major step print one line to your output: `[orch] <UTC time> {item} {step} <what you start or finish>`.
"""


@dataclass(frozen=True)
class Block:
    """A part of a prompt: what it is (``kind``), where it came from (``origin``: a role file, ``input.json``,
    ``skill:<id>``, ``scout-cache:<rel>``, ``conductor``), its exact text with the separator that follows it, and ``id``
    for a block that stands for one named thing (a skill)."""
    kind: str
    origin: str
    text: str
    id: Optional[str] = None


def render(blocks) -> str:
    """The prompt: the texts of the blocks one after the other."""
    return "".join(block.text for block in blocks)


def _join(groups: list) -> list:
    """The blocks of the parts of a prompt: parts are separated by a blank line and the prompt ends with one newline;
    each separator is part of the last block it follows."""
    blocks = []
    for number, group in enumerate(groups):
        group = list(group)
        group[-1] = replace(group[-1], text=group[-1].text.rstrip() + ("\n" if number == len(groups) - 1 else "\n\n"))
        blocks += group
    return blocks


def _then(blocks: list, block: Block) -> None:
    """``block`` after the last of ``blocks``, a blank line between them."""
    blocks[-1] = replace(blocks[-1], text=blocks[-1].text + "\n\n")
    blocks.append(block)


def budget_class(kind: str) -> str:
    """``core``, ``supporting`` or ``retrieval``: the budget class of a block kind (a kind nobody listed is supporting)."""
    return next((name for name, kinds in BUDGET_CLASSES.items() if kind in kinds), "supporting")


def budgets(blocks, limits: dict) -> dict:
    """``{class: {tokens, limit}}``: the estimated tokens of the blocks of each class against ``limits[class]``."""
    tokens = {name: 0 for name in BUDGET_CLASSES}
    for block in blocks:
        tokens[budget_class(block.kind)] += estimate_tokens(block.text)
    return {name: {"tokens": tokens[name], "limit": int(limits.get(name) or 0)} for name in BUDGET_CLASSES}


def over_budget(blocks, limits: dict) -> list:
    """``[(class, block, class_tokens, limit)]`` for each class above its limit (0 is no limit), with the heaviest block of
    the class, the first of equals. A report only: the blocks are not touched."""
    found = []
    for name, row in budgets(blocks, limits).items():
        if row["limit"] and row["tokens"] > row["limit"]:
            members = [block for block in blocks if budget_class(block.kind) == name]
            found.append((name, max(members, key=lambda block: estimate_tokens(block.text)), row["tokens"], row["limit"]))
    return found


def manifest(blocks, *, step: str, role: str, route: dict, excluded=(), limits=None) -> dict:
    """The ``prompt-manifest/v1`` document of a prompt: its blocks (kind, origin, digest, estimated tokens), what was left
    out and why, the digest and size of the whole prompt, and, when ``limits`` (``{class: tokens}``) is given, the tokens
    of each budget class against its limit."""
    text = render(blocks)
    rows = []
    for block in blocks:
        row = {"kind": block.kind, "origin": block.origin, "sha256": sha256_hex(block.text.encode("utf-8")),
               "tokens": estimate_tokens(block.text)}
        if block.id:
            row["id"] = block.id
        rows.append(row)
    doc = {"schema": "prompt-manifest/v1", "step": step, "role": role,
           "route": {key: route[key] for key in ("provider", "model", "effort") if route.get(key)},
           "blocks": rows, "excluded": [dict(row) for row in excluded], "estimated_tokens": estimate_tokens(text),
           "prompt_sha256": sha256_hex(text.encode("utf-8"))}
    if limits is not None:
        doc["budgets"] = budgets(blocks, limits)
    return doc


def top_blocks(doc: dict, limit: int = 5) -> list:
    """The ``limit`` blocks of a manifest with the most tokens, the first of equals first."""
    return sorted(doc.get("blocks", []), key=lambda row: -row["tokens"])[:limit]


def explain_table(doc: dict) -> str:
    """The manifest as a table: kind, origin, tokens and the start of the digest of each block, then what was excluded."""
    route = "/".join(doc.get("route", {}).get(key, "") for key in ("provider", "model", "effort")
                     if doc.get("route", {}).get(key))
    lines = [f"{doc['step']} ({doc['role']}{', ' + route if route else ''}): {len(doc['blocks'])} block(s), "
             f"{doc['estimated_tokens']} estimated tokens, prompt sha256 {doc['prompt_sha256'][:12]}", "",
             "kind | origin | tokens | sha256"]
    for row in doc["blocks"]:
        name = row["kind"] + (f" {row['id']}" if row.get("id") else "")
        lines.append(f"{name} | {row['origin']} | {row['tokens']} | {row['sha256'][:12]}")
    if doc.get("excluded"):
        lines += ["", "excluded:"] + [f"- {row['id']}: {row['reason']}" for row in doc["excluded"]]
    return "\n".join(lines)


INTERACTIVE_TOOL = "AskUserQuestion"  # a skill that needs it waits for a person; every conductor role runs headless
EXCLUSIVE_GROUP_MAX = 1
EXCLUSIVE_GROUP_LIMITS = {"php-architecture": 2}  # every other exclusive group allows one


def _is_role_contract(target: str) -> bool:
    """Whether a ``selection.replaced_by`` points at a role contract or a schema (a script or a hook does not replace the
    text a role reads)."""
    parts = re.split(r"[\\/]", target)
    return "roles" in parts[:-1] or "schemas" in parts[:-1] or target.endswith(".schema.json")


def _conflicts_with(skill: dict, other: dict) -> bool:
    """Whether ``skill`` lists ``other`` in its ``conflicts``: by id, by name, or, for a skill of the project that has no
    bucket in its id, by the folder of a ``<bucket>/<folder>`` entry."""
    return any(target in (other["id"], other["name"]) or ("/" not in other["id"] and target.rsplit("/", 1)[-1] == other["name"])
               for target in skill["selection"].get("conflicts") or [])


def check_skills(skills: list, *, tools: Optional[set], budget: int = 0) -> tuple:
    """``(kept, excluded, conflict)`` of the skills of a role, from what they declare and nothing in their text.

    ``skills`` are ``{name, id, selection, tokens}`` in the order of the role's list (``selection`` is the content of
    ``selection.json`` or ``{}``; ``tokens`` is the size of the text that enters the prompt, or None when none does).
    ``tools`` are the tools of the route (None when it names none, so ``requires_tools`` is not judged). A skill is
    left out as ``duplicated_by_role_contract``, ``interactive_in_headless``, ``tool_missing``, ``over_budget`` (the text
    is above its ``max_tokens`` or above ``budget`` when that is not 0; never cut), ``persona_duplicate`` (a second
    ``persona``) or ``exclusive_group`` (beyond the limit of its group). ``conflict`` is the first pair of kept skills
    one of which lists the other in ``conflicts``, else None. ``excluded`` rows are ``{id, reason, detail}``."""
    kept, excluded, groups = [], [], {}

    def drop(skill, reason, detail=""):
        excluded.append({"id": skill["id"], "reason": reason, "detail": detail})

    for skill in skills:
        meta = skill["selection"]
        required = list(meta.get("requires_tools") or [])
        missing = sorted(set(required) - tools) if tools is not None else []
        tokens = skill.get("tokens")
        group = meta.get("exclusive_group")
        if meta.get("replaced_by") and _is_role_contract(meta["replaced_by"]):
            drop(skill, "duplicated_by_role_contract", meta["replaced_by"])
        elif INTERACTIVE_TOOL in required:
            drop(skill, "interactive_in_headless", INTERACTIVE_TOOL)
        elif missing:
            drop(skill, "tool_missing", ", ".join(missing))
        elif tokens is not None and meta.get("max_tokens") and tokens > meta["max_tokens"]:
            drop(skill, "over_budget", f"{tokens} tokens, max_tokens {meta['max_tokens']}")
        elif tokens is not None and budget and tokens > budget:
            drop(skill, "over_budget", f"{tokens} tokens, limits.skill_tokens_max {budget}")
        elif meta.get("kind") == "persona" and any(row["selection"].get("kind") == "persona" for row in kept):
            drop(skill, "persona_duplicate", "persona")
        elif group and groups.get(group, 0) >= EXCLUSIVE_GROUP_LIMITS.get(group, EXCLUSIVE_GROUP_MAX):
            drop(skill, "exclusive_group", group)
        else:
            kept.append(skill)
            if group:
                groups[group] = groups.get(group, 0) + 1
    conflict = next(((first, second) for number, first in enumerate(kept) for second in kept[number + 1:]
                     if _conflicts_with(first, second) or _conflicts_with(second, first)), None)
    return kept, excluded, conflict


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


def write_set_block(text: str):
    """``(document, error, shown)``: the JSON object of the last fenced ``write-set`` block of a scout answer (the
    ``json write-set`` form is the same block), and the answer without its ``write-set`` blocks. No fallback to
    another ``json`` block: a hint is only what the scout tagged as one."""
    found = [match for match in _FENCE_BLOCK.finditer(text or "") if match["tag"] == "write-set"]
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


def _head(role: str, input_doc: dict, roles_dir, skills: list, rules: str = "", skill_texts=None) -> list:
    """Blocks of the role text and task block, then the repository rules an isolated role still needs and its skills: by
    name when the provider loads skills itself, as text when the role runs isolated (its provider loads none)."""
    manifest, text = role_render.load_role(role, roles_dir)
    prompt = role_render.render_prompt(input_doc, manifest, text)
    task = role_render.render_task_block(input_doc)
    origin = ",".join(str(entry.get("path")) for entry in manifest.get("instructions") or []) or role
    if prompt.endswith(task):
        blocks = [Block("role_text", origin, prompt[:len(prompt) - len(task)]), Block("input", "input.json", task)]
    else:  # a renderer that does not end with the task block: one block, nothing is guessed
        blocks = [Block("role_text", origin, prompt)]
    if rules:
        rules = re.sub(r"\s*<!--.*?-->", "", rules, flags=re.S)  # instruction markers are for generators, not for roles
        _then(blocks, Block("repository_rules", "CLAUDE.md|AGENTS.md", "## Repository rules\n\n" + rules.rstrip() + "\n"))
    texts = dict(skill_texts or {})
    named = [name for name in skills if name not in texts]
    if named:
        _then(blocks, Block("skill_names", CONDUCTOR, "## Skills\n\nLoad and apply these skills: "
                            + ", ".join(f"`{name}`" for name in named) + ".\n"))
    for name, body in texts.items():
        _then(blocks, Block("skill", f"skill:{name}", f"## Skill `{name}`\n\n" + body.rstrip() + "\n", id=name))
    return blocks


def _progress(item: str, step: str) -> Block:
    return Block("progress", CONDUCTOR, _PROGRESS.format(item=item, step=step))


def scout(input_doc: dict, *, item: str, step: str, roles_dir=None, skills=(), skill_texts=None) -> list:
    blocks = _head("context-scout", input_doc, roles_dir, list(skills), skill_texts=skill_texts)
    blocks[-1] = replace(blocks[-1], text=blocks[-1].text + "\n")
    return blocks + [_progress(item, step)]


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


def executor(input_doc: dict, *, item: str, step: str, scout_text: str = "", rules=(), correction: str = "",
             role: str = "executor", roles_dir=None, skills=(), targeted_tests: bool = True, repo_rules: str = "",
             skill_texts=None, expected=None, answers=(), fix: str = "", scout_origin: str = "", batch: str = "") -> list:
    scout_from = f"scout-cache:{scout_origin}" if scout_origin else "scout-cache"
    parts = [_head(role, input_doc, roles_dir, list(skills), repo_rules, skill_texts)]
    if batch:
        parts.append([Block("run_rules", CONDUCTOR, batch)])
    if scout_text:
        parts.append([Block("context_map", scout_from, "## Context map\n\nA read-only scout mapped the context; treat its "
                            "lines as leads, not facts.\n\n" + _fence(scout_text, "text"))])
    if expected and (expected.get("paths") or expected.get("tests")):
        parts.append([Block("expected_paths", scout_from, _expected(expected))])
    if targeted_tests:
        commands = _conductor_commands(input_doc)
        if commands:
            parts.append([Block("verification", CONDUCTOR, "## Verification\n" + commands)])
    else:
        parts.append([Block("verification", CONDUCTOR, _RUN_CHECKS)])
    if rules:
        parts.append([Block("run_rules", CONDUCTOR, "## Run rules\n\n" + "\n".join(f"- {rule}" for rule in rules))])
    if answers:
        parts.append([Block("answers", "questions.json", _answers(answers))])
    if fix:
        parts.append([Block("correction", CONDUCTOR, fix)])
    if correction:
        parts.append([Block("correction", CONDUCTOR, "## Correction\n\nYour previous attempt is in the working tree. Make "
                            "exactly this correction, inside the same scope"
                            + (" and re-run the tests of what you touched" if targeted_tests
                               else ", then run the acceptance checks again") + ".\n\n" + _fence(correction, "text"))])
    parts.append([_progress(item, step)])
    parts.append([Block("result_contract", CONDUCTOR, "## Result\n\n" + _STAGE_REPORT)])
    return _join(parts)


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
             checks_pending: bool = False, corrected=(), outside=(), repo_rules: str = "", skill_texts=None,
             focus=(), focus_origin: str = "stage-report") -> list:
    summary = "\n".join(f"- {row['id']}: {row.get('verdict') or row.get('exit')}" for row in checks) or "- none"
    parts = [_head("reviewer", input_doc, roles_dir, list(skills), repo_rules, skill_texts),
             [Block("candidate", CONDUCTOR, f"## Candidate (review round {round_no})\n\nBase revision `{base}`; the "
                    "candidate is the working tree (uncommitted changes, untracked files included). Read files as you "
                    "need; do not change anything.")],
             *([[Block("focus", focus_origin, _focus(focus))]] if focus else []),
             *([[Block("review_scope", CONDUCTOR, _PRE_FINAL.format(floor=min_severity))]] if pre_final else []),
             *([[Block("review_scope", CONDUCTOR, _corrected_scope(corrected))]] if corrected else []),
             *([[Block("review_scope", CONDUCTOR, _outside_scope(outside))]] if outside else []),
             [Block("verification", CONDUCTOR, ("Acceptance checks run by the conductor on this candidate:\n\n" + summary)
                    if not checks_pending else
                    "The conductor runs the acceptance checks on this candidate at the same time; their result is not "
                    "known yet and is not your concern: review the candidate itself.")],
             [Block("diff", CONDUCTOR, "Diff against the base:\n\n"
                    + _fence(diff or "(no tracked changes; see the untracked files)", "diff"))],
             [_progress(item, step)],
             [Block("result_contract", CONDUCTOR, "## Result\n\n" + _REVIEW_FINDINGS)]]
    return _join(parts)


def _focus(lines) -> str:
    """The "Focus" section: where to look first (the advice of the executor, the features of the risk score); the
    review keeps its whole scope."""
    return ("## Focus\n\nLook at these points first: the executor advised them or the risk score of the conductor found "
            "them. They do not reduce the review: judge the whole change as usual.\n\n"
            + "\n".join(f"- {line}" for line in lines))


def _outside_scope(outside) -> str:
    return ("## Changed outside the write set\n\nThe executor changed these paths, which `scope.write_set` does not own. "
            "Judge whether each change is needed by the goal; an unneeded or harmful one is a finding (basis: input "
            "contract):\n\n" + "\n".join(f"- `{path}`" for path in outside))


def triager(input_doc: dict, *, item: str, step: str, base: str, findings: dict, roles_dir=None, skills=(),
            repo_rules: str = "", skill_texts=None) -> list:
    parts = [_head("triager", input_doc, roles_dir, list(skills), repo_rules, skill_texts),
             [Block("candidate", CONDUCTOR, f"## Candidate\n\nBase revision `{base}`; the candidate is the working tree. "
                    "Scratch files go to a temporary directory outside the repository.")],
             [Block("findings", "review-findings", "## Review findings\n\n"
                    + _fence(json.dumps(findings, ensure_ascii=False, indent=2), "json"))],
             [_progress(item, step)],
             [Block("result_contract", CONDUCTOR, "## Result\n\n" + _TRIAGE_RESULT)]]
    return _join(parts)


def closer(*, item: str, step: str, command: str) -> list:
    """The closing prompt: the registrar records the result with one command the conductor built, nothing else."""
    parts = [
        [Block("instruction", CONDUCTOR, "# Closing: record the result of " + item)],
        [Block("instruction", CONDUCTOR,
               "You are the registrar of a conductor run. The work, its checks and its review are finished and closed; you "
               "only record the result in the work source. You never judge, repair or extend the work, never change a file "
               "and never commit.")],
        [Block("instruction", CONDUCTOR,
               "## Do exactly this\n\nRun this command once with Bash. Copy it character for character: change no "
               "argument, add none, and run nothing else (every other command is denied).\n\n" + _fence(command, "sh"))],
        [_progress(item, step)],
        [Block("result_contract", CONDUCTOR,
               "## Result\n\nAnswer with the standard output of the command in one fenced `json` block, then one last "
               "line: `RECORDED` when the command exited 0, else `REFUSED: <the CODE: message line of its standard "
               "error>`. If it failed, do not run it again and do not look for another way.")],
    ]
    return _join(parts)


def researcher(input_doc: dict, *, item: str, step: str, query: str, sources: list, command: str, roles_dir=None,
               skills=(), repo_rules: str = "", skill_texts=None) -> list:
    """The prompt of the researcher: the question, the sources it may ask (ids) and the one command that asks one."""
    listed = "\n".join(f"- `{name}`" for name in sources)
    parts = [_head("researcher", input_doc, roles_dir, list(skills), repo_rules, skill_texts),
             [Block("instruction", CONDUCTOR, "## Research question\n\n" + _fence(query, "text"))],
             [Block("instruction", CONDUCTOR, "## Allowed sources\n\nAsk only these sources, by id:\n\n" + listed)],
             [Block("instruction", CONDUCTOR,
                    "## Ask a source\n\nThe question is already in the query file of this command. Run it with Bash to ask "
                    "the source; for another source change `--source`, for a narrower question write a new query file "
                    "outside the repository and name it in `--query-file`. Every other command is denied.\n\n"
                    + _fence(command, "sh"))],
             [_progress(item, step)],
             [Block("result_contract", CONDUCTOR, "## Result\n\n" + _RESEARCH_RESULT)]]
    return _join(parts)


CONTRACT_TEXT = {"stage-report": _STAGE_REPORT, "review-findings": _REVIEW_FINDINGS, "triage-result": _TRIAGE_RESULT,
                 "research-result": _RESEARCH_RESULT}


def report_fixer(*, kind: str, problem: str, answer: str, item: str, step: str, limit: int = 40_000) -> list:
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
    ]
    return _join([[Block("instruction", CONDUCTOR, text)] for text in parts]
                 + [[Block("instruction", CONDUCTOR, "## The problem\n\n" + _fence(problem, "text"))],
                    [Block("result_contract", CONDUCTOR, "## The contract\n\n" + CONTRACT_TEXT[kind])],
                    [Block("instruction", "role-answer", "## The answer\n\n" + _fence(shown, "text"))],
                    [Block("result_contract", CONDUCTOR, "## Result\n\nAnswer with exactly one fenced block tagged `"
                           + kind + "` holding the corrected JSON object, and nothing else.")]])


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
