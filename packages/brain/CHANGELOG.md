# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Plugin and skill:** the Claude Code plugin `brain` (`.claude-plugin/plugin.json`, `provides.plugins`) delivers the skill `brain-locator` 0.2.0, moved from the `system` bucket of `skiller`; its path ladder starts with `brain vault --json`.
- **`scripts/cache-brain-docs.sh`**, moved from `maind`; `maind` is taken from `$MAIND_BIN` or `PATH`.
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
- **Document sync:** `brain docs integrate|pull|push|script --project DIR`, moved from `skiller`. `pull` copies vault
  files matching `docs.patterns` into the project and only adds or updates; `push` copies project files into the
  vault and leaves a vault file with different content alone (`DOCS_CONFLICT`, exit 1) unless `--force`; `integrate`
  is the `skiller integrate` block (pull for `pull` and `bidirectional`, then `.claude/sync-brain.sh`), and
  `--dry-run` writes nothing. A `memory_brain` object in `.swissknife.json` still turns sync on (with a deprecation
  warning); a plain string does not. Nothing is ever deleted. The generated `sync-brain.sh` also matches a file
  directly below the folder for patterns such as `docs/**/*.md`, like the Python copy.
