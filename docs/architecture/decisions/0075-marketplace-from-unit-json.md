# ADR 0075: The marketplace and the Codex index are assembled from unit.json

## Status

Accepted

## Context

skiller wrote the root marketplace and the Codex index and read the plugin folders of modules from a host configuration
(`plugin_dirs`). Adding a module plugin meant a change in skiller.

## Decision

- **Declaration.** `provides.plugins[]` of `unit/v1` has, next to `name`, exactly one of `manifest` (a `plugin.json`),
  `source` (a plugin folder) or `catalog` (a `plugin-catalog/v1` file for a module that ships several plugins).
- **Assembler.** `aicore.content.marketplace` builds `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`
  from the units. `aicore marketplace build --hub ROOT` writes them; `--check` reports drift (exit 1).
- **Catalog.** skiller describes its own plugins (buckets, aliases, `core`, `generate-skill`, `skm`) in
  `packages/skiller/.claude-plugin/catalog.json` and calls the assembler from `skiller registry`. `skills[]` paths of a
  catalog are relative to the module.
- **Bytes.** The generated files are unchanged, except the `package` of the `task` alias entry, which is now `planner`.
- `plugin_dirs` stays for module skills only.

## Alternatives considered

- Each module writes its own marketplace file: rejected, the root needs one index.
- Generating `plugin.json` from `unit.json` now: rejected, it would change the bytes of the hand-kept manifests.

## Consequences

- A module with a plugin declares it; the marketplace follows.
- A host that keeps plugin folders without `unit.json` loses their marketplace entries.

## Supersedes

None.
