# ADR 0065: maind configuration is split into settings and a fleet registry; machine registries move

## Status

Accepted

## Context

The node file `config.json` of maind mixed what a person edits with what maind writes (projects, namespaces, agent
definitions, MCP servers). Machine registries were kept in `~/.swissknifeman` and `~/.maind`.

## Decision

- **Settings.** What maind only reads (`node`, `memory`, `graph`, `code_graph`, scalar `agents` keys, `integrations`,
  `mcp.emit_example`, `mcp.perplexity_web`, `observability`) is the `[maind]` table of the layered configuration;
  the schema is `packages/maind/configs/config.schema.json`.
- **Registry.** What maind writes (`projects`, `namespaces`, `agents.definitions`, `mcp.servers`, `providers`, `role_packs`) is
  `<state>/maind/registry.json` in the former shape, written only by `write_registry`. `Config.load` assembles the former
  dictionary from both.
- **Legacy.** The legacy node file (`config.json`, `.maind.json`) is read with one `MAIND_LEGACY_CONFIG` warning: its
  settings while no layer has `[maind]`, its registry while there is no `registry.json`; writes go to the active
  source. `~/.maind` moves to `<state>/maind` and `<module>/data` to `<data>/maind` through `resolve_with_legacy`;
  `.maind.graph.json` becomes `[maind.graph.links.<id>]` of the project (`MAIND_LEGACY_GRAPH_LINKS`); backups go through
  `aicore.state.backup`. The data of the memory daemon is not moved. Values move with `swissknifeman upgrade`.
- **Machine registries.** `maind topology show|init [--json]` keeps the map in `<state>/maind/topology.json` (legacy
  `~/.swissknifeman/topology.json`); `skiller topology` stays an alias with one `SKILLER_TOPOLOGY_MOVED` warning.
  The registry of connected projects stays with skiller, in `<state>/skiller/projects.json`, and `skiller list --json`
  (contract `projects-list/v1`) exposes it. The skills of maind read both through these commands.

## Alternatives considered

- One TOML file for everything: rejected, the registry is written by code and `toml_edit` cannot keep arrays of tables.
- Moving the registry of connected projects into maind: rejected, skiller owns the delivery that writes it.

## Consequences

- Settings follow the layers and `swissknifeman config explain`; the registry keeps one writer.
- Nothing is migrated silently.

## Supersedes

None.
