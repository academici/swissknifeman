# Task transition map for P1.1

Дата: 2026-08-10.

## Источники

- `findings/01-repository-problem-map.md` — observed command/runtime contradictions.
- `findings/03-design-audit-2026-08-10.md` F1/F3/F4/F11/F12 — compiler/cwd/context/docs failures.
- `findings/06-cross-project-execution-telemetry.md` — observed routing/future/process/literal/
  baseline/audit/close pathologies and real fail-closed counterexamples.
- `research/07-adaptive-failure-and-telemetry-synthesis.md` — verified failure/action matrix.
- terminal P0 canon — `phases/P0/P0.2.state.md` at execution time.

## Exact change classes

| Current failure | Target transition | Owner/tests |
|:--|:--|:--|
| Cross-phase Routing can pass lint and fail compiler | lint rejects the same illegal cell before execution; legal item/same-phase range remains green | `plan_lint.py`, `task_contract.py`, `test_plan_lint_routing.py` |
| `plan-run` routing mismatch can become terminal product red | emit exact legal route/continuation without product-failure status | command/runtime + journal/state tests |
| Future/unavailable consumer validation can turn a green producer red | classify `dependency-not-ready/unknown`; gate only existing affected consumers | `plan_gates.py`, `task_contract.py`, focused tests |
| Raw tool/status signal is treated as outcome | `observe → reproduce → classify → act → verify`; only acceptance/safety/authority terminal | `review_policy.py`, commands, transition table tests |
| Running external process can be prematurely terminalized | reconcile PID/output/state and wait same process before retry | commands + red-first process-state fixture |
| Pre-existing/unrelated red gates current item | compare baseline delta and ownership; record without product stop | `plan_gates.py`, focused tests |
| ATTENTION is serialized as `audit-red` | distinct `audit-attention`; material trigger alone produces RED | `journal.py`, state/status and audit tests |
| Start/terminal/run-report identities do not join | Claude/Codex observed session adapters + deterministic per-attempt `run_id` | session context + journal tests |
| Reconciliation appends duplicate terminal close | idempotent close returns existing event pointer and appends zero bytes | `journal.py`, item-state tests |
| Commands restate fixed close/audit cycles | consume compact P0 canon and keep only command delta | five command sources + provider parity tests |
| Review keyed to phase/status ritual | scope/SHA/risk material trigger and verdict reuse | `review_policy.py`, `plan_gates.py`, focused tests |
| Layout v2 Task Contract emits historical `same-session — item` | v2 emits exact `continue-root` for ordinary continuation; separate no-`Layout` v1 fixture preserves historical compatibility | `task_contract.py`, `command_render.py`, `test_task_contract.py`, v2/v1 fixtures |
| Public Task docs still teach mandatory status-driven audit/close | canonical source moves to `packages/task/docs`; aggregate `docs/task` is generator-owned; lifecycle/index teach one pre-exec audit plus material-triggered reuse | package docs, `scripts/docs-sync.sh --check`, standalone+aggregate builds |

P1.1 starts with targeted `rg`/source reads inside `packages/task` and may edit only its exact
`Files`. This synthesis is the compact initial bundle; it does not claim to replace code inspection
during implementation. RAG:— (repo-grounded: sources above).
