# aicore

The shared foundation of the swissknifeman modules. Every module depends on `aicore` and on nothing else
(see `requires` in its `unit.json`); `aicore` depends on no module.

The package holds:

- `unit.json` — the manifest of this module, written against its own `unit/v1` schema.
- `schemas/unit/v1` — the manifest every module ships as `packages/<id>/unit.json`.
- `schemas/check-result/v1` — the common result of one diagnostic check.
- `schemas/error/v1`, `schemas/capability-support/v1`, `schemas/model-catalog/v1` — provider failures, support
  observations and the model catalog; `aicore.provider.{errors,models}` implement them and
  `configs/{provider-errors,model-catalog}.json` hold their data.
- `schemas/digest/v1` — the tagged SHA-256 digest of canonical JSON, with language-neutral test vectors;
  `aicore.util.digest` is the one implementation and `aicore.util.schema` the closed-profile validator of all schemas.
- `lib/aicore/{util,provider,artifacts,usage}` — the shared stdlib-only code moved from the root `core/` package
  (import the subpackages directly; there is no flat facade), and `configs/provider-*.json` — the provider data,
  found from the package file.

The root `core/` package is a transitional alias layer over `aicore`; modules still import `core` and declare
`requires: aicore` for it until they move onto `aicore` themselves. Run the module tests with
`bash packages/aicore/scripts/test.sh`.

Check the manifests of all modules from the repository root:

```bash
python3 scripts/ecosystem-units.py check
python3 scripts/ecosystem-units.py list
```

See `schemas/README.md` for the schema layout rules.
