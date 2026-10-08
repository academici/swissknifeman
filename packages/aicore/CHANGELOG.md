# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Shared code moved in from the root `core/` package** (history preserved): `aicore.util` (block, cli, env, http,
  io, paths, proc, project, repo, term, text), `aicore.provider` (the provider model and its catalogs),
  `aicore.artifacts` (artifact rendering, locking and reconciliation) and `aicore.usage`. There is no flat facade;
  import the subpackages directly. The root `core/` package stays as a transitional alias layer.
- **Provider data ships with the package**: `configs/provider-{capabilities,distribution,projection}.json`, found
  from the package file (`aicore.provider.data.config_path`); `aicore.provider.manifest.default_manifest_path()`
  replaces hard-coded repository paths in consumers.
- **`scripts/test.sh` and `scripts/validate.sh`**: the module tests and the fast structural checks run on their own,
  without any other module.
- **Architecture tests**: `aicore` imports only itself and the standard library; `usage.py` stays self-sufficient.
