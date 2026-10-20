# Repair: the `stage-report` block of P1.1 executor.1

A role finished its work and ended its answer with a result block that does not fit the contract. You do not redo, judge or extend the work, read no file and run nothing. You rewrite that one block from the facts the answer states.

## Rules

- Keep every fact of the answer: statuses, paths, check ids and exits, verdicts, findings, reasons.
- Never invent a check, an exit, a verdict, a path, a finding or a reproduction the answer does not give; when a required fact is missing, use the closest honest statement of the answer (for example an issue that says what is missing).
- Never raise a status: a blocked answer stays blocked.
- Change only what the problem below names, plus what the contract needs for the block to be valid.

## The problem

```text
/status: missing
```

## The contract

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

## The answer

```text
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Result

Answer with exactly one fenced block tagged `stage-report` holding the corrected JSON object, and nothing else.
