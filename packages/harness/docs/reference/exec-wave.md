# Driver exec-waves

Command `harness run <PLAN-ID> <Pn>` removes manual startup ritual item'ov
`plan-protocol`: reads the phase queue, drives the worker **process** (not
`Agent`/`Task` tool — suppression AgentTool in a subprocess session is not
is playing), gives a verdict on each item'y and writes a log where
the worker physically could not. The driver does not make decisions - he produces.

## What it does

- **`plan_reader`** reads the execution queue of ONE phase: item'you're fine
  `## Phase Status`, terminal (`🟢`/`🟠`/`⛔`) excluded, for each
  remaining - route (`task.task_contract build`), value `Exec`, right
  driving. Drive right = `Exec` in `## 3. Routing` resolves to `run` (legacy
  `plan-exec`/`manual`/`plan-run` spellings included) and the item route resolves. Semantic `Next` for v1 and v2 is taken only from
  owner `handoff.md`; layout-v2 item-state contains only result fields and is not
  fallback-source orchestration.
- **`worker`** starts ONE item process `claude -p "/task:plan-run
  &lt;PLAN-ID&gt; &lt;Pn.m&gt;" --output-format json` under timeout (default 1800s),
  strictly one worker at a time (serial wave - parallel fan-out on
  common codebase does not start). Model selectors/effort are taken from
  `packages/task/configs/command-routing.json`.
- **`gate`** gives a verdict `GREEN`/`ATTENTION`/`RED` from four sources:
  run outcome class, `plan-lint --baseline --gate new`, git-topology
  closing (`<SHA to>..HEAD`), status/fields item'and after the run. Table
  «sign → verdict» total: any RED wins, unmatched set
  signs by itself RED (fail-safe).
- **`journal`** appends the line to `journal.jsonl` EXACTLY when the session
  worker did not reach close-protocol itself (timeout/transport/quota/error/
  routing-blocked/no-op) — successful self-close `/task:plan-run` not
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
| `--plans-root PATH` | directory where to look `<PLAN-ID>/plan.md` (default `<monorepo>/plans`) |
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
