# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Locator fragment** `scripts/aicore-locator.sh`: the one canonical way for a wrapper or test runner to find
  `aicore` (`AICORE_ROOT`, `_vendor/aicore`, sibling), with `AICORE_NOT_FOUND` and exit code 2 on a miss.
- **README** with the layout, subsystems, locator, compatibility shim, contracts and tests.
- **Shared code moved in from the root `core/` package** (history preserved): `aicore.util` (block, cli, env, http,
  io, paths, proc, project, repo, term, text), `aicore.provider` (the provider model and its catalogs),
  `aicore.artifacts` (artifact rendering, locking and reconciliation) and `aicore.usage`. There is no flat facade;
  import the subpackages directly. The root `core/` package stays as a transitional alias layer.
- **Provider data ships with the package**: `configs/provider-{capabilities,distribution,projection}.json`, found
  from the package file (`aicore.provider.data.config_path`); `aicore.provider.manifest.default_manifest_path()`
  replaces hard-coded repository paths in consumers.
- **`scripts/test.sh` and `scripts/validate.sh`**: the module tests and the fast structural checks run on their own,
  without any other module.
- **`digest/v1` contract and `aicore.util.digest`**: canonical JSON bytes and the tagged SHA-256 digest with
  language-neutral test vectors (`schemas/digest/v1/vectors.json`). `aicore.artifacts.artifact`,
  `provider.control_plane` and `provider.health` use it instead of their own copies; the digests they produce are
  unchanged for the values they hash. Floats and non-string object keys are now rejected everywhere.
- **Provider contracts**: `error/v1`, `capability-support/v1` and `model-catalog/v1` with examples.
  `aicore.provider.errors` has the twelve failure classes, `ProviderError` and `classify_failure`, which classifies
  by the rules of `configs/provider-errors.json` and never copies provider text into a record;
  `aicore.provider.models` reads `configs/model-catalog.json` (`load_model_catalog`, `select_model`,
  `select_effort`, `inventory`); `SupportSource` and `AvailabilityDimension` join `provider.values`. A test keeps the
  provider layer free of waiting and retry code.
- **`aicore.util.schema`**: the closed-profile JSON Schema validator, with `load_contract` for a
  `<contract>/v<N>/` directory; `scripts/ecosystem-units.py` validates all aicore contracts with it.
- **Architecture tests**: `aicore` imports only itself and the standard library; `usage.py` stays self-sufficient.
- **`aicore.state`**: the standard places for configuration and state. `machine_locations` resolves the XDG
  config/state/data/cache directories (a relative `XDG_*` value is ignored); an absolute `SKM_HOME` moves all four
  under one directory and switches off every legacy lookup, so sandboxes and tests never read the real home.
  `project_*` helpers name `.swissknifeman/{config.toml,state,backups}` and `find_project_root` finds the project.
  `resolve_with_legacy` prefers the new place, falls back to an existing legacy path with one warning per process
  and never copies or removes anything. `backup` and `list_backups` keep timestamped copies below
  `.swissknifeman/backups` (or the machine state directory) and rotate only stamp-named directories.
- **`aicore.MIN_PYTHON = (3, 9)`**, the single minimum Python version, and a test that parses every module with the
  3.9 grammar; the architecture test also checks the layer of `state` (only `util`).
- **`aicore.config` (first part): TOML reading and editing.** `config.toml` reads with `tomllib` on Python 3.11+ and
  with the vendored `tomli` 2.3.1 (`aicore/_vendor`, byte-for-byte from the pure wheel, pinned by hash in
  `VENDORED.json`, covered by an integrity test) before that, so a file means the same on 3.9 to 3.13. A syntax error
  becomes `ConfigError("CONFIG_FILE_INVALID")` with the file and the line; `LineIndex` maps key paths to lines.
  `config.toml_edit` sets or removes one leaf value, keeps comments, indentation and every other line, refuses
  dotted keys, inline tables, arrays of tables and multi-line values with a hint to edit by hand, and parses its
  own result and compares it with the expected document before returning it. Architecture tests keep the TOML
  import in `config/toml.py` only and the `config` layer on `util` and `state`.

### Changed
- **The gitignore policy moved into `aicore.state.gitignore`** (history preserved) and its data to
  `configs/gitignore-policy.json` of this package, found from the package file. The policy gains `project-config`
  (`.swissknifeman/config.toml`, committed) and `swissknifeman-state` (`.swissknifeman/state/`, ignored).
  `core.gitignore_policy` stays as an alias of the same module object.
- `scripts/test.sh` unsets `SKM_HOME`, `XDG_*_HOME` and `SKM_UNITS_PATH` before running the tests.
- `aicore.util.paths.state_dir` is documented as a legacy location (new code uses `aicore.state`).

### Removed
- `core.config_paths` and `shared_config_path` (the gitignore policy was the only user).
