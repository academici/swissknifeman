# ADR 0040: Extension configuration is a map table of the [aicore] section

## Status

Accepted

## Context

The configuration model of ADR 0034 allows only scalar leaves and arrays of scalars. Subscriptions, plugins and overlays
are entries named by the person (`subscriptions.<id>`, `plugins.<id>`, `overlays."<module>:<slot>"`). The project file is
committed to git, so it must not be able to start commands on a machine, the way a cloned repository cannot run git hooks.

## Decision

- **Map tables.** A config schema may declare an object with one anchored `patternProperties` key (names without dots)
  whose entries are a single leaf or a closed table of leaves. Entries merge by key across layers, take the leaf
  defaults, and work with `_unset` (an entry or one leaf), `_append`, `explain` and the generated
  `config.example.toml` (a commented sample entry). Environment variables cannot address entries (one warning).
- **A schema for aicore.** `[aicore]` has `events.{delivery, timeout_seconds, max_attempts}`, `subscriptions`,
  `plugins` and `overlays` (`packages/aicore/configs/config.schema.json`, `provides.config` of `unit.json`).
- **Machine-only definitions.** `run`, `plugin`, `manifest`, `trusted`, `on`, `projects` and timeouts carry
  `x-skm-layers` of defaults, machine, invocation and flags. A project file may switch an entry off (`enabled = false`)
  and add overlays. A subscription for one project is a `projects` filter in the machine file.
- **Module defaults.** A module declares default subscriptions in `unit.json` (`subscribes`, id `<module>:<name>`).

## Alternatives considered

- Array of tables `[[aicore.subscriptions]]`: rejected, one layer would replace the whole array and `explain` could not
  address an entry.
- Separate registration files outside `config.toml`: rejected, a second configuration mechanism next to `aicore.config`.

## Consequences

- One configuration for everything, with `explain` and layers working for extensions.
- A project can no longer define subscriptions; this narrows the idea of ADR 0006 that a project file may.
- Every module schema may now use map tables; the validator profile for them is ADR 0043.

## Supersedes

Refines ADR 0006.
