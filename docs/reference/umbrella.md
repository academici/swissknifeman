# Umbrella CLI

`swissknifeman` is one entry over the independent CLIs of the modules. `bin/swissknifeman` is a thin launcher
(development-clone guard, then `scripts/umbrella.py`). The umbrella holds no module logic and no module ids: it reads the
modules from their `unit.json` and the aliases from data ([ADR 0072](../architecture/decisions/0072-umbrella-reads-modules-from-unit-json.md)).

## How a command is resolved

The first word is tried in this order:

1. A built-in command: `units`, `install`, `doctor`, `help`, `-V`.
2. An alias of `configs/umbrella.json` (`umbrella-config/v1`): the former groups and the legacy skiller verbs.
3. A module id with `provides.cli` in its `unit.json`: the rest of the arguments go to that CLI.
4. Anything else: `Unknown command`, the help text, exit 1.

Modules are found with `aicore.ext.units.discover_units`; `SKM_UNITS_PATH` (separated by `os.pathsep`) defaults to
`packages` and `bridges` of the hub. Bridges are listed by `units`, but their scripts are not command groups.

## Built-in commands

| Command | Purpose |
| --- | --- |
| `swissknifeman units [list\|show <id>] [--json]` | modules found by `unit.json`; `--json` prints `umbrella-units/v1` |
| `swissknifeman install [--profile P \| --units a,b] [--bin-dir DIR] [--force] [--dry-run] [--json]` | see [install profiles](../install-profiles.md) |
| `swissknifeman doctor [--unit ID] [--category C] [--json] [--timeout S]` | see [doctor](doctor.md) |
| `swissknifeman -V`, `--version`, `version` | `git describe --tags` of the hub; a fallback file when there is no tag |
| `swissknifeman help`, `-h`, `--help` | generated help: built-ins, aliases, modules |

## Aliases

Aliases are data. Each alias has `routes`; the first route whose `when` matches wins, a route without `when` always
matches. A route names a module (`unit`) or a hub script (`script`), an optional `argv_prefix` and `drop_first`.

| Alias | Goes to |
| --- | --- |
| `skills` | skiller |
| `env` | harness |
| `wf` | `harness wf` |
| `release` | `release bundle ...` → `aicore release bundle` (see [release bundle](release-bundle.md)); other words → `skiller release` |
| `release-fleet` | `scripts/release-fleet.sh` |
| `conformance` | `plugin <extension.json>` → `aicore ext conformance`; `engine` → `orch conformance` (see [conformance](conformance.md)) |
| `hub` | maind |
| `config` | `aicore config` |
| `setup` | `--machine` → `scripts/bootstrap-machine.sh`; otherwise `maind onboard` |
| `status` | `--all`, `--namespace`, `--project` → `maind projects status`; none or another flag → `skiller status`; a word → `maind projects status --project` |
| `connect`, `vendor`, `integrate`, `update`, `init`, `sync`, `lock`, `list`, `registry`, `topology` | the verb of the same name of skiller |

An alias whose routes all have a condition that the arguments miss is a usage error (exit 2) that names the accepted words.

## Adding a module

A new module with `provides.cli` in its `unit.json` is a command group the moment it is found: no umbrella code or
configuration changes. A new alias is a new key in `configs/umbrella.json`, checked against `configs/umbrella.schema.json`.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | unknown command, failed install or doctor `fail`, missing launcher |
| 2 | usage error: bad arguments, unknown module (`UNIT_UNKNOWN`) or profile |

A command that resolves to a module CLI or script returns that program's exit code.

## Contracts

`umbrella-config/v1` (aliases), `umbrella-units/v1` (output of `units --json`), `umbrella-doctor/v1`, `umbrella-install/v1`
and `install-profiles/v1` are listed in [contracts](../architecture/contracts.md).
