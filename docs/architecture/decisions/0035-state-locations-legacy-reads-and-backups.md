# ADR 0035: State locations, legacy reads and backups

## Status

Accepted

## Context

[ADR 0005](0005-layered-config-and-standard-state-locations.md) named the standard places. Modules wrote into
`~/.swissknifeman/<app>`, `*.bak` files next to the originals and a shared `config_paths` helper. Tests and sandboxes
must never read the real home, and a live installation must keep working before its files are moved.

## Decision

`aicore.state` resolves every place; it creates nothing except through `ensure_dir` (mode `0700`).

- **Machine places** (`machine_locations`, `config_dir`, `state_dir`, `data_dir`, `cache_dir`): `$XDG_CONFIG_HOME`,
  `$XDG_STATE_HOME`, `$XDG_DATA_HOME`, `$XDG_CACHE_HOME` with `/swissknifeman` appended and the usual defaults under
  `~`; a relative `XDG_*` value is ignored. A non-empty absolute `SKM_HOME` puts all four under
  `$SKM_HOME/{config,state,data,cache}`, marks the set `isolated` and switches off every legacy lookup; a relative
  `SKM_HOME` is an error. Tests: `tests/state/test_locations.py`.
- **Project places:** `<root>/.swissknifeman/{config.toml,state/,backups/}`; `find_project_root` takes the nearest
  ancestor holding `.swissknifeman/` or `.git`.
- **Legacy reads.** `resolve_with_legacy(new, legacy)` returns the new path when it exists, the new path when
  isolated, otherwise the first existing legacy path with one warning per process, otherwise the new path. It never
  copies or removes: reads and writes stay in one directory. Moving files is `swissknifeman upgrade`.
- **Backups.** `backup(path, project=...)` copies to `<project>/.swissknifeman/backups/<UTC stamp>/<relative path>` or,
  for machine files, to `<state>/backups/<stamp>/...`, keeps the newest ten stamps (`DEFAULT_KEEP`), and rotates only
  directories whose name is a stamp. Tests: `tests/state/test_backups.py`. Existing `backup_file` callers move with
  their modules.
- **Git policy.** `gitignore-policy.json` (moved from `configs/`, code in `aicore.state.gitignore`) commits
  `.swissknifeman/config.toml` and ignores `.swissknifeman/state/`; the `core` shim keeps the old module name.
- **Removal.** `core/config_paths.py` and `shared_config_path` are deleted; nothing replaces them.

## Alternatives considered

- Copy legacy files on first read: rejected, two writable copies diverge.
- Fixed `~/.swissknifeman` for everything: rejected, it ignores XDG and cannot isolate tests.

## Consequences

- A sandbox sets only `SKM_HOME` and cannot touch the real home.
- A warning, not an error, tells a person that a legacy location is still in use.

## Supersedes

Refines [ADR 0005](0005-layered-config-and-standard-state-locations.md).
