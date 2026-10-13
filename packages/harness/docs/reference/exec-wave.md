# Driver exec-waves

Command `harness run <PLAN-ID> <Pn>` removes manual startup ritual item'ov
`plan-protocol`: reads the phase queue, drives the worker **process** (not
`Agent`/`Task` tool — suppression AgentTool in a subprocess session is not
is playing), gives a verdict on each item'y and writes a log where
the worker physically could not. The driver does not make decisions - he produces.

## What it does

- **`plan_reader`** reads the execution queue of ONE phase through the planner plan API
  (`plan.py show <plan> <Pn>|<Pn.m> --json`, `plan.py next <plan> --json`): terminal items
  (`done`, `done_with_deviations`, `skipped`) are excluded; for each remaining item - route
  (`item.route`), status and drivability. An item is driven when the phase is `detailed`, the item
  is not `blocked` and its route resolves; otherwise the refusal is named (`PHASE-NOT-DETAILED`,
  `ITEM-BLOCKED`, `ROUTING-UNRESOLVED`). Semantic `next_form` is the plan's `next` step. Nothing
  parses plan Markdown.
- **`worker`** starts ONE item process `claude -p "/planner:plan-run
  &lt;PLAN-ID&gt; &lt;Pn.m&gt;" --output-format json` under timeout (default 1800s),
  strictly one worker at a time (serial wave - parallel fan-out on
  common codebase does not start). Model selectors/effort are taken from the aicore model
  catalog. The legacy driver finds the planner through `PLANNER_ROOT`, `SKM_TASK_ROOT` (deprecated,
  one warning), `PLANNER_PLAN_PY` or the `planner` command on `PATH` (never a neighbouring folder or the monorepo root); none
  found is `PLANNER_UNAVAILABLE`. The invocation template comes from the `aicore` model catalog, not from a planner file.
- **`gate`** gives a verdict `GREEN`/`ATTENTION`/`RED` from four sources:
  run outcome class, `plan.py check` (errors RED, warnings ATTENTION), git
  closing (`<SHA to>..HEAD` commits and the uncommitted remainder outside the plan directory),
  status/fields of the item JSON after the run. Table
  «sign → verdict» total: any RED wins, unmatched set
  signs by itself RED (fail-safe).
- **`journal`** appends a friction event (`plan.py log`: `blocker` for a refused launch,
  `difficulty` for a failed or idle run) EXACTLY when the session
  worker did not reach `plan.py finish` itself (timeout/transport/quota/error/
  routing-blocked/no-op) — successful self-close `/planner:plan-run` not
  duplicated (D32).

## Usage

```
harness run <PLAN-ID> <Pn> [--dry-run] [--limit N] [--timeout S]
                            [--plans-root PATH] [--json]
```

| Flag | Meaning |
|:--|:--|
| `--dry-run` | queue only/routes/accurate `argv`/reasons for failures - WITHOUT worker spawn and WITHOUT a single record (read-only) |
| `--limit N` | maximum item'ov waves (default - entire queue) |
| `--timeout S` | timeout for ONE worker run, seconds |
| `--plans-root PATH` | directory where to look `<PLAN-ID>/plan.json` (default `<monorepo>/plans`) |
| `--json` | same summary machine (`ensure_ascii=False`) |

Wave **serial** and stops at **first RED**; `ATTENTION` her
does not stop, but is included in the report by name. There is not a single shooting gallery in retrospect -
fallen item is waiting for the next manual start.

## What it DOESN'T do (closed list)

Decision machine `decide` · run-folder · retry-ladder of three shooting ranges ·
integration with instant messengers and remote-approve · package `packages/artifex` ·
rolling out agent-pack'ohm · second driver (`codex exec`) · unattended-profile
(`--permission-mode` — run policy remains the owner's environment) ·
parallel launch of workers.

## Acceptance

Live reception belongs to package tests and `bash packages/harness/scripts/validate.sh`:
v1/v2 plan-reader fixtures check route/Next boundaries, CLI dry-run — read-only,
a wave tests — stop-on-RED/continue-on-ATTENTION. Historical field runs remain
provenance, but do not replace current validators. Proportion of interventions with fixture-wave —
synthetic number; combat statistics are still accumulating durable log.
