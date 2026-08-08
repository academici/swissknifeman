---
id: D52
date: 2026-08-07
status: superseded
item: ''
items: []
supersedes: []
superseded_by: D137
---
## Решение

**Шов дефекта ОБЪЯВЛЯЕТСЯ со стороны `decisions/`/`findings/`, а не новым полем журнала, и его вокабуляр (`file` × `rule_or_contract_locus` × `defect_class`) переиспользуется дословно.** Схема `journal.jsonl` этим планом не меняется; входное объявление отпечатка обязано быть удовлетворимо полями уже замороженного `history-projection` v1. Отвергнуто расширение схемы журнала.

## Почему

Схема журнала запечатана планом `2026.07.18-FOREMAN` P1.1, и D24 прямо запретил требовать несуществующее поле; механизм связи со стороны находок и решений уже введён D24 и уже переиспользован D46 для записи результата гейта потребителя — третьего механизма не заводится. Вокабуляр шва тоже не чеканится заново: он заморожен во флоте вместе со split-ban («wording, severity, report splitting, or reviewer identity cannot change it»), и второй словарь идентичности гарантированно разойдётся с первым — это ровно основание, по которому D6 переиспользует классы полномочий. RAG:— (repo-grounded: `packages/task/lib/task/journal.py` `REQUIRED_FIELDS`; `packages/task/lib/task/review_policy.py` `finding_id`; `authority-policy-v1` §Bounded AUTO-FIX; D24, D46 этого плана)
