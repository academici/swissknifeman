# Subagents and dev-loop — {{PACK_PREFIX}} (Vue/Vite frontend)

This pack distributed subagent roles and serial workflow. Stack: Vue/Vite,
option {{VUE_VARIANT}}, manager `{{PKG_MANAGER}}`.

## Roles (`.claude/agents/{{PACK_PREFIX}}-*.md`)

| Role | When | Tools |
|:--|:--|:--|
| `component-builder` | one reusable UI-unit (SFC + composable) | Edit/Write |
| `slice-builder` | vertical page slice/features (route→page→store→api) | Edit/Write |
| `test-writer` | tests Vitest+test-utils according to the finished code until green | Edit/Write |
| `reviewer` | read-only review: tsc/eslint, types, structure, a11y | read-only |
| `spec-writer` (opt.) | tech-spec before a major multi-screen feature | Write(docs) |
| `orchestrator` (from `_common`) | breaking down a large task into a plan Task→@role | read-only |

## dev-loop

`.claude/workflows/{{PACK_PREFIX}}-dev-loop.js` — on ONE branch for each slice:
impl → tests-to-green → review-gate. The slice scope is set by a person:

```
args = { branch: 'feat/...', base: '{{BASE_BRANCH}}', max_slices: 3,
         slices: [ { id, title, goal, acceptance_criteria, skills?, risk? } ] }
```

`risk` slice (`LOW|MED|HIGH`) — hint for Lean-tiering: impl `LOW→haiku` otherwise `sonnet`,
review `LOW→sonnet · MED→opus/high · HIGH→opus/xhigh`. No `risk` → default `MED`. test-writer
returns its score `risk_level`, it determines the depth/model review.

## Gates

- **SubagentStop** → `review-gate.sh` (`REVIEW_GATE_MODE` in `.claude/review-gate.env.ini`):
  fast `{{CHECK_CMD}}`.
- **PostToolUse** (Edit/Write `*.ts|*.vue`) → `validate-frontend.sh`: advisory, injectitis
  errors tsc/eslint into context, does NOT block.

## Lessons overnight-run (are hardwired into workflow — observe and manually)

1. **One branch for run**, hard cap number of slices by literal (`DEFAULT_MAX`) — is worried
   resume; circuit-breaker: 2 non-green in a row → stop.
2. **Model/effort — by RISK, not by default.** Cheap ones execute, expensive ones design/
   arbitrates (dashes above). Inheriting a parent model is a deliberate exception, not a default.
3. **Don't pollute background agents** — completion notification comes automatically; polling cycles /
   `ScheduleWakeup` burns the context cache in vain.
4. **Prompts are deterministic - for the sake of resume-cache**: none timestamp/random; model/effort-
   override — as a separate call parameter (opts do not change completed stages). In the big
   fan-out log `budget.remaining()` after the wave.
5. **Parallel - only for independent files** (public thread = general tree).
