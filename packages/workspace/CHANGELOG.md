# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **New module `workspace` (0.1.0, `development`, `destination: hub`):** `swissknifeman workspace init|status|doctor` and `project attach|list|show|scan|rebind|detach` over the places, documents, bindings and resolver of `aicore.workspace` (ADR 0085). `init` creates the layout, the git repository (`main`, first commit with a `Workspace-Device` trailer) and the device file; a repeat is a no-op and a non-empty folder is `WORKSPACE_ROOT_NOT_EMPTY`. `attach` identifies a checkout by its marker, else by matching remotes (never by name; `ATTACH_CONFIRM_REQUIRED` without `--yes` and a terminal, `PROJECT_AMBIGUOUS` for several matches), writes the marker without committing it and binds the checkout. `doctor` returns `check-result/v1` documents.
- **Configuration `[workspace]`:** `publish.max_tracked_bytes`, `publish.max_binary_tracked_bytes`, `git.lock_timeout_s`, `plans_migrator`.
- **Events** `workspace.root.initialized` and `workspace.project.attached` with data schemas in `schemas/event-data/v1`; the extension point `plans-migrator`.
