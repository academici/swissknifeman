---
id: D138
date: 2026-08-08
status: accepted
item: P4.4
items: [P3.6, P4.4, P6.4]
supersedes: []
superseded_by: null
---

## Решение

**Единый exact-discovery реестра `lint-check-dispositions.json` расширяется на
`task.plan_gates`: его локальные функции `_lint_*` входят в тот же introspection set, что и
`task.plan_lint_checks.{common,policy,parsing,engine}`.** P4.4 не переносит свои два гейта в
другой модуль и не заводит второй перечень: тест P3.6 перечисляет ровно все объявленные owners,
а JSON по-прежнему обязан совпасть с обнаруженным множеством байт-в-байт. RAG:— (repo-grounded:
`phases/P3/P3.6.md` требует exact introspection; `phases/P4/P4.4.md` требует проверки именно в
`plan_gates.py`; `findings/P4.4-lint-disposition-ownership-conflict.md`).

## Почему

Оба исходных требования обязательны и конфликтовали только из-за узкого списка owners в тесте:
оставить его прежним делает регистрацию P4.4 ложной красной, а добавить JSON-запись без discovery
создаёт silent fail-open. Явное расширение одного механизма сохраняет проверяемую полноту,
модульное владение P3.3/P4.4 и будущую активацию P6.4.

## Consequences

P4.4 добавляет `test_lint_dispositions.py` в Files и обновляет convention/configuration вместе с
двумя checks. Цена — P3.6 больше не может предполагать, что все owners находятся только в
`plan_lint_checks`; он обязан называть объявленный набор owners в одном тесте. Это не меняет
семантику существующих проверок, не включает новые opt-in gates и не затрагивает планы v1.
