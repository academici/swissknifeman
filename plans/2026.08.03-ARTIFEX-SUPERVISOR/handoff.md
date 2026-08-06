# HANDOFF — 2026-08-06 — after P5.2

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — design-class rule conflict + frozen-contract version bump |
| Context | NEW SESSION — шаг-не-item (`plan-design` reads the plan from disk) |
| Суть | Resolve the P5.2 rule conflict (successor-package mutation authority) and the Claude Code `2.1.222`→`2.1.223` pin drift, then re-open P5.2 with an updated Scope/Validation. |
| Команда | `/task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P5.2` |

**Done:** P5.5 G2B manifests are committed at `33bf5b0a`; D117 voided D114–D116; D118 delegated
the bridge architecture (package-owned, reusing existing business argv/fold/activity/worker
primitives) — see D117/D118 in `plan.md` §5. P5.2's D118 seam is now implemented and unit-tested
at commit `c9e580ba`: `activity.BusinessProviderActivityPort.run()` composes
`build_business_argv`/`worker.run`/`fold_records`|`fold_business_records` exactly once per
admission; the new CLI subcommand `dispatch-business-intent` is the sole intent-issuing entry
point; `dispatch-business` stays validate-only (`intent_written:False`). Package suite: 89/89
tests green (`bash packages/artifex/scripts/test.sh`); `packages/artifex/scripts/validate.sh`
green (its `rg`-based guard silently no-ops — `rg` is not installed here; manually reproduced
with `grep`, 0 matches, package runtime does not import plan-local paths). `run-pilot.py` is
rewritten as a thin caller (Git worktree lifecycle + whole-batch preflight only).

**Remaining:** P5.2 is `🔴 Blocked` with two documented facts, zero D105 admissions spent, zero
provider intent issued:
1. **Rule conflict (primary trigger).** Editing `packages/artifex/lib/artifex/{cli.py,activity.py}`
   — required by P5.2's own Scope Included (D118 package-owned seam) — makes P5.5's own
   `validate-business-successor.py` report `G2B generation/assurance drift`, because the frozen
   `business-successor-generation-v1.json`/`business-successor-assurance-v1.json` package-file
   hashes no longer match current bytes. But the P5 phase contract's Границы reserves "only P5.5
   may mutate exact successor package/contract/assurance paths" — P5.2 has no authority to
   refresh those P5.5-owned artifacts. `plan-design` must pick one: (a) grant P5.2 authority to
   re-freeze P5.5's generation/assurance manifests as part of its own gate, or (b) reopen P5.5 to
   own the seam bytes so P5.2 stays a pure consumer.
2. **Provider version drift.** Installed `claude --version` → `2.1.223 (Claude Code)`; the frozen
   `business-dispatch-admission-v1@1.0.0` contract, `provider-business-projection-v1.json` and
   `providers/claude_code.BUSINESS_VERSION` all pin exactly `2.1.222 (Claude Code)` (Codex
   `codex-cli 0.146.0` still matches). `plan-design` must either bump the pin under a new
   owner-authorized D#, or arrange to run against `2.1.222`.

Once both are resolved, `run-pilot.py --slice <id> --results artifacts/P5/repository-pilot-
results-v1.json` can execute the three P5.2 admissions in catalog order, and
`validate-repository-pilot.py`/`findings/P5-repository-pilot.md` (not yet written — no live
evidence exists) become producible.

**Sources of truth:** `phases/P5.md` P5.2 (blockquote + Completion Notes/Pending Work carry the
full escalation) · commit `c9e580ba` (seam code + tests) · `packages/artifex/lib/artifex/
activity.py` (`BusinessProviderActivityPort.run`) · `packages/artifex/lib/artifex/cli.py`
(`dispatch-business-intent`) · `plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/run-pilot.py` ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/validate-business-successor.py` (rerun to
reproduce the drift) · `plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-successor-
generation-v1.json`/`business-successor-assurance-v1.json` (P5.5-frozen, now stale against
current package bytes).

**Open risks:** The repository working tree carries substantial unrelated uncommitted/untracked
changes across many other packages (skiller/harness/task/core/docs, plus untracked
`.p4-d99.0X38VL/`, `.swissknife.json`, `core/provider/runtime.py`,
`packages/skiller/skills/dart/`, `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/`) — foreign diff,
not touched by this item, but it also means `run-pilot.py`'s own `MAIN_TREE_DIRTY` preflight gate
will refuse for a second, independent reason until that state is committed/cleared by its owner.
Any future pilot attempt must re-verify main-tree cleanliness at that time, not assume today's
state.

**Workarounds/Deferred/Open questions:**

- workarounds: none — the escalation is a genuine authority-boundary/version-drift stop, not
  worked around.
- deferred: P5.2 live pilot execution, P5.3–P5.4, P6, and the pre-existing unrelated dirty-tree
  state (owner's, not this item's).
- open_questions: — (raised as the two escalation facts above; resolution is `plan-design`'s).
