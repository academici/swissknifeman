---
id: D15
date: 2026-08-12
status: accepted
item: P1.2
items: [P1.2]
supersedes: []
superseded_by: null
---
## Решение

Владелец разрешил reversible redesign P1.2 в границах
`packages/task/lib/task/plan_migrate.py`,
`packages/task/lib/task/plan_lint_checks/parsing.py` и `packages/task/tests` для
migrator/linter compatibility. Решение не расширяет closed grammar и не
авторизует новую fleet transformation/write policy. RAG:—
(owner/repo-grounded: `decisions/queue.jsonl`,
`findings/04-layout-v1-migration-results.md`).

## Почему

Первый rehearsal доказал локальный Routing compatibility gap. Последующая
15-target matrix выявила другие классы, поэтому узкое разрешение нельзя
трактовать как одобрение скрытых семантических решений. RAG:—
(repo-grounded: `findings/05-layout-v1-full-fleet-admission-matrix.md`,
`research/04-P1.2-migration-policy-boundary.md`).
