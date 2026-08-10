# Task transition map for P1.1

Дата: 2026-08-10.

## Источники

- `findings/01-repository-problem-map.md` — observed command/runtime contradictions.
- `findings/03-design-audit-2026-08-10.md` F1/F3/F4 — compiler/cwd/boundary failures.
- terminal P0 canon — `phases/P0/P0.2.state.md` at execution time.

## Exact change classes

| Current failure | Target transition | Owner/tests |
|:--|:--|:--|
| Cross-phase Routing can pass lint and fail compiler | lint rejects the same illegal cell before execution; legal item/same-phase range remains green | `plan_lint.py`, `task_contract.py`, `test_plan_lint_routing.py` |
| `plan-run` routing mismatch can become terminal product red | emit exact legal route/continuation without product-failure status | command/runtime + journal/state tests |
| Commands restate fixed close/audit cycles | consume compact P0 canon and keep only command delta | five command sources + provider parity tests |
| Review keyed to phase/status ritual | scope/SHA/risk material trigger and verdict reuse | `review_policy.py`, `plan_gates.py`, focused tests |

P1.1 starts with targeted `rg`/source reads inside `packages/task` and may edit only its exact
`Files`. This synthesis is the compact initial bundle; it does not claim to replace code inspection
during implementation. RAG:— (repo-grounded: sources above).

