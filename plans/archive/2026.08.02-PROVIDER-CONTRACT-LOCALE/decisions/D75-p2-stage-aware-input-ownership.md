---
id: D75
date: 2026-08-14
status: accepted
type: plan_contract_repair
item: P2.1
items: [P2.1, P2.2, P2.3]
supersedes: []
superseded_by: null
---
## Решение

Under the repository owner's delegated direction to choose the optimal safe solution and finish
P2.1, repair the P2 stage-aware admission metadata: P2.2 names the exact overlay contract and
carrier-matrix paths it produces, and P2.3 marks those absent future inputs as `producer: P2.2`.

## Почему

The active-phase read-budget gate correctly refuses missing Required Reads without a declared
producer. Both files are already normative P2.2 outputs and P2.3 inputs; the missing annotation
was a plan-carrier defect, not an unresolved product decision. The phase DoR also spelled a
clarification marker literally inside the statement that none remained, causing a false-positive
lint warning. The repairs make existing state machine-readable without changing scope,
acceptance, routing, contract meaning, or implementation.

## Consequences

Until P2.2 closes, P2.3 is `pending-producer` instead of falsely `ready` with missing-file errors.
After P2.2 closes, absence of either declared output fails closed as
`producer_terminal_missing`. No product file or frozen contract is changed by D75.
