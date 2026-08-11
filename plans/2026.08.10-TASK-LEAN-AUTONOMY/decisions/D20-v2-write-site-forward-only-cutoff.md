---
id: D20
date: 2026-08-11
status: accepted
item: P2.1
items: [P2.1]
supersedes: []
superseded_by: null
actor: repository-owner (delegated conflict resolution via D18)
model: gpt-5.6-terra/high (session route; effective effort self-attested)
evidence: RAG:— packages/task/lib/task/plan_lint_checks/policy.py + phases/P1/P1.md + phases/P2/P2.1.md
---

## Решение

Сохранить v1 `WRITE_SITE_CODES_CANON_DATE=2026-07-27` и добавить отдельный layout-v2 cutoff
`2026-08-12`, следующий календарный день после реализации v2 reader. Внутренняя status row несёт
layout marker; policy выбирает cutoff по нему. V2 terminal item с `Updated >= 2026-08-12` и без
канонической write-site строки обязан дать ERROR.

## Consequences

Закрытые 2026-08-11 P0/P1 carriers остаются immutable audit provenance и не начинают красить
каждый последующий plan lint задним числом. P2.1 всё равно печатает allow/allow, а все будущие v2
закрытия после activation boundary машинно gated. `policy.py` добавляется в exact Files P2.1.

## Почему

После исправления пустого v2 `Updated` target lint выявил четыре исторических items. Переписать их
значило бы нарушить D17/D18; special-case по plan/item ID создал бы костыль. Отдельная дата
активации повторяет уже документированную forward-only discipline этого же gate для v1 и остаётся
общей для всех v2 plans. RAG:— (repo-grounded).
