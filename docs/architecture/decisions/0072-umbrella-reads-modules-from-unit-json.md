# ADR 0072: The umbrella CLI reads modules from unit.json; aliases are data

## Status

Accepted

## Context

`bin/swissknifeman` was a bash script with a fixed list of launchers and groups. A new module needed a code change in the
root, and the root knew module ids.

## Decision

- **Thin launcher.** `bin/swissknifeman` runs the development-clone guard and `scripts/umbrella.py`. The Python part uses
  the standard library and `aicore` only.
- **Discovery.** Modules come from `aicore.ext.units.discover_units`; `SKM_UNITS_PATH` defaults to `packages` and
  `bridges`. A module with `provides.cli` is a command group of its own id.
- **Aliases are data.** The former groups (`skills`, `env`, `wf`, `release`, `release-fleet`, `hub`, `config`, `setup`,
  `status`, `conformance`) and the legacy skiller verbs live in `configs/umbrella.json` (`umbrella-config/v1`, schema
  `configs/umbrella.schema.json`) as ordered routes with optional conditions. The only place with module ids in the hub is
  this data file.
- **Built-ins.** `units`, `install`, `doctor`, `help` and `-V`; the help text is generated from the units and the aliases.
- **Compatibility.** Every former group and legacy verb keeps working; the changed help is recorded as a golden case with
  a reason.

## Alternatives considered

- A plugin directory of subcommands: rejected, `unit.json` already declares the CLI of a module.
- Keeping the bash list: rejected, each new module would edit the root.
- Module ids in the umbrella code: rejected, the composition root must not know the modules it composes.

## Consequences

- A new module with `provides.cli` is a command with no change in the hub.
- Routes of an alias can name a module that is not installed; the launcher then reports a missing launcher (exit 1).

## Supersedes

None.
