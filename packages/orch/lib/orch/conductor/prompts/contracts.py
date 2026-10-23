"""The closed result block each role ends its answer with, and the progress line rule: texts only, byte for byte."""
from __future__ import annotations


RESULT_KINDS = {"executor": "stage-report", "bounded-implementer": "stage-report", "reviewer": "review-findings",
                "triager": "triage-result", "researcher": "research-result", "advisor": "advice"}


_STAGE_REPORT = """\
End your answer with exactly one fenced block tagged `stage-report` holding one JSON object and nothing else:

```stage-report
{"status": "done | done_with_deviations | done_pending_checks | blocked",
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
thing as an `escalation` issue; find all of them before you stop (a changed file's tests, generated files, registries, docs), so one
escalation names every missing path and the plan is widened once. Never guess past such a gap. `done_with_deviations` needs at least one `deviation`
issue. `done_pending_checks` means the work is complete but acceptance checks could not run in your environment: it needs a `pending`
issue naming them, and the conductor runs the checks and closes the piece on their result. Every `checks_run` entry has exactly the keys shown (`id`, `cmd`, `exit`) or, for a manual procedure,
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

_ADVICE = """\
End your answer with exactly one fenced block tagged `advice` holding one JSON object and nothing else.
`recommendation` is the id of one of your `options`; `needs_owner` is true when only the owner can decide; `category`
is optional:

```advice
{"problem_ref": "the problem_ref given above",
 "options": [{"id": "option-id", "text": "what this option does", "pros": ["why"], "cons": ["why not"]}],
 "recommendation": "option-id",
 "confidence": "low | medium | high",
 "sources": ["https://… or repository/path, or empty"],
 "needs_owner": false,
 "category": "security | destructive | public-api | scope-expansion | other"}
```
"""


_PROGRESS = """\
## Progress lines

Before each major step print one line to your output: `[orch] {item} {step} <what you start or finish>`.
"""


CONTRACT_TEXT = {"stage-report": _STAGE_REPORT, "review-findings": _REVIEW_FINDINGS, "triage-result": _TRIAGE_RESULT,
                 "research-result": _RESEARCH_RESULT, "advice": _ADVICE}
