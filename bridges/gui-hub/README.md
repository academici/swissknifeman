# gui-hub

Bridge between the GUI host (`gui`) and the hub: the fleet of maind projects, the four control-surface layers of a
project, the doctor and the unit list as GUI views, and two hub commands. It is a hub unit (`unit.json`, kind `bridge`)
that contributes `gui.json` (`contribution/v1`) and answers through the aicore plugin protocol (`extension.json`,
points `gui:query` and `gui:command`).

The bridge only calls the hub command line (`$SKM_UMBRELLA`, else `swissknifeman` on `PATH`) and moves fields of its
JSON into `view-data/v1`; it computes no status, layer or fix of its own and imports no module.

| Query | Hub command | View |
| --- | --- | --- |
| `gui-hub.fleet` | `swissknifeman status --all --json` | `resource-list`: project, status, trusted, skills, agent packs, fixes |
| `gui-hub.fleet-summary` | `swissknifeman status --all --json` | `metric-group`: projects, connected, with fixes, memory daemon |
| `gui-hub.layers` | `swissknifeman status --all --json` | `status-table` of the project (matched by real path): skills, roles/agents, MCP, memory/graph (+ other) |
| `gui-hub.doctor` | `swissknifeman doctor --json` | `status-table`: one row per check |
| `gui-hub.units` | `swissknifeman units list --json` | `resource-list`: kind, version, stability, destination |

`fixes[].layer` lands in a layer by one table (`skills`, `agent-pack` → roles/agents, `mcp`, `memory`/`graph`/
`code-graph` → memory/graph, anything else → other). A layer row offers a repair (`gui-hub.sync` with its cap) only
when the fix is `maind sync ... --only <cap>` with a cap of the allowlist; any other fix stays text.

Commands (argv, run by the GUI broker):

| Command | argv | Notes |
| --- | --- | --- |
| `gui-hub.doctor-run` | `run.py doctor` → `swissknifeman doctor` | low risk, streamed, cancellable |
| `gui-hub.sync` | `run.py sync <cap> [--dry-run]` → `swissknifeman hub sync --project <maind id> --only <cap> [--dry-run]` | cap from the allowlist (`mcp`, `code-graph`, `graph`, `memory`, `memory-hook`, `health-hook`, `health-doc`, `feature-log-hook`, `ecosystem-skill`, `agent-pack`); the project is the working folder the broker chose; medium risk, confirmed unless a dry run |

`run.py` runs nothing else: another verb, an unknown cap or extra arguments exit 2; a working folder that is not a
maind project exits 2 with `PROJECT_NOT_IN_MAIND`. Failures of the hub command line are `HUB_UNAVAILABLE` and
`HUB_CLI_FAILED` with a short safe message.

## Tests

```bash
bash scripts/test.sh
```

The tests use a fake `swissknifeman` (`tests/fixtures/umbrella-*`) with canned answers. The GUI host and the
foundation are found by `SKM_GUI_ROOT` and `AICORE_ROOT`, else in the hub registry (`swissknifeman units list
--json`).
