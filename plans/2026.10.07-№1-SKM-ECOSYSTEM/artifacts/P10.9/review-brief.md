# Read-only review: orch.run.* events, data schemas, events.emit, fixtures

You are an independent reviewer. The repository is /home/vostrikov/projects/packages/swissknifeman-next (working tree,
uncommitted changes of one item; `git status` shows them). Do not edit files; the repository is read-only for you.
You may run tests and commands. Report findings only; the executor fixes them.

## Scope (new or changed)

- `packages/orch/unit.json` (provides.events, contract urn:swissknifeman:orch:event-data)
- `packages/orch/schemas/event-data/v1/*.schema.json` (4 closed schemas)
- `packages/orch/lib/orch/events.py` (`emit`, `data_schema`)
- `packages/orch/tests/test_events.py`, `packages/orch/tests/fixtures/events/**`
- `packages/orch/docs/{events,index}.md`, `CHANGELOG.md`

## Contract

1. Types and data: orch.run.started {run_id, submission_id, attempt_id, source{plugin,ref}, scenario} (all required);
   orch.run.stage.finished {run_id, stage_id, attempt, status} + optional attempt_id, error_class (error/v1 class or
   unknown_outcome), input_digest; orch.run.finished {run_id, submission_id, ref, attempt_id, outcome
   done|done_with_deviations|blocked|refused, gate pass|missing|red|stale|none}; orch.run.refused {submission_id,
   step claim|prepare|register, reason_codes[]} + optional run_id, ref, policy_id, binding. Closed profile.
2. `$id` is `urn:swissknifeman:orch:event-data:<type with dots as hyphens>:v1`; the pattern of the planner module is the model.
3. `emit` never raises; when `settings.events_enabled` is false nothing is written; any failure prints one line
   `ORCH_EVENT_NOT_EMITTED: <type>: <reason>` on stderr; no secret value may appear in output or journal.
4. Pure operations (prepare --dry-run, policy test) do not emit.
5. Product files are English, with no plan IDs, `PLAN<n>` tokens or home paths. Core orch names no partner package.

## How to check

`export HOME=$(mktemp -d) SKM_HOME=$(mktemp -d) SKM_AICORE_EVENTS__DELIVERY=off`, then
`bash packages/orch/scripts/test.sh`, `bash packages/orch/scripts/validate.sh`, `python3 scripts/test-event-contracts.py`,
`python3 scripts/ecosystem-units.py check`.

## What to report

Only real defects: wrong behaviour, a violated contract item, a missed edge case, a test that passes without testing
anything, a doc statement that disagrees with the code. Skip style. For EVERY finding give file:line, one sentence, and a
reproduction (failing test or command output, written outside the repository). Without one it is at most "plausible".
Finish with `VERDICT: no findings` or `VERDICT: N findings`.
