# ADR 0050: Skiller settings live in the layered project config

## Status

Accepted

## Context

`skiller` kept the skill selection in `.swissknife.json` (shared with other modules) and the vendor mode in
`.swissknifeman/config.json`. The layered configuration ([ADR 0034](0034-layered-config-semantics.md)) gives every
module a section of `.swissknifeman/config.toml`, and live projects still have the older files.

## Decision

- **Two tables.** `[skiller]` holds the selection for `connect` and the legacy `vendor` (`project_type`, `buckets`,
  `plugins`, `exclude`, `presets`, `agent`, `skills_path`); `[skiller.sync]` holds the vendor mode (`agent`,
  `skills_path`, `presets`, `include`, `buckets`, `exclude`, `gitignore_managed`). The schema is
  `configs/config.schema.json`; the machine file cannot set these keys.
- **Legacy files by section.** `.swissknife.json` (skiller keys only) and `.swissknifeman/config.json` fill the
  matching section when `config.toml` sets none of its keys, with the warning `SKILLER_LEGACY_CONFIG`. If the table
  exists, the legacy keys are ignored with `SKILLER_LEGACY_IGNORED`. Writes go to the file the section is read from;
  new projects get TOML.
- **Unchanged.** `.swissknifeman-manifest.json` and `skills-lock.json` stay where they are because committed skill
  copies depend on them; keys of other modules in `.swissknife.json` are not touched. Backups of skiller use
  `aicore.state` instead of `*.bak`.

## Alternatives considered

- The legacy file as an extra layer merged key by key: rejected, the old file would win over the new TOML key by key,
  which is hard to follow for a person who started to move settings.
- Moving every service file at once: rejected, it breaks the committed copies and writers owned by later stages.

## Consequences

- Until the upgrade stage a project may have two files; the one that is not read is reported.
- Moving the values is done by `swissknifeman upgrade`.

## Supersedes

None.
