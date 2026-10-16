# ADR 0030: Shared contracts: digest, error, capability support, model catalog

## Status

Accepted

## Context

Digest code, failure classes and support levels were copied between modules, and orch and task are not yet built on
`aicore`. Contracts need a language-neutral form first and adopters later.

## Decision

Four contracts live in `packages/aicore/schemas/<contract>/v1/` with valid and invalid examples. `digest/v1` is the
tagged `sha256:<64 hex>` of canonical JSON (sorted keys, no whitespace, UTF-8 without escaping, no floats) with
language-neutral test vectors. `error/v1` is the failure record and its class registry. `capability-support/v1`
separates the support level (`native`, `adapted`, `unsupported`) from the source (`declared`, `probed`, `inferred`)
and the dimension (`feature`, `resource`, `policy`, `health`). `model-catalog/v1` holds class selectors, effort
selectors and the model inventory per provider. The implementations are `aicore.util.digest`, `aicore.util.schema`
(the closed-profile validator, a generalisation of the copies in orch and task), `aicore.provider.errors` (which
classifies by the rules in `configs/provider-errors.json`, not by code) and `aicore.provider.models`. Orch and
task adopt the contracts in their own stages.

## Alternatives considered

- Schemas only, implementations later: rejected, the copies inside `aicore` would stay duplicated.
- Move orch and task onto the contracts now: rejected, it crosses their stage boundaries.

## Consequences

- One digest and one validator implementation; `exec` digests stay in the bare-hex form until orch adopts `digest/v1`.
- A new value of a closed enum is a breaking change and needs `v2`.

## Supersedes

None.
