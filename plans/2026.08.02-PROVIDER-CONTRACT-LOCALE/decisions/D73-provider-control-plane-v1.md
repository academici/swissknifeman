---
id: D73
date: 2026-08-14
status: accepted
type: contract_freeze_decision
item: P1.3
items: [P1.3]
contract_version: v1.0.0
supersedes: []
superseded_by: null
---
## Решение

The repository owner accepts the exact bytes of
`root/contracts/provider-control-plane-v1.md` at `v1.0.0`, SHA-256
`f959cb9a7dfd672c7a208942e52a63c51cb64b9af8c72ed85d6d174439e91772`.
The accepted proposal is DecisionRequest
`P1.3-provider-control-plane-freeze-v1.0.0-2026-08-14`, action digest
`3e6cfb1b6fbf8af95b13513c52a83eb33bb9e1f330731d5734e580c9d36f9ae5`,
resolved `approve` with reason `P5_DECISION_OWNER_APPROVED`.

Exact Owner reply:
`APPROVE P1.3 PROVIDER-CONTROL-PLANE C1-C6 AS WRITTEN`.

The accepted C1-C6 set preserves the predecessor G01-G11 crosswalk and every no-write,
provider-isolation, rollback, convergence, and authority boundary encoded in the contract.

## Почему

P1.3 requires one explicit, deterministic legacy upgrade and rollback contract before
provider implementations can consume the shared control-plane meaning.

## Consequences

D73 freezes only the exact provider-control-plane v1.0.0 bytes and the closed C1-C6 decision
set. It authorizes no apply, provider, package, Brain, credential, or fleet mutation. Any later
semantic or byte change requires another typed decision and contract version verdict.
