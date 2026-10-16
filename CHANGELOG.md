# Changelog

## [Unreleased]

## [0.30.2] - 2026-10-16

### Fixed

- `release-fleet` / delivery readback: a project with a native Codex selection (`.codex/config.toml`, `[plugins."<id>@swissknifeman"]`) is read back through that selection; leftover vendored `.agents/plugins` bundles and their `skiller.codex.connect.*` lock records no longer block delivery (`DELIVERY_READBACK_FAILED` after every patch release). A vendored marketplace entry naming a plugin missing from the release is now reported as `unattested-plugin:<name>` instead of raising `KeyError` (`corex`, `chatom`).
- `release-fleet` Claude/Codex surfaces: a directory marketplace (`known_marketplaces.json`, `source: directory`) is confirmed in place from the checkout instead of waiting for an `installed_plugins.json` entry that Claude Code never writes (`claude-cache/*` stayed `DELIVERY_PROVIDER_UNCONFIRMED`); a Codex plugin the owner disabled is recorded as `DELIVERY_DISABLED_BY_OWNER` rather than a missing delivery (`codex-cache/skm`).

## [0.30.1] - 2026-10-16

### Fixed

- `analyst` and `maind` plugin manifests: `agents` listed the `./agents` directory, which Claude Code rejects ("must end with .md"), so both plugins failed to load. They now list the agent files (`analyst` 0.4.1, `maind` 0.6.2).
- `maind onboard`: the conditional skip of the instruction step outside the umbrella monorepo no longer counts as a failure (`skiller` skills `blender`, `blender-modeling` 0.4.2, `skiller` 0.19.4).

## [0.30.0] - 2026-10-16

First release of the new line: the ecosystem layout (`packages/*` modules on `aicore`), the project-local launcher, the `planner` plugin (`task` stays as an alias), layered configuration. The history of the previous layout is not carried over; migrate with [UPGRADE.md](UPGRADE.md).
