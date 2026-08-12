---
id: D9
date: 2026-08-10
status: accepted
item: P1.2
items: [P1.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via explicit design-finish remediation instruction)
model: gpt-5.6-sol/high (semantic plan-design route; effort self-attested)
evidence: RAG:✅ 2026-08-10 findings/02-external-rag.md + research/05-design-finish-remediation-f11-f15.md
---

## Решение

`docs/reference.md` остаётся carrier'ом и write scope владельца существующего foreign diff, а не
P1.2. До старта P1.2 repository owner/foreign-diff owner отдельно reconciles и commits строку,
в которой присутствуют exact official URLs:

- `https://www.prince2official.com/Prince2-News-and-Announcements/agile-progress-reporting-dashboards`
- `https://github.github.com/spec-kit/concepts/spec-of-specs.html`

P1.2 проверяет оба URL только в committed `HEAD:docs/reference.md`. Red prerequisite оставляет
P1.2 `⬜ Not started` и публикует structural waiting Next; текущий dirty файл не читается как
approval, не коммитится, не откатывается и не перезаписывается этим планом.

## Почему

План обязан иметь umbrella external-source ledger, но не вправе поглотить чужую незавершённую
запись. Committed owner prerequisite сохраняет provenance и делает cold-clone evidence
воспроизводимым без нарушения foreign-diff boundary. RAG:— (repo-grounded: root
`reference-provenance`/`worktree-safety`, audit F13/F14, explicit owner instruction).
