---
id: D135
date: 2026-08-08
status: accepted
item: P3.4
items: [P3.4]
supersedes: []
superseded_by: null
---
## Решение

**P3.4 materializes and verifies Bundle v1 only for layout-v2 item'ы в admission
`ready` текущей фазы `🟡 In progress` после появления хотя бы одного committed Bundle этой фазы; historical и future записи остаются вне этой поверхности.** Проверка bundle
входит в `plan-lint`, который выбирает ту же ready-область, что P3.3; explicit
`plan-views.py` modes продолжают проверять decisions, status и state. RAG:—
(repo-grounded: `task.plan_admission`, `task.plan_weight`, `task.plan_bundle`; owner-grounded:
`brief/01-refinements.md`, 2026-08-08).

## Почему

`bundle --all` честно проходит все item-spec, включая исторические carrier'ы, которые
ещё не имеют полного декларативного входа. Это не дефект ready bundle и не даёт права
ослабить `unresolvable_entry`; применить materialization ко всей истории означало бы
вне scope мигрировать её ради проверки одного item'а.

## Consequences

D133 сохраняет требование явных существующих режимов вместо несуществующего `all`.
P3.4 не добавляет агрегирующий launcher, не перестраивает виды в линтере и не меняет
frozen taxonomy; новая граница фиксирует, какой producer output обязан существовать.
