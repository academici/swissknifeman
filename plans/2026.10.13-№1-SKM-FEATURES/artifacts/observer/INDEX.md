# Observer index: how the PLAN4 (SKM-FEATURES) conductor runs were driven

Start here if the session of the observer is lost. This folder is copied into the plan (`plans/2026.10.13-№1-SKM-FEATURES/artifacts/observer/`); everything the observer knew is either here or listed below with its path.

## Files in this folder
| File | What |
|---|---|
| `INDEX.md` | this map |
| `FINDINGS.md` | defects found: FIXED (with commits) and STUDY (needs a decision) — the list for the end-of-plan review |
| `journal.md` | chronological journal of actions, mistakes and decisions of the observer |
| `INSTRUCTIONS.md` | the owner's run instructions (economy, review budget, batch rule, control) |
| `run-options.json` | the `--options` file of the runs (rules for the executor, review off, limits) |
| `env.sh` | the four env vars a conductor run needs (`PLANNER_ROOT`, `PLANNER_PLAN_PY`, `SKM_ORCH_ROOT`, `AICORE_ROOT`) |
| `logs/` | progress logs of the P10 runs (`run-p10-*`) and `ci-matrix-profile.txt` (per-step seconds of V11). The P9 logs were lost with `/tmp`; the same progress lines are in each run's state dir (`progress` journal) and in `observer.md` of the run. |

## Where everything else is
- Repository: `/home/vostrikov/projects/packages/swissknifeman-next`, branch `ecosystem-split`. Plan: `plans/2026.10.13-№1-SKM-FEATURES` (items `phases/P*/P*.*.json`, results in `result`, evidence `artifacts/<item>/evidence/`).
- Conductor runs (state is local, gitignored): `.swissknifeman/state/orch/conductor/<run>/` — `run.json`, `state.json`, per item `P*.*/streams/*.jsonl` (raw role streams), `prompts/`, `reports/`, `options.json` (since the copy fix). Observer reports: `.swissknifeman/orch/reports/<run>/observer.md`.
- Tools: `python3 packages/orch/scripts/conduct.py status|observe|resume|settle`, `run-usage.py <run>`, `step-profile.py <stream.jsonl>`, `estimate.py`.
- Observer skill: `packages/orch/dev-skills/orch-debug/SKILL.md` (0.3.0). Memory of the assistant: `~/.claude/projects/-home-vostrikov-projects-packages-swissknifeman-next/memory/` (`feedback-orch-batch-runs.md` and others).
- Worktree with the observer's mechanism fixes: `~/.cache/skm-wt-session`, branch `orch-shared-session` (see its status below).
- Source of this folder while a session lives: `~/.cache/skm-orch-run/observer/`; `sync-observer.sh` there copies it into the plan folder and commits it (only between runs: a dirty plan folder makes the conductor refuse its commit).
- Do not keep run files in `/tmp`: it was wiped twice (a disk cleanup, then something else).

## Runs
| Batch | Run id | Items | Result |
|---|---|---|---|
| B1 | `cnd-20261014T173854Z-697e72` | P9.1-P9.4 (phase P9 closed by P9.4) | done; commits `2e0f282b1`, `ebe9e2e63`, `fb90a9a14`, `61cc61aac`; owner-side fix of the P8 tail `96b4b54a0` |
| B2 | `cnd-20261015T053109Z-7b7f1a` | P10.1, P10.2 (stopped by the observer to switch to a shared session) | P10.1 `d44a8b4ae`, P10.2 `43ee2c958`; plan write-set commits `31cbcf5ac`, `f2149a8b0`, `da1ce7e10`, `1386ca67c`; golden fix `117af6fcf` |
| B3 | `cnd-20261015T062002Z-5ee94d` | P10.3, P10.4 (closes phase P10: V11 `ci-matrix run --all`, V12, V13) | P10.3 `69285e82f`; P10.4 see the log |

Mechanism fixes made by the observer: `8271eabfc` (shared executor session, merged); in the worktree, not yet merged unless the journal says so: `7762b7053` (drop `--no-session-persistence` for shared executors), `489663831` (golden check with every unit change), `493f510ee` (options.json, brief guard, prompt rule). After merging, record the new hashes here.

## Continue from here (prompt for a fresh session)
> Read `plans/2026.10.13-№1-SKM-FEATURES/artifacts/observer/INDEX.md`, then `INSTRUCTIONS.md`, `FINDINGS.md`, `journal.md`. You are the observer (skill `orch-debug`). Check `git status`, `git log --oneline -15`, `python3 packages/orch/scripts/conduct.py status`, `git -C ~/.cache/skm-wt-session log --oneline -6`. Finish the open work in the journal (merge the worktree commits, then start the next roadmap batch: P11.1-P11.3, one run, `run --items`, shared session by default). Keep the journal, the findings and this index inside the plan folder after every batch.
