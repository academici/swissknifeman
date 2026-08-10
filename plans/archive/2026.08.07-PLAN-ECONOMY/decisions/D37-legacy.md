---
id: D37
date: 2026-08-07
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Минимальный набор носителей, который реестр P1.1 обязан объявить**, иначе P2 нечего адресовать: `plan-core` · `status-view` · `decision-record` · `decision-view` · `phase-index` · `item-spec` · `item-state` · `phase-closure` · `history-view` · `journal` · `handoff` · `brief` · `research` · `findings` · `roadmap` · `index` · `open-questions` · `bundle` (P3) · `artifacts`. Реконсиль-требование к P1.1; отсутствие носителя в реестре — эскалация из P2, а не тихое расширение резолвера.

## Почему

Реестр — адресное пространство всех гейтов и путей (P1.1 Why); если носитель в нём не объявлен, резолвер P2.1 обязан либо его выдумать (второй источник истины), либо остановиться. Дешевле назвать состав сейчас — скелет P1 не терминален, а расхождение обнаружилось бы уже реализацией. RAG:— (repo-grounded: `research/04-…` §3; `phases/P1.md` P1.1)
