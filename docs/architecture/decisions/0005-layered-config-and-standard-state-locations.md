# ADR 0005: Layered configuration and standard state locations

## Status

Accepted

## Context

Settings and service files are scattered: dot-files in projects, `*.env.ini`, `*.bak` next to files, registries in
several home directories, and machine settings inside the repository working copy.

## Decision

Configuration is layered: module defaults, machine, project, environment `SKM_<MODULE>_<KEY>`, flags. Each module
ships a schema for its section, and `config show --explain` reports the value and the layer it came from.
State follows XDG locations (`~/.config`, `~/.local/state`, `~/.local/share`, `~/.cache`); a project keeps
`.swissknifeman/{config, state/, backups/}`; `SKM_HOME` relocates everything for isolation. Old files move to the
new places by the table in the ecosystem document.

## Alternatives considered

- Keep per-module files and formats: rejected, machines and the dev clone would keep fighting over one file.

## Consequences

- Different computers are configured independently of the working copy.
- Provider surfaces (`.claude/settings*.json`, `.codex/config.toml`, and so on) stay with the providers and are
  written only through `aicore.artifacts` with a lock and a backup.
- The file format of the human-edited layers is refined by ADR 0011; merge semantics by ADR 0019.

## Supersedes

Refined by ADR 0011 (file format of the machine and project layers) and ADR 0019 (merge semantics).
