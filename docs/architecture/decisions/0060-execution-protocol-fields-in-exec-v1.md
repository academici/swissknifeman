# ADR 0060: Execution protocol fields in `exec/v1`, as minor changes

## Status

Accepted

## Context

Runs need event identity, owner fencing, a key hierarchy, a launch plan that proves how it was prepared, capability
freshness and an action per error class. `exec/v1` documents already exist and must stay valid.

## Decision

- **Rule.** The URNs and `v1` do not change; only optional fields and semantic checks are added, and
  `aicore schema compat --base origin/ecosystem-split` reports no breaking change. Each change is a line in the contract
  changelog of `packages/orch/docs/contracts.md`.
- **Identity and fencing.** `run-event` gets `event_id`, `causation_id`, `correlation_id`, `owner_epoch`, `attempt_id`,
  `call_id`, `error` and `raw`; `stage-result` and `effect-receipt` get `attempt_id` and `owner_epoch`.
- **Keys.** Prefixes `sub-`, `att-`, `call-` and `evt-` form a hierarchy; reuse of a key for different content is the
  semantic code `KEY_REUSED`.
- **Launch plan.** Digests of every input, the configuration used, module versions, decisions, the policy decision, the
  proof of the capability records, and a reason code with the chain for every refusal.
- **Capabilities and effects.** `capability-record` carries source, observation time, freshness and remediation
  (`CAPABILITY_FRESHNESS`); `effect-receipt` carries a precondition (`PRECONDITION_MISMATCH`); `run-policy` carries a
  version, sandbox, per-error actions, fallback routes (`FALLBACK_UNDECLARED`) and budgets.
- **Condensing.** `condense` is a stage kind; a drift between the condensed and the required parts is
  `CONDENSED_REQUIRED_DRIFT`.

## Alternatives considered

- `exec/v2`: rejected, nothing here breaks an existing document.

## Consequences

- Older readers ignore the new optional fields.
- Every new semantic code is listed in `docs/contracts.md` and in `contracts.semantic_checks`.

## Supersedes

None.
