You are an independent read-only code reviewer. Do not edit anything; inspect, run commands and tests, report findings, stop.

Repository: the current directory (a git working tree with UNCOMMITTED changes). Review ONLY these paths (other dirty paths belong to the owner): `git diff HEAD -- packages/orch CHANGELOG.md` plus the untracked files `packages/orch/lib/orch/{retry,journal,effects}.py` and `packages/orch/tests/{test_runstate_properties,test_retry,test_journal,test_effects}.py` (see `git status --short packages/orch`).

Change under review (plan item P10.6) — concurrency and integrity model of orch execution:
- `lib/orch/port.py` `RunState.apply`: fixed order of checks (foreign contract_version kept and not applied; schema; run_id; dedup by `event_id` with EVENT_CONFLICT; seq rules SEQ_ORDER; fencing by `owner_epoch` with STALE_EPOCH; stage rules). A rejected event must change NO state (including `_max_epoch`, `_ids`, `_seen`, `_foreign`). A normalized error/v1 of an event is copied into the stage error record. `EnginePort.watch(run_id, after_seq=None)`.
- `lib/orch/retry.py`: `class_of`, `decide(RetryInputs, policy)` — rules in order: policy/default action; unknown_outcome of a writing stage is always reconcile; a repeating action of a writing stage with dirty worktree or unresolved receipt becomes reconcile; budgets (attempts_used counts attempts including the failed one); retry_after wait; fallback_route (first declared route different from current, else FALLBACK_UNDECLARED); replan.
- `lib/orch/journal.py`: run journal under `<state>/orch/runs/<run_id>/`; `append_event` validates, takes `flock` on `events.lock`, dedups by event_id / seq under the lock, appends one line with O_APPEND + fsync, handles a torn tail; `read_events(dir, after_seq)`; atomic `write_doc`/`read_doc`; `run_dir` must not allow path escape.
- `lib/orch/effects.py`: `check` / `record` — precondition re-check right before an effect; applied receipt → already_applied; unknown receipt → reconcile request; mismatch → failed receipt PRECONDITION_CHANGED.
- Docs: `packages/orch/docs/engine-port.md`; CHANGELOG.md.

Design decisions that are intentional (do not report them): journal reports a seq clash as SEQ_ORDER and an event_id clash as EVENT_CONFLICT; an event without `contract_version` is INPUT_INVALID, only a present different version is foreign; orch uses only stdlib, orch and aicore; time is passed as an argument, never read.

What to look for (hard risks): an effect repeated or an outcome lost; a rejected event that still changes reducer state; two journal writers corrupting or duplicating events; torn-line handling; path traversal through run_id or document names; retry decisions that repeat a write after partial changes; off-by-one in budgets; Python 3.9 incompatibility (the package must run on 3.9); public-API/schema inconsistencies between code, docs and tests.

Run the checks yourself: `bash packages/orch/scripts/test.sh` (about 10 s) and `bash packages/orch/scripts/validate.sh`.

Output format: a short summary, then numbered findings, each `path:line — one-sentence defect` followed by `REPRODUCTION:` with a failing test or command output you actually ran. A finding without a reproduction is at most "plausible" and must be labelled so. If nothing is wrong, say so plainly. Do not suggest style changes.
