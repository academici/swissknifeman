---
id: D139
date: 2026-08-08
status: accepted
item: P4.4
items: [P4.4, P5.5, P6.2, P6.4]
supersedes: []
superseded_by: null
---

## Решение

**Квалификация terminal return-loop escalation и owner authorization записываются в одной
существующей item-scoped finding с additive frontmatter:** `gate: return-loop-v1`,
`fingerprint_digest`, `occurrences`, `qualification` и `owner_authorization: D#`.
Для `qualification=unqualifiable` вместо digest/count обязательна
`missing_carrier_reason`; остальные два состояния несут digest и count. P4.4 строит и
валидирует evidence, P6.2 производит его при закрывающем пути, P6.4 включает проверки.
RAG:— (repo-grounded: sealed journal boundary D24; additive finding metadata D137;
`root/contracts/return-loop-v1.spec.json` перечисляет evidence каждой qualification).

## Почему

Линтер не может доказать, что закрывающая команда квалифицировала эскалацию, если факт остаётся
только в stdout; добавлять поле в `journal.jsonl` запрещено. Existing findings уже являются
append-only item-scoped carrier и принимают additive frontmatter, поэтому сохраняют
воспроизводимый факт без нового носителя и без переписывания истории.

## Consequences

До P6 выключенные проверки P4.4 остаются молчащими: historical plans не обязаны содержать
новую finding. После opt-in отсутствие, невалидная qualification или несуществующий D# в
`owner_authorization` — hard diagnostic; advisory/bypass mode не появляется. P5 продолжает
владеть transport `DecisionRequest`, а не формой P4 evidence.
