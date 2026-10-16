# gui contracts

Contracts of the `gui` module: documents exchanged between the backend, the frontend, the bridges and external
extensions. Each contract is a JSON Schema validated by `aicore.util.schema` (the closed profile of the foundation).

## Rules

- **Folder.** `schemas/<contract>/v1/<contract>.schema.json` with `examples/valid/*.json` (at least two) and
  `examples/invalid/*.json` (at least three: an extra field, a wrong enum value, a missing required field, plus the
  cases named by the contract). An invalid example is named `<case>.<code>.json`, where `<code>` is the expected
  validation issue code, for example `extra-field.additional.json`.
- **Identity.** `$id` is `urn:swissknifeman:gui:<contract>:v1`; the root `$schema` is
  `https://json-schema.org/draft/2020-12/schema`; every document carries a `$schema` field whose value is the
  contract URN (`const`).
- **Closed profile only.** No `readOnly`, `format`, `maxLength`, `maxItems`, `anyOf`, `allOf`. Upper limits (lengths,
  sizes) are enforced by the resolver and the API and listed in the documentation of the contract.
- **Closed objects.** `additionalProperties: false` on every object and a `description` on every property; maps use
  `patternProperties` with an anchored pattern. An open object is allowed only for a document of another contract (the
  `schema-form` document), with a description naming the contract that validates it.
- **Several kinds in one document** (stream, view-data, config-mutation): one file, a root `oneOf` over `$defs`, the
  discriminator is a `const` field (`kind` or `view`).
- **Shared definitions.** Definitions of the foundation are referenced, never copied:
  `urn:swissknifeman:aicore:common:v1#/$defs/<name>` (semver, module_id, relpath, argv, rfc3339_utc), the aicore digest
  contract and `urn:swissknifeman:aicore:event:v1`.
- **Registration.** Each contract is an entry of `provides.contracts` in `unit.json`
  (`{id, path, version: v1, stability: development}`) and a row of the table below.
- **Tests.** `tests/test_contracts.py`: for every contract the valid examples pass and every invalid example fails
  with the code in its name.
- **Loading.** `lib/gui/contracts.py` loads a contract with `aicore.util.schema.load_contract` and the prefix
  `urn:swissknifeman:gui:`; references to `urn:swissknifeman:aicore:*` resolve in the foundation.
- **Versions.** A frozen contract changes additively in the same version and must pass `aicore schema compat`; a
  breaking change is a new `v<N+1>/` next to the old one.

## Contracts v1

| Contract | URN | Purpose | Added by |
| --- | --- | --- | --- |
| `contribution` | `urn:swissknifeman:gui:contribution:v1` | `gui.json` of a bridge or an extension: owner, protocol, handler, routes, widgets, queries, commands (`exec` invoke or argv, dry-run), forms with UI annotations by JSON pointer, configuration sections, docs | P1.2 |
| `view-data` | `urn:swissknifeman:gui:view-data:v1` | answer of a query for a host view, one kind per `view` | P1.2 |
| `api-error` | `urn:swissknifeman:gui:api-error:v1` | error envelope of the local API and its code registry | P1.3 |
| `bootstrap` | `urn:swissknifeman:gui:bootstrap:v1` | handshake of versions and protocol between the shell, the frontend and the backend | P1.3 |
| `run` | `urn:swissknifeman:gui:run:v1` | record of a command run and its states | P1.3 |
| `stream` | `urn:swissknifeman:gui:stream:v1` | WebSocket frames, one kind per `kind`, with a cursor and `snapshot_required` | P1.3 |
| `trust` | `urn:swissknifeman:gui:trust:v1` | plugin trust: enforcement (`declared`, `enforced`, `advisory`), grants, plugin state, plugin document | P1.3 |
| `config-mutation` | `urn:swissknifeman:gui:config-mutation:v1` | configuration write: preview request, preview, commit request, commit result | P1.3 |
| `catalog` | `urn:swissknifeman:gui:catalog:v1` | deterministic resolved catalog of contributions with rejection codes and a digest | P1.4 |

The column "Added by" names the step of the module plan that freezes the contract; until then the row is a reservation.
Frozen: `contribution`, `view-data` (field reference: [docs/contribution.md](../docs/contribution.md)); `api-error`,
`bootstrap`, `run`, `stream`, `trust`, `config-mutation` (code registry, run transitions, stream and write rules:
[docs/api.md](../docs/api.md)); `catalog` (resolver and catalog: [docs/contribution.md](../docs/contribution.md#resolver)).
