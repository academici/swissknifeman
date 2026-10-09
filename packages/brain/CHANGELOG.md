# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Module skeleton:** `unit.json` (version 0.1.0), `bin/brain` launcher with the development-clone guard and the
  `aicore` locator, `lib/brain` package, `scripts/test.sh` and `scripts/validate.sh`.
- **Vault lookup:** `brain vault [--json] [--project DIR]` walks the ladder `brain.vault_path` of the configuration,
  the deprecated `memory_brain` object of `.swissknife.json`, the deprecated `MAIND_BRAIN_VAULT` variable and
  `~/Vaults/Brain` (only with an `.obsidian` folder). A configured path that does not exist is `VAULT_MISSING`.
- **Project folder:** `brain project` finds the vault folder of a project through `<vault>/.projects.json` or the
  control notes (`repo:` frontmatter) under `catalog.projects_dir`.
- **Configuration:** the `[brain]` table (`vault_path`, `catalog.projects_dir`, `docs.*`, `notes.*`) with a schema and
  a generated `config.example.toml`; `vault_path` and `notes.fallback_folder` are machine-wide, a `notes.folder` inside
  `docs`, `docs-public` or `plans` is refused (`CONFIG_NOTES_FOLDER`).
- **Doctor:** `brain doctor [--json]` reports `brain.vault`, `brain.config` and `brain.notes-folder` as
  `check-result/v1`; a machine without a vault is a warning, not a failure.
