# Subagents and dev-loop — {{PACK_PREFIX}} (Flutter/Dart)

Stack: Flutter/Dart, target {{TARGET_KIND}}, state {{STATE_MGMT}}; FFI: see `rules/ffi.md`.

## Roles (`.claude/agents/{{PACK_PREFIX}}-*.md`)

| Role | When | Tools |
|:--|:--|:--|
| `slice-builder` | vertical screen slice (screen→widgets→state→repo) | Edit/Write |
| `test-writer` | flutter-tests (widget+unit/golden) to green | Edit/Write |
| `reviewer` | read-only: analyze/format, state, dispose, POS-embedded | read-only |
| `ffi-reviewer` (opt.) | narrow review FFI/native border (memory/ABI/isolate) | read-only |
| `spec-writer` (opt.) | tech-spec before a major feature/peripheral integration | Write(docs) |
| `orchestrator` (from `_common`) | plan Task→@role for a large task | read-only |

## dev-loop

`.claude/workflows/{{PACK_PREFIX}}-dev-loop.js` — impl→tests-to-green→review on the same branch.
The slice scope is specified by a person via `args.slices` (`{id,title,goal,acceptance_criteria,
skills?,risk?}`). `risk` (`LOW|MED|HIGH`) → Lean-tiering: impl `LOW→haiku` otherwise `sonnet`,
review `LOW→sonnet · MED→opus/high · HIGH→opus/xhigh`. No `risk` → default `MED`; depth/
model review - by `risk_level`, which returned test-writer.

## Gates

- **SubagentStop** → `review-gate.sh` (`{{CHECK_CMD}}`, mode in `review-gate.env.ini`).
- **PostToolUse** (Edit/Write `*.dart`) → `validate-flutter.sh`: advisory `dart analyze` →
  additionalContext, does NOT block.

## Lessons overnight-run (are hardwired into workflow — observe and manually)

1. **One branch for run**, hard-cap slices literal (`DEFAULT_MAX`) — is worried resume;
   circuit-breaker: 2 non-green in a row → stop.
2. **Model/effort — by RISK, not by default.** Cheap ones execute, expensive ones design/
   arbitrates (dashes above). Inheriting a parent model is a deliberate exception, not a default.
3. **Don't pollute background agents** — notification arrives automatically; polling cycles / `ScheduleWakeup`
   burns the context cache in vain.
4. **Prompts are deterministic - for the sake of resume-cache**: none timestamp/random; model/effort-
   override — as a separate call parameter. In a big fan-out, log `budget.remaining()` after the wave.
5. **Parallel - only for independent files** (public thread = general tree).

Bucket `mobile` thin: architecture/state/FFI/POS live in agent prompts and `rules/`.
