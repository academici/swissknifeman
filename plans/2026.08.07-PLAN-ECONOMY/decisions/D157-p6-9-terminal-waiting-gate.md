---
id: D157
date: 2026-08-09
status: superseded
item: P6.9
items: [P6.9]
supersedes: []
superseded_by: D158
actor: gpt-5.6-sol/high
---

## Решение

После frozen v1.1.1 arm-A `fail` P6.9 является structural `waiting`, а не executable item:
текущий write scope пуст, ARTIFEX остаётся на паузе, а следующий допустимый шаг появляется только
после нового accepted owner D# на successor acceptance/repair после D155. Даже после такого D#
первым запускается повторный `task:plan-design 2026.08.07-PLAN-ECONOMY P6.9`; прямой
`plan-exec` запрещён до reconcile нового verdict identity, producer paths и donor scope.
RAG:— (repo-grounded: `findings/12-p6-acceptance-measurement.md` §Attempt v1.1.1; D153–D155;
`research/27-p6.9-terminal-waiting-gate-2026-08-09.md`).

## Почему

Старое ТЗ ожидало positive v1.1.0 verdict и заранее давало implementation-сессии право менять два
файла donor-плана. Фактический successor v1.1.1 завершился `fail`, а D155 требует отдельного owner
mandate для любого нового repair/successor attempt. Design-команда P6.9 сама таким мандатом не
является. Structural waiting сохраняет точный путь продолжения, не выдавая отсутствующую authority.

## Consequences

P6.9 остаётся `⬜ Not started`, план и фаза P6 остаются открыты, `plans/ACTIVE.md`, donor
`2026.08.03-ARTIFEX-SUPERVISOR` и `packages/artifex` не меняются. Старые donor slices и D151
сохраняются как исторические входы, но исключаются из live bundle P6.9. Цена — после будущего owner
D# потребуется ещё один frontier/high design-pass P6.9 до любой mutation; это намеренный
fail-closed барьер, а не новый acceptance attempt.
