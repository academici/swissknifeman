---
id: D8
date: 2026-08-10
status: superseded
item: P1.2
items: [P1.2]
supersedes: []
superseded_by: D16
actor: plan-designer
model: gpt-5.6-sol/high (semantic plan-design route; effort self-attested)
evidence: RAG:— findings/03-design-audit-2026-08-10.md F5 + plan-protocol v2 status/Next canon
---

## Решение

GO означает: все P1.2 acceptance predicates green, item закрывается `🟢 Done`, а Next ведёт к
`close: task:plan-close 2026.08.10-TASK-LEAN-AUTONOMY P1`. ADJUST означает: хотя бы один
predicate red/unknown, P1.2 остаётся `🟡 In progress`, через owner tool создаётся ровно один
durable DecisionRequest с exact owning-package continuation, а handoff объявляет структурный
`waiting: <decision-id resolved> → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2`.

## Почему

ADJUST не является успешной terminality и не может архивировать план; одновременно он не
запускает автоматический design/audit loop без материального D3 trigger. RAG:— (repo-grounded:
audit F5, `research/02-design-finish-reconciliation.md`, plan-protocol v2 status/Next canon).
