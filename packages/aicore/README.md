# aicore

The shared foundation of the swissknifeman modules. Every module depends on `aicore` and on nothing else
(see `requires` in its `unit.json`); `aicore` depends on no module and on nothing but the Python standard library
(Python 3.9 or later).

## Layout

```text
packages/aicore/
  unit.json  README.md  CHANGELOG.md
  bin/aicore                           # command line: `aicore config ...`
  configs/       provider-{capabilities,distribution,projection,errors}.json  model-catalog.json  gitignore-policy.json
  lib/aicore/    util/  provider/  artifacts/  state/  config/  usage.py  _vendor/tomli/
  schemas/       <contract>/v1/  and README.md
  scripts/       test.sh  validate.sh  aicore-locator.sh
  tests/         util, io, text, usage, contracts, architecture, vendor; provider/, artifacts/, state/ and config/
```

`lib/aicore/__init__.py` carries only the version; there is no flat facade. Import the subpackages directly.

## Subsystems

| Subsystem | Holds | Used by |
| --- | --- | --- |
| `aicore.util` | atomic write, paths, text, terminal, CLI and processes, HTTP, repository root, managed blocks, project type, `digest` (canonical JSON and tagged SHA-256), `schema` (closed-profile JSON Schema validator) | all modules |
| `aicore.provider` | provider capability manifests, configuration layers, control plane, health, adapter registry, request lifecycle, `errors` (failure classes and classification by data), `models` (model catalog); data in `configs/` found from the package file (`provider.data.config_path`, `manifest.default_manifest_path()`) | harness, maind, planner, orch, skiller |
| `aicore.artifacts` | plan, apply and lock of artifacts in projects, reconcile | skiller, harness, maind |
| `aicore.state` | standard machine and project places (`SKM_HOME`, XDG, `.swissknifeman/`), legacy lookup, timestamped backups with rotation, the gitignore policy | `aicore.config`, all modules |
| `aicore.config` | module settings from layers (`resolve`): schema defaults, machine file, project file, extra layers, environment, `--config` file, flags; `explain` (origin of every value), secret references (`Secret`, `register_secret_resolver`), `edit_layer_file` (comment-preserving write with backup); module discovery and `config.example.toml` generation; the `aicore config` CLI; the one TOML entry (`toml`, `toml_edit`) | all modules |
| `aicore.usage` | one accumulator of tokens parsed from provider logs; self-sufficient, so it can be vendored byte for byte | analyst, harness, skiller |

## Configuration and state

Settings of a module come from layers and are read only through `aicore.config.resolve(module, ...)`; a module never
parses `config.toml` itself. Places come from `aicore.state`.

### Places

| What | Default | With `SKM_HOME=<dir>` |
| --- | --- | --- |
| machine config file | `$XDG_CONFIG_HOME/swissknifeman/config.toml` (`~/.config/...`) | `<dir>/config/config.toml` |
| state (registries, machine backups) | `$XDG_STATE_HOME/swissknifeman` (`~/.local/state/...`) | `<dir>/state` |
| data | `$XDG_DATA_HOME/swissknifeman` (`~/.local/share/...`) | `<dir>/data` |
| cache | `$XDG_CACHE_HOME/swissknifeman` (`~/.cache/...`) | `<dir>/cache` |
| project config (in git) | `<project>/.swissknifeman/config.toml` | same |
| project state, backups (ignored) | `<project>/.swissknifeman/{state,backups}/` | same |

`SKM_HOME` isolates a sandbox or a test: all four machine places move under it and no legacy location is read. It
must be an absolute path; a relative `XDG_*` value is ignored. A file that exists only at an old location
(for example `~/.swissknifeman/analyst`) is still read, with one warning per process; nothing is copied or removed
until `swissknifeman upgrade`. Before a write the old file is copied to `.swissknifeman/backups/<UTC stamp>/` (machine
files: to the state directory), and the newest ten copies are kept. `aicore config paths` prints the resolved places.

