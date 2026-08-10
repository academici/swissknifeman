---
id: D7
date: 2026-08-10
status: accepted
item: P0.1
items: [P0.1, P0.2, P1.1, P1.2]
supersedes: []
superseded_by: null
actor: plan-designer
model: gpt-5.6-sol/high (semantic plan-design route; effort self-attested)
evidence: RAG:— root AGENTS.md package-scope routing + findings/03-design-audit-2026-08-10.md F3/F4
---

## Решение

Четыре item'а сохраняются, но каждый имеет одного write-owner и exact cwd: P0.1 — Harness,
P0.2 — Skiller, P1.1 — Task, P1.2 — repository root. Generated outputs другого уровня допустимы
только как deterministic result named owner generator; item не поглощает source edits соседнего
package.

## Почему

Это сохраняет lean four-item plan и D1 adaptive grouping, одновременно выполняя обязательное
root→package instruction routing и конечную write boundary. RAG:— (repo-grounded: root
`AGENTS.md` package-scope/generated-artifact rules, audit F3/F4, synthesis
`research/02-design-finish-reconciliation.md`).
