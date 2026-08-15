# P4.4 route-start helper defect

Observed on 2026-08-15 during P4.4 attempt 1: the canonical `task:plan-run`
runtime example calls `task.journal.derive_run_id()` with positional arguments,
but the installed helper accepts keyword-only arguments. No journal entry was
written by the failed call. The equivalent keyword-only call created the valid
route-bound `in-progress` event at `journal.jsonl:147`.

Owner: `packages/task/commands/plan-exec.md` and its generated provider
projections. Repair the example without changing the helper's API.
