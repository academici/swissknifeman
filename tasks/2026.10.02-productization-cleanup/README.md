# Task: self-contained product — no plan references, one run command, English-only

**Status:** ⬜ approved by owner 2026-10-01, to be executed in a NEW session (this file is the full brief).
**Base:** working tree of 2026-10-01 (uncommitted: task-lean-execution L1–L5, plan-id.py, gitignore-policy +
`maind doctor --gitignore-drift`, `memory.bind_host`, abs-path cleanup). Commit or branch it first (owner decides).
**Format:** one bounded task, phases below; each phase ends with ONE read-only review step (separate session or
reviewer), not a review per item. Run each broad suite once per phase, not per edit.

## Owner decisions (final)

1. Remove ALL working documents from the repository index and ignore them: `plans/`, `roadmap/`, `tasks/`,
   `.cursor/plans/` (≈4.5 MB). Files stay on disk locally (`git rm -r --cached` + `.gitignore`), history stays in git.
2. Nothing in the tracked product may reference those plans: no concrete plan IDs, no paths into them, no
   Short-ID citations (`PLAN1.D35`), no calibration/fixture/contract that reads or names a plan file.
   Generic protocol text (`plans/<PLAN-ID>/…` placeholders describing consumer projects) stays.
3. One universal run command: `task:plan-run` (inherits the session route). `plan-exec` disappears as a command.
4. Everything inside the product is English and compact (commands, skills, protocol, templates, configs, docs,
   code comments, diagnostics). Commit messages stay Russian Conventional Commits unless the owner says otherwise.
5. Result must be a coherent product: all suites green except the baseline list, no dangling references.

## Baseline (record before editing; these fail on clean HEAD, not part of this task)

`skiller test_release::test_dry_run_reaches_skiller_without_error` (RELEASE_IMMUTABLE_TUPLE — fixed by the release
version bump, last step); `maind test_onboard` ×9 (needs live memory daemon); `artifex` 2 failures + 7 errors
(`test_package_promotion`, `test_business_dispatch`, `test_cli`, `test_compiler` — read ARTIFEX plan artifacts;
resolved by P1 below). Re-measure with each package's `scripts/test.sh` / `scripts/validate.sh`.

## P1 — Decouple the product from plans (before untracking)

Inventory (regenerate, do not trust numbers): ≈700 mentions of concrete plan IDs in product files —
`packages/task/tests` 143, `task/lib` 120 (mostly citation comments), `skiller/skills` 86 (74 files), `docs/` 150+,
`skiller/lib` 38, `task/configs` 33, `skiller/tests`/`docs` ~50, `harness/tests` 16, `analyst/lib` 12, `core/tests` 9,
`artifex/tests`, `scripts/*`, `configs/provider-capabilities.json` (76), `configs/locale-corpus-v1.json`.

```bash
git grep -nIE "20[0-9]{2}\.[01][0-9]\.[0-3][0-9]-(№[0-9]+-)?[A-Z]|PLAN[0-9]+\.|plans/(archive/)?20|roadmap/|tasks/20" \
  -- . ':!plans' ':!roadmap' ':!tasks' ':!.cursor/plans' ':!releases'
```

Functional dependencies (tests/code that READ a plan file) — find them by simulation, in a throwaway worktree:
`git worktree add <tmp> HEAD && cd <tmp> && git rm -rqf plans roadmap tasks .cursor/plans`, then run every package
suite and diff failures against the baseline. 2026-10-01 measurement: task 9 tests (lifted-schema byte-identical
checks, `resolve_plan_dir(...)` contract examples, route/task_contract fixtures), skiller 1, harness ≥30 (`test_instruction_*`,
`test_provider_*`), artifex all plan-reading tests.

Rules:
- Needed data → copy into the owning package's `tests/fixtures_data/` (synthetic/minimized, no plan names) and point
  the test there. Byte-identity tests against a plan-lifted file → compare against the package's own committed file.
- Citation comments/docstrings (`(2026.07.24-AGENT-RELIABILITY P2.4)`, `D78`, `P0.2`…) → delete or reword to state
  the rule itself. No replacement IDs.
