---
id: D5
date: 2026-08-10
status: accepted
item: P1.2
items: [P1.1, P1.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via brief/00-brief.md)
model: gpt-5.6-sol/high (authored; actual effort not independently attested)
evidence: RAG:— brief/00-brief.md + findings/01-repository-problem-map.md + research/01-target-operating-model.md
---

## Решение

Focused deterministic checks остаются safety net; приёмка operating model требует живого
canary и разбора фактической траектории. Новая exhaustive test matrix не создаётся.

## Почему

Формальная зелень не доказывает отсутствие ритуальных циклов на реальном проекте.
RAG:— (repo-grounded: `brief/00-brief.md`, `findings/01-repository-problem-map.md`,
`research/01-target-operating-model.md`).
