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
- Schemas stay inside the closed profile of the validator used by the hub (`packages/orch/lib/orch/schema.py`):
  JSON Schema draft 2020-12 with the root `$schema`, `additionalProperties: false` on every object, and a
  `description` on every property. Dictionaries with free-form keys are expressed as lists of records.
- Fixtures are exercised by `scripts/test-ecosystem-units.py`.

## Contracts

| Contract | Version | Purpose |
| --- | --- | --- |
| `unit` | v1 | Module manifest (`packages/<id>/unit.json`): identity, version, dependencies, public surface |
| `check-result` | v1 | Result of one diagnostic check (`ok`, `warn`, `fail`, `skip`) |
