## Findings
[Major] packages/orch/lib/orch/conductor/application/run_service.py:79 - `resume --retry` only accepts an executor step whose saved report status is `blocked`, so a piece the conductor itself blocked never reopens.
Scenario: checks stay red (`CHECKS_RED`), a review hits `REVIEW_LIMIT`, or `scope.outside` is `block` and `execute.executor_round` wraps the report only after `_step` has stored status `done` -> `RETRY_NOT_BLOCKED` even though the escalation says to retry.
Fix: persist that wrapped blocked report on the executor step (or treat a blocked piece with no blocked executor round like an advice hold and drop `register`/`close`/`commit`).

[Major] packages/orch/lib/orch/conductor/application/loop.py:102 - `--adopt` paths captured for the first still-open claim are attached only when the first listed item runs, so a later item keeps a dirty tree and records those paths as source changes.
Scenario: items A,B with `--adopt`, A already `done`, tree dirty; `claim_all` skips the clean-tree check and returns the dirty paths, then `pieces` skips A and gives B `adopted=[]` -> B's `source_paths` swallows the files, so they miss the write-set check and the commit.
Fix: attach `first_adopted` to the first item that actually runs, or require a clean tree when the first listed item is already closed.

[Major] packages/orch/lib/orch/conductor/stages/execute.py:270 - `_adopted` checks the stored path list, not the tree now, so clearing the stray files does not make resume succeed.
Scenario: `--adopt` snapshots `src/ok` and `notes/tmp` (outside the write set) -> `WORKTREE_DIRTY`; the owner deletes `notes/tmp` and resumes -> the same stop, because `state["adopted"]` still contains `notes/tmp`.
Fix: drop adopted paths that are no longer dirty before the write-set check.

[Major] packages/orch/lib/orch/conductor/infrastructure/work_source.py:127 - a failed or unreadable re-brief returns with no record, and the next executor round keeps the previous input.
Scenario: the plan's write set is amended, `source brief` exits non-zero or the blob is not JSON -> the correction round still uses the old digest and write set, and can commit paths the amended plan no longer allows.
Fix: emit a visible failure (or stop) and do not continue on the stale input.

[Major] packages/orch/lib/orch/conductor/infrastructure/work_source.py:187 - `artifacts_dir` is documented as a repository-relative folder, but `project / artifacts_dir` accepts an absolute path or `..` and writes the piece's records there.
Scenario: brief `artifacts_dir` is `/tmp/out` or `../outside` -> `stage-report.json`, the review verdict, and check evidence are written outside the project, and commit is asked to take that path.
Fix: resolve the directory and stop unless it stays inside the project.

[Minor] packages/orch/lib/orch/conductor/stages/context.py:28 - a write-set pattern can walk `..` and the role prompt then reads a `CLAUDE.md` or `AGENTS.md` outside the repository.
Scenario: write set `../../../secret/CLAUDE.md/placeholder` with `module_rules` enabled -> that parent file's matching section is inserted into the isolated role prompt.
Fix: stop the walk on a `..` segment and only read files under the project root.

## Checked and fine
- Closed steps are skipped from the saved result, and `corrections_at` / `check_fixes_at` / `autofix_at` are not incremented again when that round is replayed.
- Work-source calls use an argument list (`run_orch`, register, commit); the closer and research commands are built with `shlex.join`.
- Preflight still stops required roles on acp, a disabled or missing provider, a required sandbox, or an open quota gate before executor work.
- Active time is the saved segments plus the current monotonic segment, and `RUN_TIMEOUT` is a `Stop` that the loop stores on the run.
- `release` still refuses a piece that already has an executor step or is `done`, and `resume`/`release`/`settle` raise `RUN_UNKNOWN` when `run.json` or `state.json` is missing.
- Overlapping checks and review still cancel the review when a check goes red, and a review that finished first is carried into the same correction via `combined`.