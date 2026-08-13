---
id: D16
date: 2026-08-12
status: accepted
item: P1.2
items: [P1.2, P1.3, P1.4, P1.5]
supersedes: []
superseded_by: null
---
## Решение

Применён owner response `authorize-phase-redesign` для
`DR-P1.2-full-fleet-migration-policy`. P1 разделяется на: (1) узкую Routing-
нормализацию по D15; (2) frozen admission policy и 15/15 green dry-run previews;
(3) отдельную controlled-write фазовую ступень с source-digest, rollback и zero-live
ledger; (4) retirement v1 runtime только после этого ledger. Исходное v1-дерево
каждого target сохраняется byte-exact; нормализованные state/decision carriers
не изображают хронологию и не вводят скрытых defaults. RAG:—
(owner/repo-grounded: `decisions/queue.jsonl`, `findings/05-layout-v1-full-fleet-admission-matrix.md`,
`research/05-P1-phase-redesign-and-premortem.md`).

Owner response разрешает redesign и запись в 15 exact `migration_order` targets, но не
даёт авторизацию на молчаливое удаление stale registry rows или семантический
repair invalid plan roots вне `migration_order`; если они остаются в fresh inventory, P1.4
материализует exact DecisionRequest и остаётся nonterminal. RAG:—
(repo-grounded: action surfaces `DR-P1.2-full-fleet-migration-policy`, P1.1 inventory).

## Почему

Один expanded item смешал бы closed grammar repair, frozen migration semantics,
cross-project writes и irreversible reader retirement. Четыре оставшихся item дают
отдельные acceptance/rollback boundaries, но сохраняют adjacent batch reuse внутри
migrator и fleet cutover. Альтернативы и отказ от single-item expansion записаны
в `research/04-P1.2-migration-policy-boundary.md` и `research/05-P1-phase-redesign-and-premortem.md`.
RAG:— (repo-grounded: findings/05, research/04–05).
