---
id: D17
date: 2026-08-12
status: accepted
item: P1.5
items: [P1.5]
supersedes: []
superseded_by: null
---
## Решение

Live path/digest re-resolution bundle/read-budget gate применяется только
к nonterminal executable items. Bundle terminal item остаётся closure-time
digest manifest: его схема и carrier bytes проверяются, но намеренно
удалённый retirement input не резолвится заново и не заставляет
переписывать закрытую историю. Canonical test fixture после P1.5 всегда
создаёт v2; retired missing/v1 input создаётся только как explicit
rejection fixture без compatibility/generated-view path. RAG:— (repo-grounded:
`findings/09-P1.5-retirement-preflight.md`, `research/06-P1.5-retirement-acceptance-boundary.md`).

## Почему

Перезапись закрытых specs/bundles под новый filesystem и сохранение
live migrator tombstones одинаково нарушают D7: первое искажает evidence,
второе возвращает retired runtime surface. Разделение live executor
admission и terminal evidence сохраняет оба инварианта.
