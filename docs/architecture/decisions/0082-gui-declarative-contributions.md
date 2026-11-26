# ADR 0082: GUI contributions are declarative; UI annotations stay outside canonical schemas

## Status

Accepted

## Context

Bridges and extensions add views, queries, commands and forms to the GUI. Forms need UI hints per field (widget,
group, order, read-only). The canonical schemas of modules are validated by the closed profile of
`aicore.util.schema`, which accepts only the `x-skm-secret` and `x-skm-layers` annotations and rejects any other
`x-*` keyword. Running plugin JavaScript in the UI would make every extension a code execution risk.

## Decision

- **Contract.** A contribution is a `gui.json` document validated by `urn:swissknifeman:gui:contribution:v1`, owned by
  the `gui` module (`packages/gui/schemas`).
- **Declaration.** `provides.gui` (a relative path) is an additive property of aicore `unit/v1` and `extension/v1`;
  `scripts/ecosystem-units.py check` verifies the file and validates it with `contribution/v1`.
- **UI annotations.** Annotations live in `forms[]` of the contribution and point to fields by JSON pointer; canonical
  schemas do not change. A read-only mark in a form is UX only: the bridge and the domain owner refuse the write.
- **Forms.** The frontend renders forms with its own renderer limited to the closed profile plus the forms overlay;
  there is no client-side validation, the authority is the backend preview; TypeScript types are generated from the
  contracts and kept by golden tests. No plugin JavaScript in v1: only host views and declared widgets.

## Alternatives considered

- `x-skm-widget` / `x-skm-group` inside canonical schemas: rejected, the closed profile refuses unknown `x-*`, it mixes
  validation with UI and would change the schemas of every module.
- rjsf with Ajv or JSON Forms: rejected, incomplete draft 2020-12 support; Ajv compiles validators with `new Function`
  and needs `unsafe-eval` in the CSP.

## Consequences

- A JSON pointer can go stale when a schema changes; the resolver and tests report it.
- Sources: https://rjsf-team.github.io/react-jsonschema-form/docs/usage/validation/ ; https://jsonforms.io/news

## Supersedes

None.
