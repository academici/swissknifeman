# `skiller analyze-run` — post-run run analysis

Deterministic parsing of what happened in the run (especially background
`dev-loop`), by JSONL-logs Claude Code — **without running agents and spending tokens**.
Replies to «where did the tokens go/time, where are the bottlenecks, what skills worked, and
how dead».

```bash
skiller analyze-run [--last | --session ID] [--project DIR] [--json] [--store]
```

- `--last` (default) — last run of the project; `--session ID` — specific.
- `--project DIR` — project (otherwise auto search up from CWD).
- `--json` — machine output (for scripts/future aggregation).
- `--store` — save JSON-report in `<project>/.claude/analyze/<session>.json`
  (hit the cross-session trend; `.claude/analyze/` should be added to `.gitignore`).

## What it shows

- **By agent:** fact tokens `in/out`, **cache-hit%** (`cache_read`), model,
  wall-clock, top tools, retrays, tool-errors - from the field `usage` transcript.
- **Skills:** active project set (`resolve_active_set`/`budget_for_set`) ×
  actually loaded (`Skill`-calls) → **effective** (loaded), **DEAD**
  (in set, 0 downloads → candidate remove or repair `description`-triggers,
  avg. `skiller eval --triggers`), loaded outside the set.
- **Runtime failures** (heuristic): `Rate limited` / `SingletonLock` / `API Error` and
  etc. - noticeably in the end.

## Data source

`~/.claude/projects/<slug>/<session>.jsonl` (main) + `<slug>/<session>/subagents/
agent-*.jsonl`, where `<slug>` = absolute project path with `/`→`-`. Same resolve path,
what is the skill `system/session-observer`.

## Fair restrictions

- **Partial skill loading detection:** only explicit ones are visible `Skill`-tool-calls;
  native `skills:`-preload subagent and auto-trigger plugin by `description` like
  Skill-call **are not visible** → «DEAD» is heuristic.
- **Residence tier-0** (name+description in every request) in `usage` is not highlighted
  separate event - it's still a theory `skiller budget`. analyze-run believes
  FACT tokens in total and tier-1-downloads, but does not attribute tier-0 by skills.
- Runtime markers are heuristics: they can also catch mentions of phrases in the text of the task itself.
- Transcript scheme internal to Claude Code; parser is tolerant, but when changing
  format CC fields can go.

## Roles: analyze-run vs `session-observer`

Complement, do not compete:

| | `skiller analyze-run` | skill `system/session-observer` |
|---|---|---|
| How | deterministic CLI (Python) | agent-driven (jq-recipes + synthesis) |
| About what | **numbers**: tokens/timings/cache/dead skills | **why**: drift, skill-skip, loops, corrections |
| Cost | does not burn tokens | spends agent context |
| Exit | markdown + JSON | learnings in memory, promotion by man |

Practice: `analyze-run` — quick quantitative snapshot after task; if the numbers
highlighted the problem - `session-observer` for quality analysis «why».
