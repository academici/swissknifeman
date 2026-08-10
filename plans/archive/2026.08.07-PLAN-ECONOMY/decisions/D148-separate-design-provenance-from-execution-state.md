---
id: D148
date: 2026-08-09
status: accepted
item: P6.2
items: [P6.2]
supersedes: []
superseded_by: null
---

## Решение

**`item-state` сохраняет `plan-design` events в append-only journal/history и в freshness digest,
но не использует их для execution `position.status`, `attempt` и `last_result`.** Позиция item'а
редуцируется по остальным command events; `plan-audit` остаётся значимым, потому что его RED
реально блокирует продолжение. Отвергнуты: терминальный `no-op` после каждого содержательного
design-run (ложное имя результата) и новый journal result `designed-ready` (расфриз sealed D24).

## Почему

Штатный `task:plan-design ... P6.2` обязан записать `result=in-progress`, но текущий
`plan_item_state.RESULT_STATUS` без учёта `command` превратил ещё не исполнявшийся P6.2 в `🟡` и
активировал phase-level bundle gate для P6. Это смешение authoring provenance с execution state;
временная append-only `no-op` correction возвращает текущий план в честное состояние, но не является
долгосрочной семантикой. RAG:— (repo-grounded:
`findings/P6.2-d91-and-bundle-dor-recon-2026-08-09.md`;
`packages/task/lib/task/plan_item_state.py`; journal events текущего design-run).