- Skills/docs/configs naming plans → reword; `_doc`/`evidence` strings in JSON configs likewise.
- Digest-pinned files: `packages/maind/tests/test_provider_deploy.py` (D108/D115 preimage bytes pinned by sha256 in
  `provider_deploy.py` — keep bytes; the code constant and fixture are one unit, rename IDs only if both change);
  `provider-harness.md` + the P5 harness-conformance artifact embed an audit digest — regenerate with
  `render_operator_reference`/`render_p5_artifact` after any harness fixture edit, and move the artifact out of
  `plans/archive/…` (the test must not read a plan path).
- `packages/task/configs/*calibration*.json` already use `corpus/<name>` labels; `calibrate-token-estimate.py`
  reads plan artifacts as corpus — repoint its CORPUS to package-local sample files.
- Generated carriers: `skiller registry`, `packages/task/scripts/render-provider-commands.py --write --root .`,
  `packages/harness/scripts/render-cursor-rules.py --write`, `scripts/docs-sync.sh` (revert unrelated stale `docs/task`
  copies it touches).
- Add the gate (below) in the SAME phase so regressions fail immediately.

Gate (extend `scripts/public-hygiene.py`, with tests): fail on (a) tracked paths under `plans/ roadmap/ tasks/ .cursor/plans/`
(after P2), (b) concrete plan-ID regex above, (c) Short-ID citations `PLAN\d+\.[DPF]`, (d) `roadmap/` or `tasks/20…`
links; allow generic `plans/<PLAN-ID>` placeholders. Remove the temporary `CONTENT_EXEMPT_PREFIXES`.

Acceptance: simulation worktree (plans/roadmap/tasks removed) passes every suite = baseline minus the artifex plan
failures; gate green; `git grep` inventory returns nothing.

## P2 — Untrack working documents

`git rm -r --cached plans roadmap tasks .cursor/plans`; add `/plans/ /roadmap/ /tasks/ /.cursor/plans/` to `.gitignore`;
update `configs/gitignore-policy.json` (swissknifeman root has them ignored; fleet projects keep their own policy)
and `docs/roadmap.md`, `docs/status.md`, `docs/rejected-optimizations.md`, `docs/reference.md`, `docs/provider-support.md`,
`.vitepress/config.mts` links that point at removed paths. Root `CLAUDE.md`/`AGENTS.md` and `plans/ACTIVE.md` handling:
nothing tracked may link to the ignored folders. Verify `plan-lint` still works locally against the ignored `plans/`.
One commit, only on explicit owner approval (changes what the repository publishes).

## P3 — One command: `task:plan-run`

Differences found (2026-10-01): lifecycle identical; `plan-exec` pins `implementation/medium` (Claude frontmatter
`model: sonnet` switches the model on invocation; Codex/Cursor launch pins), `plan-run` inherits the session route and takes
the minimum from the plan row; only `plan-run` materializes the owner invocation (`task_contract._materialize_owner_invocation`,
`plan_repeat`). Route admission is already class-ladder only (stronger model admitted, weaker stops, pool in
`command-routing.json`).

Design:
- Catalog: drop `task:plan-exec` from `configs/command-routing.json` + `commands/`; keep `task:plan-run` as the single
  execution command (routing `inherited-plan`). Merge the two instruction bodies into ONE compact English command.
- Readers keep accepting the legacy spelling: `journal.COMMANDS`, handoff/Next regexes (`plan_delivery`, `review_policy`),
  `terminal_policy`/`plan_item_state`/`plan_returns` command sets, `task_contract.resolve_exec` (`plan-exec`/`manual`/`plan-run`
  → one mode), `terminal_admission --command`, `plan_work --command`. Writers emit only `plan-run`.
- Routing `Exec` column: canonical `run | plan-design`; lint accepts legacy `plan-exec|manual|plan-run`; execution-sheet,
  launch blocks, handoff templates, `plan_assurance` Next strings emit `task:plan-run`.
