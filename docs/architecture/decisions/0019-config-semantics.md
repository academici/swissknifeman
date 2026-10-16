# ADR 0019: Configuration semantics: merging, removal, explain, secrets, invocation layer

## Status

Accepted

## Context

A layered configuration needs exact behaviour before code depends on it.

## Decision

A missing field takes the lower layer's value. Removal uses explicit syntax (TOML has no null), for example an
`unset` list. Arrays are replaced by default, maps are merged, appending to an array uses an explicit form. A module
schema may forbid overriding a key below a given layer, and unknown keys are a schema error. `explain` shows the
result, its layer, file, line and shadowed values. A `secret_ref` type (`env://NAME`, `keyring://...`) keeps secret
values out of config dumps, events, logs, doctor reports, manifests, receipts and launch plans (covered by a
redaction test). The invocation layer `--config FILE` sits between the environment and flags. A profile layer is
deferred until install profiles exist. Data sensitivity is a minimal flag on artifacts and secrets.

## Alternatives considered

- Ad hoc rules per module: rejected.

## Consequences

- The rules are fixed before the loader is written and are tested against fixtures.
- The OpenAPI Overlay model serves only as an orientation, not as a format.

## Supersedes

None.
