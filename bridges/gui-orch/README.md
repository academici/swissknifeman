# gui-orch

Bridge between the GUI host (`gui`) and the orchestrator (`orch`): the conductor runs of a project, one run with its
items, recorded routes, prompt metadata, budgets, provider gates, the observer report, open questions and the provider
sandbox as GUI views, and the conductor commands below. It
is a hub unit (`unit.json`, kind `bridge`) that contributes `gui.json` (`contribution/v1`) and answers through the aicore
plugin protocol (`extension.json`, points `gui:query` and `gui:command`).

The bridge only calls the orch command line (`$SKM_UMBRELLA orch ...`, else `swissknifeman` on `PATH`) in the project
folder and moves fields of its JSON into `view-data/v1`. It uses aicore redaction and does not read the state folder of the
orchestrator: the list of runs is `orch conduct runs --json`.

| Query | Orch command | View |
| --- | --- | --- |
| `gui-orch.runs` | `conduct runs --json` | `resource-list`: run, view status, reason, started, items, resumes, live owner |
| `gui-orch.latest` | `conduct runs --json --limit 1` | `resource-list` with the newest run (dashboard widget) |
| `gui-orch.run` (`run_id`) | `conduct status --run R --json` | `resource-detail`: status, reason code, current stage, last line, tokens, stop; sections Items and Agents; action Resume |
| `gui-orch.items` (`run_id`) | `conduct status --run R --json` | `status-table`: one row per item (`done` ok, `done_with_deviations` warn, `blocked` fail, running warn) |
| `gui-orch.report` (`run_id`) | `conduct observe --run R` | `markdown`: `observer.md`, read only when its real path is `<project>/.swissknifeman/orch/reports/<run>/observer.md` |
| `gui-orch.questions` (`run_id` optional) | `conduct questions --json [--run R]` | `resource-list`: item, question, kind, state, age, overdue |
| `gui-orch.sandbox` | `doctor --json` | `status-table`: the `orch.*` checks (`orch.sandbox` first) and a row that says what the sandbox covers |
| `gui-orch.routes` (`run_id`, `item`) | `conduct status --run R --json`, `route explain --role ROLE --run R --item I --json` | `status-table`: separate labelled `used` and `available now` values in each role's detail |
| `gui-orch.prompt` (`run_id`, `item`, `step`) | `conduct prompt explain --run R --item I --step S --json` | `resource-detail`: kind, origin, tokens, 12-character digest, excluded kind/reason, core/supporting/retrieval totals; no prompt text |
| `gui-orch.budget` (`run_id`) | `conduct status --run R --json` | `metric-group`: fresh tokens against effective soft/hard item and hard run limits; incomplete usage warns |
| `gui-orch.gates` | `conduct gates --json` | `status-table`: active capacity gates, with a confirmed clear action |
| `gui-orch.timeline` (`run_id`, `item` optional) | `conduct timeline --run R [--item I] --json` | `timeline`: the steps as intervals, newest first, with status (`done`, `stopped`, `interrupted`, `open`), duration and end; an interrupted and resumed step is two entries, an open one has no end |

`run_id` must match `cnd-[0-9A-Za-z-]+` before the CLI is called. Routes (`/x/gui-orch/...`): `runs`, `runs/:run_id`,
`runs/:run_id/items`, `runs/:run_id/items/:item/routes`, `runs/:run_id/items/:item/prompt/:step`,
`runs/:run_id/budget`, `runs/:run_id/timeline`, `runs/:run_id/report`, `providers/gates`, `questions`, `sandbox`; dashboard widget `gui-orch.latest`. Counts, ages and
tokens are integers (the backend refuses floats).

Used routes come only from that run's recorded routing labels (`provider`, `model`, `effort`, `class`); current
configuration and gates affect only `available now`. Missing history is `unknown`. The host status-table has no
custom columns, so both values have explicit labels in `detail`. Launch argv and environment are never projected.
`step` must match `^[a-z][a-z0-9-]*(\.[0-9]+(-q[0-9]+)?)?$` at both the host and adapter boundary; orch also checks
the resolved manifest path stays inside the item's directory, rejecting symlink escapes with `PROMPT_PATH_INVALID`.
Legacy manifest exclusions have `id`/`reason`; their kind is `skill`, and the id is not displayed.

