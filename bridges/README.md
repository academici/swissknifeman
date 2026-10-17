# Bridges

A bridge is the only place where two modules know each other. It is a unit of the hub: `bridges/<id>/unit.json`
(kind `bridge`, destination `hub`, `requires` for both sides and the foundation, a `protocol` range and `dev.test`),
its own `README.md`, `scripts/test.sh` and `tests/`. `python3 scripts/ecosystem-units.py check` validates the units
and scans the bridge code for imports of partner packages and for the paths of other modules.

| Bridge | Between | Verbs / content |
| --- | --- | --- |
| [`planner-orch`](planner-orch/README.md) | planner ↔ orch | `brief`, `register`, `register-review`, `commit`, `launch` (`plan.py bridge planner-orch <verb>`) |
| [`orch-skiller`](orch-skiller/README.md) | orch ↔ skiller | `resolve_role.py`: the skill closure of a role and the skill delivery mode |
| [`orch-harness`](orch-harness/README.md) | orch ↔ harness | conformance of the role manifests with the agent-pack role catalog |
| [`gui-hub`](gui-hub/README.md) | gui ↔ hub | GUI queries (fleet, control-surface layers, doctor, units) and commands (`doctor`, `sync <cap>`) over the hub command line |
| [`gui-orch`](gui-orch/README.md) | gui ↔ orch | GUI queries (conductor runs, run status, items, observer report, questions, provider sandbox) and commands (run the ready pieces of a plan, resume, release) over the orch command line |
| [`workspace-planner`](workspace-planner/README.md) | workspace ↔ planner | port `workspace:plans-migrator`: `inspect`, `apply` (critical section of the plans migration under `PlanLock`), `verify` (plugin `migrator.py`) |
| [`gui-planner`](gui-planner/README.md) | gui ↔ planner | GUI queries (plans, overview, phases, board, dependency graph, items, decisions, evidence, timeline, raw documents, edit forms, model picker) and commands (item and phase edits, decide, reopen, grant, log) over the planner command line |

## Finding the partners

A bridge never looks at a neighbouring folder. Each partner is found by an explicit environment variable, then by a
command on `PATH`:

| Partner | Variable | Command |
| --- | --- | --- |
| planner | `PLANNER_PLAN_PY` (the file) or `PLANNER_ROOT` | `planner` |
| orch | `SKM_ORCH_ROOT` | `orch` |
| workspace | `SKM_WORKSPACE_MODULE_ROOT` (the folder of the module) | the hub behind `swissknifeman` |
| skiller | `SKM_SKILLER_ROOT` | `skiller` |
| harness | `SKM_HARNESS_ROOT` (tests only) | |
| gui | `SKM_GUI_ROOT` (tests only) | the hub registry (`swissknifeman units list --json`) |
| hub | `SKM_UMBRELLA` | `swissknifeman` |

A partner that is not found gives `BRIDGE_PARTNER_UNAVAILABLE: <partner> not found (set <VAR>)` on stderr with exit 3
(the conformance tests are skipped). The foundation is found by `AICORE_ROOT`, then `_vendor/aicore` inside the bridge,
then `packages/aicore` of the hub that holds the bridge; otherwise `AICORE_NOT_FOUND` with exit 2. The planner
dispatcher passes `PLANNER_ROOT`, `PLANNER_PLAN_PY`, `PYTHONPATH` and `AICORE_ROOT` to the bridges it runs.

## Tests

`bash scripts/test-bridges.sh` runs `dev.test` of every bridge with the partners wired from the hub layout, a temporary
`HOME` and event delivery off, and prints `bridges: OK`. The planner finds `bridges/` of this repository through
`bridges.roots` in `.swissknifeman/config.toml`.
