---
id: D51
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Three authority classes are distinct: P0.3 `contract_freeze_decision` approves only recovery-contract semantics; conditional P0.4 `containment_mutation_decision` alone authorizes exact security/trust targets; P4.6 ordinary repository generation needs neither and is gated by the terminal ledger, frozen helper-plan hash and exact Harness `--authorize` set. P0.3 produces a versioned plan-local stdlib checker plus schema/tests/evidence; P0.4 verifies the checker byte hash and runs its exact `no-op` or `mutation` branch command, with a containment D# accepted only by the mutation branch. RAG:— (repo-grounded: audit F21/F22, D10/D46, P0.3/P0.4 and the Harness apply contract).

## Почему

Prevents a contract approval from becoming ambient write authority, keeps the no-op branch deterministic and makes the P0.3 producer consumed by P0.4 executable from a cold session.