`orphaned` maps to `warn`, with `RUN_ORPHANED: no live conductor holds the run; resume continues it`.
Run detail shows both the raw state and its valid view status, and a live owner (pid, host, start, command).
Resume is offered for orphaned, stopped and blocked runs; a run that waits for an answer (`waiting`, shown as `warn`, with the waiting pieces and their questions) offers `continue`, not resume. A question that has an answer but is not continued yet is `answered — continue`. Budget metrics always have ids and numeric values;
`no limit` belongs in the label. Incomplete usage warns that totals may be understated and limits cannot see missing usage.

All diagnostic values pass through `aicore.util.redact.redact_text` before control/ANSI removal and shortening
(ids/labels 64, details 500). Observer markdown keeps its report size limit and is redacted before rendering.
The foundation is located via `AICORE_ROOT`, else the hub's `units list --json`, with no module path imports.

**Sandbox caption.** "The provider sandbox restricts the commands of orch roles; GUI plugin processes are not sandboxed
(permissions are advisory)." The view shows the fact of `orch.sandbox`; it changes no enforcement of the GUI.

Commands (argv, run by the GUI broker in the project root through `run.py`; no shell):

| Command | `run.py` | Runs | Policy |
| --- | --- | --- | --- |
| `gui-orch.run-ready` | `run-ready --plan P --max-items N [--dry-run]` | `orch conduct run --plan P --ready --max-items N --detach` (dry-run: `--dry-run`, without detach) | risk high, always confirmed; effects `process.spawn`, `plan.write`, `project.write`; stream, dry-run; timeout 120 s; detached from GUI |
| `gui-orch.resume` | `resume --run R [--retry I]` | `orch conduct resume --run R [--retry I] --detach` | risk medium, confirmed by risk |
| `gui-orch.continue` | `continue --run R` | `orch conduct continue --run R` | risk medium, confirmed by risk; effects `process.spawn`, `plan.write`, `project.write`; stream, cancel; exit code 4 is a run that waits again, not a failure |
| `gui-orch.answer` | `answer --run R --item I --question Q (--option ID \| --text T)` | `orch conduct answer --run R --item I --question Q (--option ID \| --text=T)` | risk medium, confirmed always; effects `process.spawn`, `project.write`; the text is one `--text=` element (a text that starts with `-` stays a value) |
| `gui-orch.release` | `release --run R --item I` | `orch conduct release --run R --item I` | confirmed always |
| `gui-orch.gates-clear` | `gates-clear --provider P` | `orch conduct gates --clear P` | confirmed always; provider enum `claude-code`, `codex`, `grok`; argv only |

One input value is one argv element (I4). The pieces of a plan are chosen by `--ready` and a count `1..20`, never by a
list in one string; `--dry-run` is a literal of the descriptor (`dry_run.argv_append`). `run.py` accepts exactly these
forms and exits 2 for anything else without running orch. Gate clearing never goes through the query handler.

Failures: `ORCH_UNAVAILABLE` (no hub command line), `ORCH_CLI_FAILED` (exit other than 0, not JSON, a timeout, or a report
path outside the reports folder), `ORCH_RUN_NOT_FOUND` (`RUN_UNKNOWN` of the CLI), `ORCH_CONTEXT_MISSING` (no project or
a malformed `run_id`). Messages pass through `safe_text`.

## Tests

```bash
bash scripts/test.sh
```

The tests use a fake `swissknifeman` (`tests/fixtures/umbrella-*`, data in `tests/fixtures/fake.py`). The GUI host and
the foundation are found by `SKM_GUI_ROOT` and `AICORE_ROOT`, else in the hub registry (`swissknifeman units list
--json`).

`run-ready` and `resume` set launcher `gui` and inject `--detach` after their existing argv checks. Users cannot pass
that flag through the bridge. All six existing verbs remain available; dry-run stays synchronous. Detached commands
return startup JSON within the 20-second acknowledgement deadline, have a 120-second broker timeout and do not offer
cancel. Their conductors continue after the GUI closes. `continue` and `answer` retain their existing behavior.

Run detail shows Health, Silent (s), Heartbeat age (s), Last beacon and Launcher from `orch conduct status --json`.
Health `hung`, `suspected_stall` and `orphaned` maps to `warn`; `waiting_*` maps to `info`. Missing older metadata is
shown as unknown or a dash. Run outcomes and the actions for resume/continue remain available.