### Layers and merging

From low to high: schema `default`, machine file, project file, a module's own extra layers, environment,
`--config FILE`, flags. Each file starts with `schema_version = 1` and holds one `[<module>]` table:

```toml
schema_version = 1

[analyst.recompute]
candidate_min_n = 25
```

Tables merge key by key; arrays and scalars of a higher layer replace the lower value. In a file layer
`_unset = ["recompute.candidate_min_n"]` returns a key to its default (or removes it), and
`_append = {"some.list" = ["x"]}` extends an array instead of replacing it. A key cannot be both set and appended in
one layer. A schema may restrict a key to some layers (`x-skm-layers`), for example to keep machine paths out of a
project that is committed. Unknown keys, wrong types, ranges, a missing or newer `schema_version` and forbidden layers
are errors that name the layer, file, line and key.

Environment variables are `SKM_<MODULE>_<PATH>`: upper-case module id, `-` as `_`, path segments joined by `__`, for
example `SKM_ANALYST_RECOMPUTE__CANDIDATE_MIN_N=30`. The text is parsed by the type of the key (booleans:
`true|false|1|0|yes|no`; arrays: a JSON array). An unknown path under a known module warns once.

Config files are TOML 1.0. `tomllib` of Python 3.15 or later also accepts TOML 1.1, which Python 3.9 to 3.14 cannot
read, so do not use 1.1 syntax in a shared file.

### Secrets

A key marked `x-skm-secret` in the schema holds a reference, never the secret: `env://NAME` reads the environment
variable `NAME`. Other schemes are registered with `register_secret_resolver`. A plain value in such a key is an error
whose text does not repeat it. `ResolvedConfig.secret(key).reveal()` looks the value up at the call; the value is not
shown by `show`, `explain`, `repr`, error messages or tracebacks.

### Command line

```text
aicore config show <module>                          resolved values and their layers
aicore config explain <module> [key] [--json]        origin of each value; --json is config-explain/v1
aicore config set <module>.<key> <value> --machine|--project
aicore config unset <module>.<key> --machine|--project
aicore config init --machine|--project [--module ID ...] [--force]
aicore config example <unit-dir> [--write|--check]   config.example.toml of a module
aicore config paths [--json]
```

`swissknifeman config ...` is the same command. `--root DIR` names the project, `--config FILE` adds the invocation
layer. `set` and `unset` change one line with the comment-keeping editor, check the result against the schema and
back up the file first; dotted keys, inline tables and multi-line values are refused with a hint to edit by hand.

Example run in a sandbox (`scripts/dev-sandbox.sh`), with the machine file setting 20 and the project file 25:

```text
$ aicore config set analyst.recompute.candidate_min_n 25 --project
$ aicore config explain analyst recompute.candidate_min_n
recompute.candidate_min_n = 25
  from project <project>/.swissknifeman/config.toml:4
  overrides machine <home>/config/config.toml:4 = 20; defaults = 15
$ aicore config set analyst.recompute.candidate_min_n 0 --project
aicore config set: <project>/.swissknifeman/config.toml:4: project: recompute.candidate_min_n: 0 is less than the minimum 1 [CONFIG_TYPE]
```

Every module with a `provides.config` entry in `unit.json` ships `configs/config.schema.json` and a generated
`config.example.toml`; `scripts/ecosystem-units.py check` fails when the example drifts.

### Vendored tomli

Before Python 3.11 the files are read by `aicore/_vendor/tomli` (tomli 2.3.1, MIT, copied byte for byte from the
pure wheel; hashes in `VENDORED.json`, checked by `tests/test_vendor.py`). 2.3.x implements TOML 1.0 like `tomllib`
of Python 3.11 to 3.14, so a file reads the same on 3.9 to 3.14. Never edit the vendored files; to update, take the
new wheel, check its hash and write a new `VENDORED.json`. Decisions: ADR 0034 to 0036 in `docs/architecture`.

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