- Provider projections regenerate (`packages/task/adapters/{codex,cursor}/…`, claude-golden fixtures, publication locks,
  `command-locale` ids/preimages: collapse to one id and refresh digests), harness hooks/lifecycle that name `plan-exec`,
  maind/harness docs. Remove the `ECONOMY_ROUTE_OVERSHOOT`/`--owner-accepts-overshoot` leftovers.
- Tests: ≈300 references (`packages/task/tests` 141+173) — mechanical rename plus legacy-spelling acceptance tests.
Acceptance: no `task:plan-exec` emitted anywhere; legacy journals/handoffs still parse; `validate.sh` green.

## P4 — English and compact

Scope, in order: `packages/task/commands/*.md`; `packages/skiller/skills/general/plan-protocol/**` (SKILL, references,
snippets/templates — runtime copy regenerates); other skills with Russian text; `configs/*.json` `_doc`/notes; generated
adapters (regenerate); package `docs/**` and root `docs/**`; code comments and diagnostics in `packages/*/lib`, `core`,
`scripts`; test names/messages. Detect: `git grep -nP "[А-Яа-яЁё]" -- . ':!plans' ':!roadmap' ':!tasks' ':!releases'`.
- Compact = state rules once, no history/rationale narration, no repeated phase context; keep behaviour identical.
- Package `CLAUDE.md` invariants say “Russian diagnostics / Russian commit messages”: change the instruction catalog source
  (not the generated file) to English diagnostics; keep commit-message rule as is.
- Locale machinery (`core/locale`, `command_locale`, `locale-corpus-v1.json`, `configs/command-locale-preimages`) exists to
  serve Russian overlays — decide with the owner whether to keep it; if Russian disappears, remove it with its tests.
- Canon weight budgets (`packages/task/configs/canon-weight-budget.json`, skiller `budget`) should drop; update, never raise.
Run in package order task → skiller → harness → maind → analyst → artifex → core; one broad suite per package at the end.

## P5 — Integrity and wrap-up

- Resolve drift found earlier: root `configs/command-routing.json` is a stale divergent copy of
  `packages/task/configs/command-routing.json` (runtime uses the package one) — delete it or make it the single source;
  3 unreferenced contract schemas (`audit-finalization-v1`, `evidence-graph-v1`, `history-projection-v1`) — wire to a
  consumer or delete; `token-estimate-calibration-v1.json` is a calibration input, keep.
- `maind doctor --gitignore-drift` and `plan-id.py` docs/tests still valid after renames.
- Full sweep: each package's `scripts/validate.sh`/`test.sh`, `scripts/test-public-hygiene.py`, `scripts/public-hygiene.py`,
  `skiller registry`, render scripts `--check`, `core.tests`, `maind doctor --gitignore-drift` on the fleet (read-only).
- Release prep only: bump unit versions (`general`, `package.skiller`, task, harness, maind as needed) so
  `RELEASE_IMMUTABLE_TUPLE` clears; CHANGELOG `[Unreleased]` summary. Tagging/publishing needs explicit owner approval.
- Independent review (separate session): read-only verdict on P1–P5 diff, findings → one owning fix, re-review only findings.

## Pitfalls learned (do not repeat)

- Never mass-rewrite sealed evidence (`plans/**`, journals, bundles, `releases/*.json`): digests break. Remove or leave.
- `rm -rf` is blocked by the safety hook; use `git rm`, `git rm --cached`, `find … -delete` on proven-empty dirs only.
- Bare `git stash` touches the whole repo and a shared stash stack; use a WIP commit or a throwaway worktree.
- Tests that pin sha256 of text with paths (maind D108/D115) and digest-bearing generated docs must be regenerated, not hand-edited.
- Generated files are never hand-edited: change the canonical source, then run its generator and its `--check`.
- Quiet baselines: record failing tests before each phase; claim “no regression” only against that list.

## Launch prompt (paste into the new session, repo root)

```text
Execute tasks/2026.10.02-productization-cleanup/README.md end to end: phases P1→P5, owner decisions are final.
Start by recording baseline failures per package. Do not rewrite sealed plan evidence. Review once per phase
(read-only, separate pass). Do not commit, tag or publish without my explicit approval.
```
