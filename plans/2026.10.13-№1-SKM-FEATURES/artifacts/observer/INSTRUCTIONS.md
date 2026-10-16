# Run instructions (owner, 2026-10-14/15) — RE-READ BEFORE EVERY BATCH. Not in repo. (Rebuilt after /tmp wipe.)
Plan: plans/2026.10.13-№1-SKM-FEATURES, roadmap rows 13..18: P9.1-4, P10.1-4, P11.1-3, P12.1-4, P12.5, P13.1-4. Skill: orch-debug. Env: ~/.cache/skm-orch-run/env.sh (all 4 vars!).
UNIT OF RUN = ROADMAP BATCH: ONE `conduct.py run --plan PLAN --items A B C D --scenario scout-solo --options F` per roadmap row. Never one item per run. If started wrong: stop conductor AND executor child, then `run --adopt` with the full batch.
Start correctly at once; owner corrected this twice.

## Economy
1. Executor: only tests of what it changed (affected-tests --run). No ci-matrix/validate.sh/golden full/--tier all/schema compat (say it in `rules`). Heavy runs only by the conductor: item acceptance; phase.validation V11-V13 only on the phase-closing item (P9.4, P10.4, P11.3, P12.5, P13.4).
2. Review: ONE common review per batch when volume is small (not per item); none on trivial/deterministic items. grok/grok-4.7/high, one round, reviewer runs NO commands, reads diff + check results only. Total grok launches <= 4 for the run. Conductor reviews per item -> mechanism gap; do a single review of the batch diff after the last item, fix Major+ in a separate commit.
3. Preflight scan per batch: item validation/rules for runs not affecting code; write-set (task_files!) covers every path the item must touch (schemas, contract.py, fixtures, docs, CHANGELOG, golden); disk df >= 10G; all env vars exported; plan edits COMMITTED before (re)start.
4. write_set derives from item task_files (bridges/planner-orch/brief.py), NOT scope.include.

## Control
- Monitor armed in the SAME turn as run start (+ df watch). Report item end at once. Status >= every 30 min. Never kill a working role; if killing, kill executor child too and clean /tmp/skm-standalone-*.
- Main tree untouched while a run is active (journal lives in ~/.cache/skm-orch-run/, NOT /tmp). Fixes in separate worktree, merge between items; commit explicit paths; no `pkill -f` patterns that match own command (use [x]xx trick).
- After each batch: run-usage.py, step-profile.py, observer.md, metrics row (estimate vs actual, executor/review/checks min, checks share, rounds, heals, beacons, tokens, deviations, findings).
- ANOMALIES: log all in journal.md (prompt effects, subagent interaction, roughness, executor own heavy runs, repeats, idle). Obvious -> fix at once (option+test+docs) and mark found+fixed. Large -> keep and list in final report as needs-study.
- Final: docs/orch-features-run-findings.md + journal into repo (public-hygiene: no concrete plan ids), reviewer prompt. Reports short: done, verified, next.

## Added 2026-10-15 (owner) — proactive observer, correct scheme
- CORRECT SCHEME: one run per roadmap row (`run --items A B C D`), ONE shared executor session across its pieces (`session.executor: shared`, default; `--no-single-session` only on purpose); never one run per item, never describe `--items` as a mere queue. Plan write sets for orch-module items = the whole module (+bridge, golden, CHANGELOG, config.example.toml).
- BE ACTIVE while a role works: look inside every few minutes — beacons, the live stream (`.swissknifeman/state/orch/conductor/<run>/<item>/streams/*.jsonl`, `step-profile.py`), the prompt it got, what files change in the tree (read-only), df. Evaluate: is it on track, looping, reading too much, running heavy commands, editing by heredoc instead of Edit? Think how the work could be organised more efficiently and write the idea down at once.
- Small fixes (a few lines, obvious, testable) are made at once in the worktree (~/.cache/skm-wt-session) with a test and merged between pieces; larger ones go to FINDINGS.md (STUDY) for the end-of-plan review. Do not wait for a decision on the small ones.
- FINDINGS.md, INDEX.md, journal.md, INSTRUCTIONS.md live in the plan folder (`plans/<plan>/artifacts/observer/`) and link to everything (run ids, state dirs, commits, worktree, memory) so a lost session can be rebuilt from them; source copy in ~/.cache/skm-orch-run/observer/, `sync-observer.sh` copies+commits it when no run is active; sync after every batch. Never keep run files in /tmp.
- Reports to the owner stay short: done, verified, next.

## Added 2026-10-15 (owner, strict) — batch by default, polished system by the end of the plan
- ANY run whose work names several pieces (`--items A B C`, a roadmap row, the batch that `plan.py next` names, `--ready`) is a BATCH by default: all pieces in progress at the start, one executor session, list of all pieces in the first prompt. Separate sessions only on an explicit `--no-batch`. No path may silently fall back to piece-by-piece.
- Every default parameter must be written down (docs + code + a test that keeps them in step) and every rough edge found while observing is fixed or logged at once. Spend extra time on it: the goal is a fully polished, reliable system at the end of the plan.
- Study the internals while a run works: how the processes talk to each other (conductor, bridge, planner, provider CLI, guard), what can block them (ownership/fencing, dependencies, dirty tree, sandbox/Landlock, disk), and how to improve it. Not only the per-item analysis: be curious, keep reading the streams, prompts, state files.
- 2026-10-15 (owner): DO NOT start phase P13 until the owner says so. Keep fixing and polishing; park P13.
