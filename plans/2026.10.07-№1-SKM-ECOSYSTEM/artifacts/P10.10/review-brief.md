# Read-only review: work-source port of orch, planner-orch plugin, owner fencing and evidence gate

You are an independent reviewer. The repository is /home/vostrikov/projects/packages/swissknifeman-next (working tree,
uncommitted changes of one item; `git status` and `git diff` show them, new files are untracked). Do not edit files;
the repository is read-only for you. You may run tests and commands (write only under a temporary directory).
Report findings only; the executor fixes them.

## Scope (new or changed)

- `packages/orch/schemas/work-source/v1/{input,output}.schema.json` (closed, oneOf by `op`)
- `packages/orch/unit.json` (contract `urn:swissknifeman:orch:work-source`, extension point `work-source`)
- `packages/orch/lib/orch/worksource.py` (`WorkSource`, `PluginWorkSource`, `problems`, `WorkSourceError`)
- `packages/orch/lib/orch/cli.py` (`orch.py source claim|brief|prepare|register`, `_dry_run` shared with `prepare`)
- `packages/orch/tests/test_worksource.py`, `packages/orch/tests/fixtures/work-source/fake/**`
- `bridges/planner-orch/{extension.json, worksource.py, register.py, unit.json, README.md}`,
  `bridges/planner-orch/tests/{test_worksource.py, test_register.py}`
- `scripts/e2e-work-source.sh`
- `packages/aicore/lib/aicore/config/model.py` (`SKM_<MODULE>_ROOT` is not configuration), its test and README
- `configs/config-inventory.json`, `packages/orch/docs/{work-source,index,contracts}.md`, `packages/orch/README.md`,
  `CHANGELOG.md`, `tests/golden/**` (orch help output)

## Contract (what must hold)

1. Ownership: `claim` = `plan.py start <plan> <ref> --actor <P/M/E> --session <run_id> --no-scout`; an item held by
   another session is `blocked` with `ITEM_OWNED`, never taken over. `attempt_id = "att-" + run_id + "-" + ref`,
   `session = run_id`; a repeated claim with the same run_id gives the same answer.
2. Scenario: the item's scenario is checked with `orch.py policy show <scenario>` before start; unknown →
   `blocked` `SCENARIO_UNKNOWN` and the item is not started.
3. Fencing (`register.py --owner-session SESSION`): before ANY plan write, the item must be held by SESSION
   (`result.executor.session`) or already closed by this same attempt (`result.attempt_id == --attempt-id`);
   otherwise `REGISTER_STALE_OWNER` and nothing is written (also no `log`). A repeat after a lost answer is a no-op.
4. Evidence gate (`--gate evidence`): for `done`/`done_with_deviations` every acceptance check of the item needs a
   check-evidence file (exit 0, or verdict pass) → else `REGISTER_EVIDENCE_MISSING` / `REGISTER_EVIDENCE_RED`, before
   any plan write; `checks_run` claims without a file never become `--check`; `blocked` passes without evidence.
   Without the two flags register behaves exactly as before.
5. The bridge writes the plan only through `plan.py`; it never writes plan files.
6. Brief: built in process (read-only), stored with `aicore.state.blobs.put_json` in the plan repository, declared
   with `plan.py add-artifact --role input --path <blob>` (repeat no-op); a repeat with unchanged inputs reuses the
   stored brief (`reused: true`, same digest).
7. orch client: every request and answer is validated against `work-source/v1`; no registration →
   `WORK_SOURCE_UNAVAILABLE` (CLI exit 3); plugin failure or answer outside the contract → `WORK_SOURCE_FAILED`.
8. CLI: `submission_id = "sub-" + sha256_hex(canonical({plan, items, actor}))[:24]`, `run_id = "run-" +
   sha256_hex(submission_id)[:24]`; `run.json`, `launch-plan.json`, `receipts/register.json` only under the run
   directory; events `orch.run.*` only after the run journal is written; exit 0 ok, 1 refusal, 2 usage, 3 unavailable.
9. orch core names no partner package (`tests/test_boundaries.py`); product files are English, no plan ids, no home paths.

## How to check

```
export HOME=$(mktemp -d) SKM_HOME=$(mktemp -d) SKM_AICORE_EVENTS__DELIVERY=off
bash packages/orch/scripts/test.sh
bash scripts/test-bridges.sh
SB=$(scripts/dev-sandbox.sh new --name rv-ws-$$ | tail -1) && scripts/dev-sandbox.sh run "$SB" -- bash scripts/e2e-work-source.sh; scripts/dev-sandbox.sh remove "$SB"
python3 scripts/ecosystem-units.py check
```

## What to report

Only real defects: wrong behaviour, a violated contract item above, a race or ordering bug (a plan write before a
guard), a missed edge case, a test that passes without testing anything, a doc statement that disagrees with the code.
Skip style. For EVERY finding give file:line, one sentence, and a reproduction (failing test or command output,
written outside the repository). Without one it is at most "plausible". Finish with `VERDICT: no findings` or
`VERDICT: N findings`.
