# roadmap — отложенные направления swissknifeman

Здесь живут только самодостаточные спецификации, чей измеримый критерий запуска ещё не
сработал. Реализованная, отклонённая или перенесённая в исполняемый план работа из каталога
удаляется; её история остаётся в git и в именованном плане-владельце.

> **Правило каталога:** колонка **Статус** описывает только живой остаток. Исторические
> ссылки на plan items вне собственного плана всегда используют форму `<PLAN-ID> Pn.m`.

## Живой каталог

| Файл | Статус | Критерий запуска / исторический якорь |
|:--|:--|:--|
| [`2026.07.25-memory-hub-service.md`](2026.07.25-memory-hub-service.md) | 🧭 deferred by decision | Второй человек, больше двух машин/машина вне LAN, project ACL или тысячи записей; подготовительный предшественник — `2026.07.25-ECO-OPT P4`. |
| [`2026.08.15-locale-corpus-after-field-validation.md`](2026.08.15-locale-corpus-after-field-validation.md) | ⬜ ждёт field evidence | Конкретный проект, surface и воспроизводимый пользовательский эффект после compact field cut `2026.08.02-PROVIDER-CONTRACT-LOCALE P4`. |
| [`plan-design-vs-exec-status-check.md`](plan-design-vs-exec-status-check.md) | ⬜ один замер | Повтор ошибочного выбора `plan-design` для уже готовой фазы на втором плане; первый замер — `2026.07.16-INS-EVO P1`. |
| [`plan-lesson-capture.md`](plan-lesson-capture.md) | ⬜ один замер | Повтор потери post-closure owner finding на втором плане; первый замер — `2026.07.14-DTEREMA-SITE P6.2–P6.3`. |
| [`upstream-notify-diet-fork.md`](upstream-notify-diet-fork.md) | ⬜ trigger не сработал | Реальный болезненный drift либо содержательная диета `notify`-скилла; последняя квалификация — `2026.07.31-SKM-LEAN P7.3`. |

## Диспозиция 2026-09-09

- 23 owner-prioritized/triggered carrier'а перенесены байт-в-байт в
  [`2026.09.09-№1-LEAN-EXECUTION/artifacts/source-roadmap/`](../plans/2026.09.09-№1-LEAN-EXECUTION/artifacts/source-roadmap/);
  исполняемый SSOT — item contracts этого плана; Laravel parallel-isolation
  carrier назначен точно `2026.09.09-№1-LEAN-EXECUTION P5.3`.
- Artifex-остаток передан его живому плану-владельцу
  [`2026.08.03-ARTIFEX-SUPERVISOR`](../plans/2026.08.03-ARTIFEX-SUPERVISOR/), а завершённая
  memory-recall запись — архивному владельцу
  [`2026.08.07-PLAN-ECONOMY`](../plans/archive/2026.08.07-PLAN-ECONOMY/).
- Исправленная provider-docs запись и отклонённый OTEL preset удалены из живого каталога;
  их доказательства остаются соответственно в git и в
  [`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md).
- Полная проверяемая матрица судеб, включая 24 удалённые ссылки прежнего индекса, находится в
  [`findings/00-roadmap-disposition.md`](../plans/2026.09.09-№1-LEAN-EXECUTION/findings/00-roadmap-disposition.md)
  и решении
  [`D1-roadmap-promotion.md`](../plans/2026.09.09-№1-LEAN-EXECUTION/decisions/D1-roadmap-promotion.md).

## Принцип

Не внедрять спекулятивно. Новый carrier получает проверяемый trigger; сработавший trigger
переводит работу в один исполняемый план, а не создаёт параллельный backlog. Внешний provenance
фиксируется в [`docs/reference.md`](../docs/reference.md), отклонённые повторяющиеся идеи — в
[`docs/rejected-optimizations.md`](../docs/rejected-optimizations.md).
