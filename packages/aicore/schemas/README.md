# aicore schemas

Language-neutral contracts shared by all modules.

## Layout

```text
schemas/<contract>/v<N>/<contract>.schema.json   # the schema, one file per kind
schemas/<contract>/v<N>/examples/valid/*.json    # documents the schema accepts
schemas/<contract>/v<N>/examples/invalid/*.json  # documents it rejects (extra field, bad enum, missing field)
```

- A contract lives in a directory `<contract>/v<N>/`; a breaking change creates `v<N+1>/` next to it and
  leaves the old directory in place.
- `$id` is `urn:swissknifeman:aicore:<contract>:v<N>` and carries the same `N` as the directory.
- Schemas stay inside the closed profile of the validator `aicore.util.schema` (`lib/aicore/util/schema.py`):
  JSON Schema draft 2020-12 with the root `$schema`, `additionalProperties: false` on every object, and a
  `description` on every property. Dictionaries with free-form keys are expressed as lists of records, except where a standard defines the map (`skill-descriptor` `metadata`, an open object).
- Fixtures of every contract are exercised by `tests/test_contracts.py` through `aicore.util.schema.load_contract`;
  `scripts/ecosystem-units.py check` loads every contract under the closed profile.
- `digest/v1` also ships `vectors.json`: language-neutral test vectors for the canonical JSON rules.

## Contracts

| Contract | Version | Purpose |
| --- | --- | --- |
| `unit` | v1 | Module manifest (`packages/<id>/unit.json`): identity, version, dependencies, public surface |
| `check-result` | v1 | Result of one diagnostic check (`ok`, `warn`, `fail`, `skip`) |
| `error` | v1 | Normalized provider failure: class, code, retryable, safe message; implemented by `aicore.provider.errors` |
| `capability-support` | v1 | One observation of provider support for a capability, by dimension (feature, resource, policy, health) |
| `model-catalog` | v1 | Models of each provider by class and effort; data in `configs/model-catalog.json`, API `aicore.provider.models` |
| `config-explain` | v1 | Origin of every effective setting of a module: layers, winning layer, file and line, overridden values; implemented by `aicore.config` |
| `digest` | v1 | Tagged SHA-256 digest (`sha256:<hex>`) of canonical JSON; rules and test vectors; implemented by `aicore.util.digest` |
| `skill-descriptor` | v1 | What a skill is, read from its directory: identity, content digest, Agent Skills standard fields, provenance; implemented by `aicore.content.skill` |

## Module config schemas

A module's own settings are described by `configs/config.schema.json` (`unit.json` `provides.config`), a schema with
`$id` `urn:swissknifeman:<module>:config:v1`, loaded by `aicore.config.load_module_schema`. It uses the same closed
profile, extended for configuration with `minimum` and `maximum` and two annotations the validator ignores:
`x-skm-secret: true` (a string key that holds a secret reference such as `env://NAME`) and `x-skm-layers` (the layers
that may set the key). Any other `x-*` keyword is rejected. A config schema also needs `additionalProperties: false`
on every table, no `required`, a `description` on every key, and keys that are scalars or arrays of scalars; values
that apply when nothing sets a key are its `default`. The examples of these contracts do not apply to module schemas;
the tests of `aicore.config` use a fixture schema.
