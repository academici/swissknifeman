# ADR 0049: Module skills reach projects through host-provided buckets

## Status

Accepted

## Context

The skills of the `system` bucket described modules (`maind`, `harness`, `analyst`, `brain`), so they moved into
those modules ([ADR 0008](0008-skills-live-in-their-module.md)). Project profiles and configs still name the bucket
`system`, and `vendor` and `sync` read only the `skills.json` of the library. `skiller` must not know the names of
other modules.

## Decision

- **Host-provided bucket.** `buckets.json` marks `system` with `"provided_by": "host"`: it has no catalog in the
  library. The host config `configs/skiller-host.json` maps it with `bucket_aliases` to the module plugins
  (`{"system": ["maind", "harness", "analyst", "brain"]}`); skiller reads their skills from the plugin directories
  named by `plugin_dirs`.
- **Both channels.** `connect` expands the bucket into the module plugins and replaces the old
  `system@swissknifeman` key (merge-only, an explicit `false` is respected). `vendor` and `sync` copy the module
  skills the same way as library skills; `requires` and `exclude` work by name. `budget`, `status`, `doctor`,
  `registry` and `validate` understand the bucket.
- **One plugin per module.** A module plugin carries its skills, commands and agents, and a Codex manifest when it has
  skills. The agent `code-coordinator` goes to `maind` together with `cross-project-coordinator`.
- **Standalone.** Without a host the bucket is empty and skiller only warns, so profiles and project configs do not
  change.

## Alternatives considered

- Module skills only through marketplace plugins: rejected, `vendor`, `sync` and Codex would lose them and profiles
  would have to name modules.
- Indexing module skills in the library `skills.json`: rejected, the library index would hold paths into other
  modules and differ between standalone and hub.

## Consequences

- Enabling the plugin of a module also brings its commands into the first turn of a project; the budget is measured
  with `skiller budget --first-turn --with-plugins`.
- Adding a skill to a module needs no change in `skiller`.

## Supersedes

None.
