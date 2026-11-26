# Subagents and dev-loop — {{PACK_PREFIX}} (Python backend)

Stack: Python {{WEB_FRAMEWORK}}, manager `{{PKG_MANAGER}}`, binary `{{PY_BIN}}`.

## Roles (`.claude/agents/{{PACK_PREFIX}}-*.md`)

| Role | When | Tools |
|:--|:--|:--|
| `slice-builder` | endpoint slice (router→service→repo→diagram) | Edit/Write |
| `test-writer` | pytest according to the finished code until green | Edit/Write |
| `type-checker` | narrow mypy-diff pass + annotation clauses | read-only |
| `reviewer` | read-only: ruff/mypy, layers, security | read-only |
| `spec-writer` (opt.) | tech-spec before the large module | Write(docs) |
| `orchestrator` (from `_common`) | plan Task→@role | read-only |

## dev-loop

`.claude/workflows/{{PACK_PREFIX}}-dev-loop.js` — impl→tests-to-green→type-check→review on
one thread. The scope of slices is specified by a person via `args.slices` (`{id,title,goal,
acceptance_criteria,skills?,risk?}`). `risk` (`LOW|MED|HIGH`) → Lean-tiering: impl
`LOW→haiku` otherwise `sonnet`, review `LOW→sonnet · MED→opus/high · HIGH→opus/xhigh`,
type-check `sonnet`. No `risk` → default `MED`; review goes on `risk_level`, which returned
test-writer.

## Gates

- **SubagentStop** → `review-gate.sh` (`{{CHECK_CMD}}`).
- **PostToolUse** (Edit/Write `*.py`) → `validate-python.sh`: advisory ruff →
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

Bucket `python` subtle: framework canon and pytest — in agent prompts and `rules/`.
