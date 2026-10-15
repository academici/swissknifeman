# Findings of the observer (B1 P9.1-4, B2/B3 P10.1-4) — for the end-of-plan review
Status: FIXED (merged or in worktree orch-shared-session) / STUDY (needs a decision). Data from the run state, not from memory.

## Fixed by the observer
F1 FIXED planner `reads[].included` rejected by closed exec/v1 reads schema (P9.1 PREPARE_REFUSED) — optional field + test.
F2 FIXED single executor session per run: `session.executor` shared (default), `run --single-session/--no-single-session`; resume of previous executor session + `## Run batch` block. 9 tests. (8271eabfc)
F3 FIXED shared executor ran with catalog `--no-session-persistence` -> `No conversation found` on resume; the flag is dropped for shared executors; real `claude -p --resume` verified (same session id, context kept). (7762b7053)
F4 FIXED golden/affected-tests blind spot: `affected-tests` ran golden only for hub paths, so a unit change (new verb, role in launch catalog, skiller help range) left golden red until the phase-closing V12 (P8 tail cost ~1h of red rounds in P9.4; P10.1/P10.2 left orch-help/launch-list red). Now every unit change runs `golden.py check` (9 s). (489663831)
F5 FIXED skiller help hard-coded `sed -n '8,34p'` cut validate/doctor/version after P8 grew the header; test_selection checked sibling-module paths in standalone copy. (96b4b54a0)
F6 FIXED brief guard (`LIFECYCLE_PHRASES`) rejected a role manifest read because its `forbidden_inputs` names `report_api` (P10.2 BRIEF_REFUSED). (493f510ee)
F7 FIXED conductor keeps the `--options` file as `options.json` in the run dir; `resume` fell over with OPTIONS_INVALID after a /tmp cleanup. (493f510ee)
F8 FIXED executor prompt: list ALL missing write-set paths before escalating. P10.2 blocked 3 times, one missing path per round (contract.py/role-manifest/fixtures, then launch.py, then orch-skiller test). (493f510ee)

## Needs study (not fixed)
S1 `resume --retry ITEM` after a blocked round ends in REGISTER_REFUSED ATTEMPT_CONFLICT: attempt id is `att-<run>-<item>` (bridges/planner-orch/worksource.py:224), constant per run+item, and the blocked outcome is already registered. Workaround: `plan.py reopen` + `resume`. Fix idea: attempt id with a retry counter (claim carries it) or registrar supersedes.
S2 check evidence stores the exit code only (no output tail): a red phase round is blind; executors answered "blocked/no change" (P9.4 executor.2 1m55s, executor.3 blocked). Also `ci-matrix` prints nothing the conductor keeps. Fix idea: keep the last N lines of stdout+stderr of a red check in the evidence (schema change).
S3 red-first reruns V11 (ci-matrix --all) completely after every fix round: 11-18 min each. Fix idea: rerun only failed rows (ci-matrix `--only fail` or a failed-units list).
S4 ci-matrix runs units sequentially: 677 s wall = sum of steps; standalone 57% (orch standalone 194 s, planner 101 s), tests run twice (test + standalone). Parallel units or standalone only for touched units in phase validation.
S5 no disk preflight: ENOSPC killed the conductor mid-run (P9.4 phase checks) and later nearly again; conductor traceback truncated and shows source of already-modified engine.py (the conductor runs the code it edits). Fix idea: `limits.disk_min_gb` check at run start and before heavy checks; beacon with df.
S6 killing the conductor leaves the executor `claude -p` child alive; killed `standalone --baseline` left orphan par_unittest workers and /tmp/skm-standalone-* dirs (filled the disk). Process-group kill and cleanup on exit.
S7 write sets: task_files are a fence, not a hint, and plan authors forget companions (generated config.example.toml, KINDS in contract.py, role-manifest enum, fixtures, docs, golden, orch-skiller test ROLES). Cost: P10.1 1 block, P10.2 3 blocks, P9.2/P9.3 earlier. Plan-lint idea: an item that adds a conductor schema/role/verb gets the companion set automatically; for orch-module items write set = module.
S8 Executors edit files by `python3 - <<heredoc` replace scripts in Bash and read via cat/sed: P10.2 Bash 81 calls, Edit 1, 30 reads via Bash; P10.3 Bash 45, Edit 0; P10.4(a2, 20 min) Bash 65, Read 0, Edit 0, 30 reads via Bash, heredoc edits 68-120 s each. The cost driver is model turns (86-160 per piece), not commands (tests 3-23% of the step). Idea: a prompt rule to use Read/Edit/Write and to batch reads; measure on the next batch. Not tried (changes the golden prompts).
S9 `plan.py show` result.notes keeps the text of the previous blocked attempt after a retry whose register failed (confusing: executor.2's real reason was elsewhere).
S10 `settle`/`release`/`ITEM_OWNED` message references `--take-over` that does not exist; `plan.py set` refuses status/result (FIELD_OWNED); `resume` after a failed resume consumed `--retry` (RETRY_NOT_BLOCKED).
S11 phase-closing item P8.6 closed with V12 not green (so the phase closing gate does not enforce its own acceptance?): check why P8.6 passed.
S12 `CHECK_SLOW` timers include the time a process was SIGSTOPped; no pause/resume support in the conductor for disk emergencies (I used SIGSTOP by hand).
S13 observer mistakes (for instructions): B1 started per item instead of per batch (skill said "one item per run"; owner corrected twice); scope.include widened instead of task_files; env vars incomplete; plan edits not committed; no estimate.py run per item (skipped, not measured); journal in /tmp (lost); pkill -f killed own shell.
S14 shared session is only for Claude Code executors; codex/grok route always fresh. Titles of later pieces are not in the first prompt (only refs).
F9 FIXED orch-skiller test_resolve_role ROLES was a hand-kept tuple that broke on every new role (P10.2, P10.4 deviations); now derived from orch/roles/*.json.
