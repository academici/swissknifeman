# Changelog

## [Unreleased]

## [0.30.3] - 2026-10-16

### Added

- `scripts/check-env.sh` (`--strict`, `--quiet`, `--json`, `--bin-dir`): a read-only check that the machine has what the modules call (bash 4+, python3 3.9+, git, `jq`, `node` 18+, `uvx`, systemd user session, `bubblewrap` + `socat` and a working user+net namespace, an agent client, optional PHP/pnpm/ruff/rsync). It prints the fix for every gap; `install.sh` runs it first and stops when a required item is missing (`SKM_SKIP_ENV_CHECK=1` skips it). Tests: `scripts/test-check-env.py`.
- "Requirements" block (programs, versions, install commands) and "Sandbox on Ubuntu 24.04+" (the AppArmor profile for `bwrap`) in `docs/getting-started.md`, a short list in `README.md`, step 0 in `UPGRADE.md`.
- `skiller connect --cleanup-codex-bundles`: retires vendored Codex bundles (`.agents/plugins`) and their lock records once a project selects plugins natively; reversible (backup), refuses when a file is not lock-owned.

### Fixed

- `swissknifeman doctor` ran the text probes of `aicore` and `skiller` as JSON and reported them as failed ("probe output is not JSON"): a probe declared `output: text` is now judged by its exit code (first line = observation).
- `analyst.partners` could not find the planner installed by `install.sh` (`plan.py` link); `plan.py` and `render-provider-commands.py` are executable.
- `orch.sandbox` remediation points to `scripts/check-env.sh` and the requirements page.
- Tests: the description/upstream gates of skiller ran `validate.sh` from a copy without aicore (12 failures); the `maind onboard` tests no longer register temporary projects in the developer's real `skiller/projects.json`; `test_real_spawn_handshake` follows the `{"items": [...]}` contract of `projects list`.

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
