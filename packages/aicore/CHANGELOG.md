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
