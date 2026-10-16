# ADR 0034: Layered config semantics

## Status

Accepted

## Context

[ADR 0019](0019-config-semantics.md) fixed the principles (missing field falls through, explicit removal, arrays
replace, explain, secret references). Code needs exact rules: the file shape, the order of layers, the operators, the
environment mapping and the errors. Defaults must also have exactly one home.

## Decision

A module's settings are read only through `aicore.config.resolve(...)`; no module parses `config.toml` itself. The TOML
import lives in `aicore/config/toml.py` only (a test enforces it).

- **Schema.** `packages/<id>/configs/config.schema.json` (`unit.json` `provides.config`, `$id`
  `urn:swissknifeman:<id>:config:v1`): closed objects, no `required`, every leaf has a `description` and a scalar,
  scalar-array or `enum` type; the only defaults are the `default` keywords of the schema (no `defaults.json`).
  `minimum`/`maximum` and the annotations `x-skm-secret` and `x-skm-layers` extend the schema profile; other `x-*` fail.
- **File.** Machine, project and `--config` files are TOML with an integer `schema_version = 1` and one `[<module>]`
  table per module. A missing, newer or invalid version is an error; other modules' tables are ignored; an empty or
  absent file is an absent layer.
- **Order, low to high.** `defaults`, `machine`, `project`, extra layers of the module, `env`, `invocation`
  (`--config FILE`), `flags`.
- **Merge** inside a module section, in this order: `_unset = ["a.b"]` resets a key to its schema default (or removes
  it); `_append = {"a.b" = [...]}` extends an array; then plain values (tables merge, arrays and scalars replace).
  The rules are checked by the tests of the same names in `tests/config/test_model.py`: `test_missing_key_falls_through`,
  `test_maps_merge_arrays_replace`, `test_unset_restores_default`, `test_unset_without_default_removes_the_key`,
  `test_unset_is_followed_by_the_values_of_the_same_layer`, `test_append_extends_array`,
  `test_append_to_a_non_array_is_a_type_error`, `test_value_and_append_in_one_layer_conflict`,
  `test_layer_forbidden`, `test_layer_forbidden_covers_unset_append_env_and_flags`, `test_merged_value_is_validated_again`.
  `_unset` and `_append` exist only in file and extra layers.
- **Validation.** Each layer's section is validated alone (errors carry layer, file, line, key), then the merged tree.
  `x-skm-layers` lists the layers where a key may be set (`CONFIG_LAYER_FORBIDDEN` otherwise).
- **Environment.** `SKM_<MODULE>_<PATH>`; `-` becomes `_`, path segments are separated by `__`, names match the schema
  without regard to case, and the text is parsed by the leaf type (`tests/config/test_env.py`). An unknown path under a
  known module prefix warns once (`CONFIG_ENV_UNKNOWN`) because other variables share the prefix.
- **Secrets.** A leaf marked `x-skm-secret` holds only a reference `scheme://path`; `env://NAME` is built in and
  `register_secret_resolver` adds schemes. `Secret` prints `***`, cannot be pickled and resolves on `reveal()` without
  a cache. No error, explain output, `repr` or traceback carries the value (`tests/config/test_secret_redaction.py`).
- **Explain.** Each key reports value, layer, file, line, source, the default and the lower layers it overrides; the
  JSON form is the contract `config-explain/v1`.
- **Errors.** `ConfigError(code, ...)` renders `<file>:<line>: <layer>: <key>: <message> [<code>]`.

Explicit non-goals: locking the config file (concurrent writes: the last one wins, each write is atomic and backed
up); an install-profile layer; secret-resolver plugins (they arrive with the extension stage on top of the registry);
moving legacy per-module files into the new layers (done by `swissknifeman upgrade`).

## Alternatives considered

- `defaults.json` next to the schema: rejected, two sources of one default drift apart.
- Whole-file replacement per layer: rejected, a project could not change one key.
- Dotted keys or `null` for removal: TOML has no null; an explicit `_unset` is readable and checkable.

## Consequences

- `config.example.toml` and the explain output are generated from the schema.
- A module's configuration is validated before the module runs, with file and line.

## Supersedes

Refines [ADR 0019](0019-config-semantics.md) and the layers of [ADR 0005](0005-layered-config-and-standard-state-locations.md).
