---
id: D132
date: 2026-08-08
status: accepted
item: P3.2
items: [P3.2, P3.4]
supersedes: []
superseded_by: null
---
## Решение

**Frozen Bundle v1 schema не расширяется для `unresolvable_entry`.** Сборщик P3.2
разрешает каждую нормализованную декларацию тем же резолвером, что `plan_weight`; если
хотя бы одна позиция неразрешима, он fail-closed завершается до записи или замены bundle
и печатает её дословный текст. Поэтому каждый материализованный bundle остаётся
schema-valid v1. P3.4 реконструирует декларацию и присваивает отсутствию разрешения
замороженный ERROR-код `unresolvable_entry`; это класс верификации, а не дополнительный
тип JSON entry. RAG:— (repo-grounded: `root/contracts/bundle-v1.md`; `phases/P3/P3.2.md`;
`phases/P3/P3.4.md`; owner-grounded: `brief/01-refinements.md`, 2026-08-08).

## Почему

Схема допускает только digest-qualified resolved entries и намеренно запрещает лишние
поля. Добавление класса в JSON изменило бы frozen public contract, а запись без digest
не прошла бы required-поля. Вывод кода из реконструированной декларации сохраняет
пятизначную таксономию, отдельную диагностику и fail-closed поведение без второй формы
manifest или скрытого workaround.

## Consequences

P3.2 получает тесты атомарного отказа и неизменности уже существующего bundle; P3.4
получает тест, что реконструкция нерезолвленной декларации выдаёт именно
`unresolvable_entry` с дословным текстом. На schema, её копию и число failure-кодов
решение не влияет.
