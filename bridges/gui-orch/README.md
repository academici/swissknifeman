# gui-orch

Bridge between the GUI host (`gui`) and the orchestrator (`orch`): the conductor runs of a project, one run with its
items, the observer report, the open questions and the provider sandbox as GUI views, and three conductor commands. It
is a hub unit (`unit.json`, kind `bridge`) that contributes `gui.json` (`contribution/v1`) and answers through the aicore
plugin protocol (`extension.json`, points `gui:query` and `gui:command`).

The bridge only calls the orch command line (`$SKM_UMBRELLA orch ...`, else `swissknifeman` on `PATH`) in the project
folder and moves fields of its JSON into `view-data/v1`. It imports no module and does not read the state folder of the
orchestrator: the list of runs is `orch conduct runs --json`.

| Query | Orch command | View |
| --- | --- | --- |
| `gui-orch.runs` | `conduct runs --json` | `resource-list`: run, status, reason, started, items, resumes |
| `gui-orch.latest` | `conduct runs --json --limit 1` | `resource-list` with the newest run (dashboard widget) |
| `gui-orch.run` (`run_id`) | `conduct status --run R --json` | `resource-detail`: status, reason code, current stage, last line, tokens, stop; sections Items and Agents; action Resume |
| `gui-orch.items` (`run_id`) | `conduct status --run R --json` | `status-table`: one row per item (`done` ok, `done_with_deviations` warn, `blocked` fail, running warn) |
| `gui-orch.report` (`run_id`) | `conduct observe --run R` | `markdown`: `observer.md`, read only when its real path is `<project>/.swissknifeman/orch/reports/<run>/observer.md` |
| `gui-orch.questions` (`run_id` optional) | `conduct questions --json [--run R]` | `resource-list`: item, question, kind, state, age, overdue |
| `gui-orch.sandbox` | `doctor --json` | `status-table`: the `orch.*` checks (`orch.sandbox` first) and a row that says what the sandbox covers |

`run_id` must match `cnd-[0-9A-Za-z-]+` before the CLI is called. Routes (`/x/gui-orch/...`): `runs`, `runs/:run_id`,
`runs/:run_id/items`, `runs/:run_id/report`, `questions`, `sandbox`; dashboard widget `gui-orch.latest`. Counts, ages and
tokens are integers (the backend refuses floats).

**Sandbox caption.** "The provider sandbox restricts the commands of orch roles; GUI plugin processes are not sandboxed
(permissions are advisory)." The view shows the fact of `orch.sandbox`; it changes no enforcement of the GUI.

Commands (argv, run by the GUI broker in the project root through `run.py`; no shell):

| Command | `run.py` | Runs | Policy |
| --- | --- | --- | --- |
| `gui-orch.run-ready` | `run-ready --plan P --max-items N [--dry-run]` | `orch conduct run --plan P --ready --max-items N [--dry-run]` | risk high, always confirmed; effects `process.spawn`, `plan.write`, `project.write`; stream, cancel, dry-run |
| `gui-orch.resume` | `resume --run R` | `orch conduct resume --run R` | risk medium, confirmed by risk |
| `gui-orch.release` | `release --run R --item I` | `orch conduct release --run R --item I` | confirmed always |

One input value is one argv element (I4). The pieces of a plan are chosen by `--ready` and a count `1..20`, never by a
list in one string; `--dry-run` is a literal of the descriptor (`dry_run.argv_append`). `run.py` accepts exactly these
three forms and exits 2 for anything else without running orch.

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
