---
id: D26
date: 2026-08-13
status: accepted
item: P6.2
items: [P6.2, P6.3, P6.4]
supersedes: []
superseded_by: null
---
## Решение

Post-P6.1 product fixes `33a7dbcf` и `0948381c` входят в `v0.13.0`. Старый release-tree anchor
`4efef7a3` остаётся immutable evidence P6.1, но не становится tag target. P6.2 повторяе
release gates, режет CHANGELOG и запечатывает exact candidate в compact capsule; P6.3 создаёт tag
только из этого capsule; P6.4 rollout читает только compact verified-tag capsule. Push/GitHub
release не авторизованы. RAG:— (repo-grounded: Git history, release-discipline, findings/18).

## Почему

Тег на P6.1 target исключил бы исправление ложного `ROUTE-UNVERIFIABLE`; тег на moving HEAD не
имел бы воспроизводимой validation boundary. Разделение qualification/tag/rollout сохраняет
точный target и не тащит 230 KB inventory в execution read-path.
