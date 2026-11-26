# observer — capture-layer (PreToolUse / PostToolUse / Stop)

EXPERIMENTAL, per-project. Lightweight project-local session capture for post-hoc
skill parsing `system/session-observer`. Complements raw session-JSONL
(`~/.claude/projects/…`) calculated alerts (LOOP) and compact notation.

**Never blocks** — is an observer, not a gate (gate architecture -
`review-gate`). All events → `exit 0`.

## Enable (per-project, two steps)

1. **Flag:** `[harness.hooks.observer] enabled = true` in `.swissknifeman/config.toml` (carrier `OBSERVER_ENABLED=true` in `.swissknifeman/hooks.env`; the legacy `.claude/observer.env.ini` → `ENABLED=true` is still read; default `false` = no-op).
   Via Claude — `/observe on` (skill `system/session-observer`).
2. **Wiring** (opt-in, is not global - otherwise there is a hook for EVERY tool-call for everyone):
   ```
   harness hooks --target . --preset observer   # or apply-permissions --preset observer
   ```
   adds to `.claude/settings.local.json` hooks PreToolUse/PostToolUse/Stop →
   `~/.claude/hooks/observer/observer.sh`.

## What it says → `.claude/observer/`

| File | Contents |
|---|---|
| `runtime.jsonl` | thread PRE/POST by tool-call + alerts (`LOOP` at 3+ errors in a row) |
| `last_report.md` | summary on Stop (number of calls, alerts) |
| `archive/<ts>.jsonl` | log archive at the end of the session |
| `error_count` | service counter (resets to success/Stop) |

Catalog `.claude/observer/` — add to `.gitignore` project.

## Parsing

`/observe session` (skill `system/session-observer`) reads `runtime.jsonl` +
archive + session-JSONL + `git diff` → 3-axial weakness analytics
(agents/skills/settings) → learnings via memory-hook.
