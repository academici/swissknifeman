---
id: D130
date: 2026-08-08
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

**Приоритетный путь сбоя — `repair-now` в текущей root-сессии, а не автоматический `plan-design`:** первый детерминированный, локальный и обратимый фикс допускается, когда точная причина, минимальная правка, граница файлов и проверка известны; исполнитель добавляет journal record и finding, чинит и повторяет Validation. `isolated-review` нужен при повторе fingerprint/неясности, `plan-design` или owner gate — при semantic choice, public/released contract, security/authority, irreversible/destructive действии, cross-package/cross-repository effect или неограниченной правке. **Узкое исключение к D124:** противоречие буквального значения между ещё неисполняемыми внутриплановыми копиями frozen contract ремонтируется сразу, если принятая D-запись уже выбирает значение, ни один runtime consumer не использует неверное, все копии обновляются вместе и validation зелёная. Для P2.7 каноничен `phases/<Pn>/<Pn>.closed.md`; синхронизируются registry/spec copies, после чего item продолжается без cold start. **Consequences:** уточняет D124 только в части blanket-trigger `frozen/public-contract`; оно не отменяет требование review/design для смысловой смены или выпущенного контракта. Цена — обязательная доказуемая классификация и журнал вместо дешёвого, но непрозрачного «починил на глаз»; P4–P6 всё так же реализуют общий machine-gated protocol.

## Почему

Владелец потребовал прекратить мелкие блокировки и сохранять текущую сессию для очевидных локальных исправлений. Внешние источники поддерживают минимальную сложность, manager control и проверяемую итерацию, но не универсальный порог; граница и исключение выведены из repo evidence P2.7. RAG:✅ 2026-08-08 (`findings/20-local-repair-boundary-2026-08-08.md`; синтез `research/19-local-repair-policy-2026-08-08.md`).
