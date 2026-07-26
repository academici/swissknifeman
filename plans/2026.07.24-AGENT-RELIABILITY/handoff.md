# HANDOFF — 2026-07-26 — after P3.4

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/xhigh — fresh independent terminal reliability audit (`task:plan-audit`-class, no self-certification)

| Параметр | Значение |
|:--|:--|
| Model class | `frontier` |
| Effort | `xhigh` |
| Capabilities | `manual` |
| Context | `NEW SESSION — шаг-не-item` |
| Model | `gpt-5.6-sol` (Codex) or `opus`/`fable` (Claude) — per §3 Routing checked mapping, verified at cold-start preflight of whichever session executes it |
| Thinking | `xhigh` — fresh terminal adversarial verdict, no self-certification (Routing rationale) |
| Суть | P3.5: independent, read-only terminal reliability audit. Recompute exact hashes/metrics/cold runtime/canary evidence against frozen P0–P3; return GREEN, REMEDIATE or ROLLBACK under the existing two-audit-per-phase cap; P4 starts only on GREEN. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION recovery carrier for 2026.07.24-AGENT-RELIABILITY P3.5. Read AGENTS.md, CLAUDE.md and task:task-plan-run plus canonical plan-audit completely; run the canonical cold-start preflight. Read plan.md, roadmap.md, handoff.md, phases/P3.md and P3.5 Required Reads. Root delegates the read-only terminal audit to a fresh grounded frontier/xhigh subagent. Recompute exact hashes/metrics/cold runtime/canary cleanup; write only canonical audit/bookkeeping. Return GREEN, REMEDIATE or ROLLBACK under existing cap and continue to P4 only on GREEN.'
```

**Done:**

- **P3.4 закрыт 🟢 Done** (item-commit `cfd0e4ba`) — disposable-worktree self-host
  canary: `run_canary.py` (authored by this item, sole executable owner) dispatched
  the acting provider's headless CLI (Claude Code, this session) six times for real
  — routed axes pinned explicitly by flag per §3 Routing (`sonnet`/`high`,
  `--permission-mode bypassPermissions`, D46) — against the frozen six fixed cases
  (tiny control, plan/docs, provider publication, hook cold start, sequential
  multi-item root dispatch, intentional failure/recovery) in one disposable detached
  git worktree at `CANDIDATE_SHA=c1513dbb`.
- **6/6 cases passed** (12 real headless turns total), graded deterministically at
  the file/git level (diff scope vs `CANDIDATE_SHA` restricted to each case's
  declared allowlist, plus a per-case content check) — never by transcript
  self-report. Case 06 is the sharpest signal: attempt 1 correctly REFUSED to
  fabricate a sha256 for a missing input (wrote nothing); attempt 2 recovered with
  the exact independently-recomputed digest.
- **Rollback rehearsal** to `PRE_PLAN_SHA=7479972f` (`artifacts/P0.1/pre-plan-sha.txt`,
  D45) and back was clean both ways; frozen smoke = `py_compile` of
  `packages/task/lib/task/*.py` as it exists on the checked-out tree at call time +
  `task.plan_lint` import + a 0-error `plan-lint.py` run — all three passed.
- One **Unified Agent Trace v1** record per real dispatch
  (`canary-results.json::cases[].traces[]`, 12 records, `quality.completeness =
  0.667` each — `contract_ref`/`finding_refs` honestly null/empty with a reason).
- Six `case-NN-*.patch` files (`git diff --binary` against `CANDIDATE_SHA`) plus
  `canary-cases.json`/`canary-results.json`/`canary-manifest.json`/
  `canary-commits.json`/`findings/P3.4-canary.md` committed
  (`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.4/`).
- `plan.md` §0 Meta v1.16.9 → **1.17.0**; §4 Status Board P3 → `3/5`; §6 Update Log
  row; `phases/P3.md` Phase Status P3.4 → `🟢 Done`.
- **Known Deviations (process, both recorded in `phases/P3.md` P3.4):** (a) the
  rollback smoke definition was self-corrected mid-run — a first pass used `bash
  packages/task/scripts/validate.sh` and surfaced that historical commit's own
  pre-existing, unrelated journal-fixture/`test_provider_command_parity` test debt
  (not a rollback defect); `run_canary.py` was rewritten to grade only "the switch
  is clean and the old tree byte-compiles/lints", and only the rollback phase was
  re-run (the six case commits were not re-dispatched, no repeat real-provider
  cost) — a first draft of that fix itself computed paths from the wrong tree and
  was caught before the real re-run; (b) the disposable worktree's parent `mktemp`
  root directory could not be `rmdir`'d — the local harness auto-approve hook
  hard-denies `rm`/`rmdir`-shaped commands outside `safe-dirs.json`'s registered
  directories (`/tmp` is not registered) — `git worktree remove` itself succeeded
  and `git worktree list`/main-repo `git status --short` are both clean, which is
  what this item's Validation actually checks; the same class of leftover empty
  `/tmp` directories already exists for several other, unrelated worktrees in this
  repo's own `git worktree list` history.

**Remaining:**

- **P3.5** ⬜ — independent fresh terminal reliability audit (frontier/xhigh,
  `Exec = manual`, no self-certification). **P4** ⬜ waits for terminal, GREEN P3.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.17.0), §4 Status Board (P3 = `3/5`, `🟡 In progress`), §6
  Update Log.
- `phases/P3.md` — `## Phase Status` (P3.4 row `🟢 Done`), P3.4 item block
  (Completion Notes/Known Deviations carry the full record).
- `plans/2026.07.24-AGENT-RELIABILITY/findings/P3.4-canary.md` — full run narrative,
  the rollback-smoke correction rationale, and the six case-commit SHAs/patches.
- `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.4/canary-manifest.json` — exact
  provider/model/effort actually applied and their source (`cli-flag`), `cases_sha256`.
- `journal.jsonl` — this item's start/final pair (`plan-run`, `item_id=P3.4`).

**Open risks:**

- **Layer-2 (live paired) F6/F8/F9/F10 still have no live number wired into the P0.3
  bank's own floor evaluation.** P3.4 is that gap's actual live-dispatch producer
  (per P3.3's own Pending Work), but wiring these 12 real traces into
  `skiller.quality.eval`'s system-bank adapter as a graded layer-2 pass is a
  distinct future item, not silently assumed here.
- **`analyst`/`harness` package-API minor bumps still owed** (`0.1.0`→`0.2.0`,
  `0.3.0`→`0.4.0`, owed since P3.1/P3.2) — untouched again, `package.json` outside
  this item's `Files` too.
- **`skiller eval` CLI wiring for the system bank not added** — unchanged from
  P3.3's own Pending Work, out of this item's declared `Files`.
- **Predecessor items unchanged:** P0 phase-index row owner (`task:plan-close … P0`)
  and the P1.4 Update Log WARN remain open from earlier handoffs, untouched by P3.4.

**Workarounds / Deferred / Open questions:**

- **Rollback-smoke definition is now item-owned, not `validate.sh`.** Any future
  item touching `run_canary.py`'s `_smoke_steps` should preserve the tree-relative
  file resolution (confirmed via the 5-file-vs-8-file cross-check in
  `findings/P3.4-canary.md`) — the earlier draft silently used the wrong tree and
  would have reported a false-positive smoke pass on every rollback, not just the
  historical `validate.sh` one this item corrected away from.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md` compiler/enforcement seam
  description) — still owned by P3.1's original note; not touched by this item.
- **FOREMAN re-scope marker condition** — unchanged, both terminal-condition phases
  (P2.1, P3.1) are already terminal; owned by `2026.07.18-FOREMAN`'s own bookkeeping.
