# aicore

The shared foundation of the swissknifeman modules. Every module depends on `aicore` and on nothing else
(see `requires` in its `unit.json`); `aicore` depends on no module.

Today the package holds the module contract only:

- `unit.json` — the manifest of this module, written against its own `unit/v1` schema.
- `schemas/unit/v1` — the manifest every module ships as `packages/<id>/unit.json`.
- `schemas/check-result/v1` — the common result of one diagnostic check.

The shared code (utilities, providers, content delivery, config and state) still lives in the root `core/`
package and moves here later; until then modules declare `requires: aicore` for their `core` imports.

Check the manifests of all modules from the repository root:

```bash
python3 scripts/ecosystem-units.py check
python3 scripts/ecosystem-units.py list
```

See `schemas/README.md` for the schema layout rules.
