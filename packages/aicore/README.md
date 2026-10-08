# aicore

The shared foundation of the swissknifeman modules. Every module depends on `aicore` and on nothing else
(see `requires` in its `unit.json`); `aicore` depends on no module and on nothing but the Python standard library
(Python 3.9 or later).

## Layout

```text
packages/aicore/
  unit.json  README.md  CHANGELOG.md
  configs/       provider-{capabilities,distribution,projection,errors}.json  model-catalog.json
  lib/aicore/    util/  provider/  artifacts/  usage.py
  schemas/       <contract>/v1/  and README.md
  scripts/       test.sh  validate.sh  aicore-locator.sh
  tests/         util, io, text, usage, contracts, architecture; provider/ and artifacts/
```

`lib/aicore/__init__.py` carries only the version; there is no flat facade. Import the subpackages directly.

## Subsystems

| Subsystem | Holds | Used by |
| --- | --- | --- |
| `aicore.util` | atomic write, paths, text, terminal, CLI and processes, HTTP, repository root, managed blocks, project type, `digest` (canonical JSON and tagged SHA-256), `schema` (closed-profile JSON Schema validator) | all modules |
| `aicore.provider` | provider capability manifests, configuration layers, control plane, health, adapter registry, request lifecycle, `errors` (failure classes and classification by data), `models` (model catalog); data in `configs/` found from the package file (`provider.data.config_path`, `manifest.default_manifest_path()`) | harness, maind, planner, orch, skiller |
| `aicore.artifacts` | plan, apply and lock of artifacts in projects, reconcile | skiller, harness, maind |
| `aicore.state` | standard machine and project places (`SKM_HOME`, XDG, `.swissknifeman/`), legacy lookup, timestamped backups with rotation, the gitignore policy | `aicore.config`, all modules |
| `aicore.config` | module settings from layers (`resolve`): schema defaults, machine file, project file, extra layers, environment, `--config` file, flags; `explain` (origin of every value), secret references (`Secret`, `register_secret_resolver`), `edit_layer_file` (comment-preserving write with backup); the one TOML entry (`toml`, `toml_edit`) | all modules |
| `aicore.usage` | one accumulator of tokens parsed from provider logs; self-sufficient, so it can be vendored byte for byte | analyst, harness, skiller |

## Finding aicore

Wrappers and test runners of the modules find `aicore` with one canonical fragment,
`scripts/aicore-locator.sh`, copied verbatim between the markers `# --- aicore locator ---` and
`# --- end aicore locator ---`. The order is:

1. `$AICORE_ROOT`; when it is set and is not an `aicore` checkout, the fragment fails and does not look further;
2. `<module>/_vendor/aicore`;
3. the sibling `<module>/../aicore` (inside the hub repository only).

A candidate qualifies when its `unit.json` has `"id": "aicore"`. The fragment exports `AICORE_ROOT` and
`AICORE_LIB=$AICORE_ROOT/lib`, which the wrapper puts on `PYTHONPATH`. When nothing is found it prints
`AICORE_NOT_FOUND` with the hint to set `AICORE_ROOT` and exits with code 2.

## Compatibility shim

The root `core/` package is a transitional alias layer. Its `__init__.py` makes `aicore` importable (using
`AICORE_ROOT`, otherwise the sibling `packages/aicore/lib`) and registers every moved module under its old name as
the same module object (`core.io` is `aicore.util.io`, `core.provider.lock` is `aicore.artifacts.lock`), and keeps
the old flat `core.__all__`. The window lasts until `core/` is removed, when the hub modules move onto `aicore`.
New code imports `aicore`, never `core`. A test checks that every alias is the same object and that the facade is
unchanged.

## Contracts

All contracts are JSON Schema draft 2020-12 in the closed profile, with valid and invalid examples; the schema is the
source of truth and the code implements it. The layout rules and the full table are in `schemas/README.md`.

| Contract | Implementation |
| --- | --- |
| `unit/v1` | manifest of a module (`packages/<id>/unit.json`); checked by `scripts/ecosystem-units.py` |
| `check-result/v1` | result of one diagnostic check |
| `digest/v1` | `aicore.util.digest`; test vectors in `schemas/digest/v1/vectors.json` |
| `error/v1` | `aicore.provider.errors`; rules in `configs/provider-errors.json` |
| `capability-support/v1` | `SupportLevel`, `SupportSource`, `AvailabilityDimension` in `aicore.provider.values` |
| `model-catalog/v1` | `aicore.provider.models`; data in `configs/model-catalog.json` |
| `config-explain/v1` | `aicore.config.ResolvedConfig.explain_json` |

## Tests

```bash
bash packages/aicore/scripts/test.sh        # all aicore tests, in a throwaway HOME, without any other module
bash packages/aicore/scripts/validate.sh    # fast structural checks
python3 scripts/ecosystem-units.py check   # manifests and boundaries of all modules, from the repository root
```

The tests need nothing but `aicore` itself, so the folder can be tested as a standalone repository.
