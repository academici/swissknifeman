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
  `description` on every property. A dictionary whose keys are identifiers is expressed with `patternProperties` (an anchored pattern such as `^[a-z][a-z0-9-]*$`) and `additionalProperties: false`; `propertyNames` only checks key names and does not make a key allowed. Lists of records stay for ordered collections, and a standard that defines an open map (`skill-descriptor` `metadata`) keeps its open object.
- A contract can reference another contract of this directory with `$ref: "urn:swissknifeman:aicore:<contract>:v<N>#/$defs/<name>"`; `load_contract` loads the neighbouring `<contract>/v<N>/` directory for the reference (its schemas serve `$ref` only). A missing directory is an error.
- Fixtures of every contract are exercised by `tests/test_contracts.py` through `aicore.util.schema.load_contract`;
  `scripts/ecosystem-units.py check` loads every contract under the closed profile.
- `digest/v1` also ships `vectors.json`: language-neutral test vectors for the canonical JSON rules.

## Contracts

| Contract | Version | Purpose |
| --- | --- | --- |
| `common` | v1 | Shared `$defs` for other contracts to reference: `semver`, `module_id`, `relpath`, `argv`, `stability`, `extensions` (namespaced `<owner>.<name>` keys), `media_type`, `rfc3339_utc` |
| `unit` | v1 | Module manifest (`packages/<id>/unit.json`): identity, version, dependencies, public surface, default event subscriptions |
| `check-result` | v1 | Result of one diagnostic check (`ok`, `warn`, `fail`, `skip`) |
| `error` | v1 | Normalized provider failure: class, code, retryable, safe message; implemented by `aicore.provider.errors` |
| `capability-support` | v1 | One observation of provider support for a capability, by dimension (feature, resource, policy, health) |
| `model-catalog` | v1 | Models of each provider by class and effort; data in `configs/model-catalog.json`, API `aicore.provider.models` |
| `config-explain` | v1 | Origin of every effective setting of a module: layers, winning layer, file and line, overridden values; implemented by `aicore.config` |
| `digest` | v1 | Tagged SHA-256 digest (`sha256:<hex>`) of canonical JSON; rules and test vectors; implemented by `aicore.util.digest` |
| `skill-descriptor` | v1 | What a skill is, read from its directory: identity, content digest, Agent Skills standard fields, provenance; implemented by `aicore.content.skill` |
| `eval-context` | v1 | What an evaluation result was produced from: skill digest, fixtures, grader and runner, observed values only; implemented by `aicore.content.eval` |
| `event` | v1 | One event of the project journal, a subset of CloudEvents 1.0: id, source, type `<module>.<subject>.<verb>`, time, optional data; unknown extension attributes are ignored by readers |
| `artifact-ref` | v1 | Reference to data kept outside an event or a document: tagged digest, size, media type, sensitivity; implemented by `aicore.state.blobs` |
| `permissions` | v1 | Declared effects (filesystem areas, network, secrets, shell, environment pass-through, sandbox profile); embedded by `unit` and `extension` through `$ref` |
| `extension` | v1 | Manifest (`extension.json`) of an external plugin: kind `command` or `subscriber`, protocol range, entrypoint, provided points and events, permissions |
| `plugin-request` | v1 | What the host writes to a plugin: one JSON object with the operation `describe`, `invoke` or `event` |
| `plugin-response` | v1 | What a plugin writes back: one JSON object with a status, an output or an error |
| `plugin-describe` | v1 | The output of a `describe` call: plugin identity and the digest of what it provides |
| `telemetry-conventions` | v1 | Names of spans and attributes for traces and metrics, with the cardinality of each attribute and the rule that only low-cardinality attributes label metrics; data in `configs/telemetry-conventions.json`, API `aicore.util.telemetry` |

## Module config schemas

A module's own settings are described by `configs/config.schema.json` (`unit.json` `provides.config`), a schema with
`$id` `urn:swissknifeman:<module>:config:v1`, loaded by `aicore.config.load_module_schema`. It uses the same closed
profile, extended for configuration with `minimum` and `maximum` and two annotations the validator ignores:
`x-skm-secret: true` (a string key that holds a secret reference such as `env://NAME`) and `x-skm-layers` (the layers
that may set the key). Any other `x-*` keyword is rejected. A config schema also needs `additionalProperties: false`
on every table, no `required`, a `description` on every key, and keys that are scalars or arrays of scalars; values
that apply when nothing sets a key are its `default`. A *map* — an object with one anchored `patternProperties` pattern (no dots in names) whose value is a leaf or a table of leaves — lets a configuration file add named entries (`[aicore.subscriptions.notes]`); `x-skm-layers` applies to the leaves of every entry. The examples of these contracts do not apply to module schemas;
the tests of `aicore.config` use a fixture schema.
