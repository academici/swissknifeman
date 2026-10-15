# Quickstart: orchestrating a real project

What you need, what a run changes in your repository, and the few switches that matter. The full reference is [conductor.md](conductor.md).

## Before the first run
- `python3` (stdlib only) and the CLI of at least the executor provider on `PATH` (`claude` for the default route; `codex` and `grok` are optional routes). Check what a run would use, without starting anything: `conduct.py run … --dry-run` prints every route with `available` and the isolation flags.
- A git repository with a **clean working tree**: a run refuses to start on a dirty tree (`run --adopt` takes over an earlier attempt on purpose). Every finished piece becomes one commit.
- The `orch` and `aicore` packages reachable (`SKM_ORCH_ROOT`, `AICORE_ROOT` when they are not on `PATH`). `run --input` uses the built-in file source and needs no work-source configuration; plan runs need the work source of your planner registered in the machine config (`[orch] work_source`).

## Run
```text
# a piece of work that is not in a plan
orch.py input adhoc --goal "…" --include path/ --check V1="python3 -m unittest" > input.json
conduct.py --project /path/to/project run --input input.json --commit

# pieces of a plan: ONE run per group of related pieces, they share one executor session
conduct.py --project /path/to/project run --plan PLAN --items A B C   # one batch: all in progress, one executor session; --no-batch to separate
conduct.py status        # what runs now, the latest beacon
conduct.py observe --follow
conduct.py resume --run RUN [--retry ITEM]   # after a stop
```
`--project` is the repository the run works in; the orchestrator code can live elsewhere (and should be a frozen copy when the run changes `orch` itself).

## What the run touches
- Product files of the piece and one commit per piece, made by the conductor (the executor never commits).
- Run state and logs: `.swissknifeman/state/orch/conductor/<run>/` (streams of every role, prompts, reports, `options.json`) and the report of the observer `.swissknifeman/orch/reports/<run>/observer.md`. The state folder is gitignored; keep your own notes outside `/tmp`.

## Switches (all optional; later layers win: machine config < plan/phase/item options < `--options FILE` < flags)
| What | Switch | Default |
|---|---|---|
| Where the executor may write | `--fence project|plan`, `--allow-path DIR` (repeatable) | `project`: any file of the project; paths outside the plan's write set are reported as deviations. `plan` makes the write set a fence. `--allow-path` adds directories outside the project. |
| Executor session | `--batch` / `--no-batch` (`[orch.conductor] session_executor`) | `--batch`: all pieces of the run in progress at once and one session (`claude --resume`); `--no-batch`: one at a time, a fresh session each |
| Review | `review.*` in `--options` (`reviewer`, rounds, dynamic) | see conductor.md; set it per piece on purpose |
| Limits and beacons | `limits.*` | nothing is stopped for being long; beacons tell what runs |
| Instructions seen by roles | `instructions.isolate_roles`, `module_rules` | every role starts without the project instructions and gets only its prompt and a short Repository rules block |

## When something stops
`conduct.py status` names the piece and the code. `BLOCKED` pieces carry an `escalation` in the report; fix the cause and `resume --retry ITEM`. A run never discards the work of a role: a half-done piece stays in the tree and continues on `resume`.
