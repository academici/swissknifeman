# Объявленный порядок фазы: recovery и следующий bundle

**Обновление по аудиту 2026-10-04:** реализация уже была в исходниках; проверены declared order, predecessor edges, recovery/frontier и остаток required Batch. Нового числового порядка поверх объявленной цепочки не введено. Machine handoff теперь использует тот же вычисленный successor; новое phase-close больше не генерируется. Сводка: [аудит всех 12 записей](../docs/roadmap.md).

Ниже сохранены исходные наблюдения и предложения.

Дата: 2026-10-04. Измеренный дефект Task на исходном SKM HEAD
`e59e4f2ca3aab23b56e846bb59702d46037c408c`.

## Измеренная проблема

Frozen AZGUARD `2026.10.01-№1-AZGUARD-V1` объявляет полный порядок 23 пунктов
P4 в `phases/P4/P4.md`, секция `Dependencies and order`: P4.4 → P4.17 →
P4.5 → P4.6. `_execution_ranks` понимал только полный маркированный
`Planned Items` и использовал числовую последовательность для стрелочной цепочки.
Recovery выводил ложный producer P4.6 для P4.17 по общим PanelBuilder/RoleCompiler.
`materialize_next_ready` независимо сортировал номера: после GREEN P4.4 выбирал
P4.5, а после переставленного пункта пропускал следующий пункт с меньшим номером.

## Owning repair

Один локальный разбор `_declared_phase_orders` принимает только полный уникальный
набор item ID фазы: прежние bullets в `Planned Items` или самостоятельную
стрелочную цепочку в `Dependencies` / `Dependencies and order`. Частичные,
дублированные, неизвестные и конфликтующие цепочки, упоминания в произвольном
тексте и других секциях не объявляют порядок. Явные producer-аннотации сохраняются.

`Dependencies`-цепочка также задаёт непосредственный predecessor: P4.17 не
перечисляет DatabaseSource в Inputs/Required Reads, поэтому одних старых
эвристик путей недостаточно для настоящей зависимости P4.4 → P4.17.
Bullets `Planned Items` сохраняют прежнюю семантику рангов без новой serial edge.
Recovery inference, сортировка и cutoff следующего bundle используют эти ранги.
Plan schema, public runtime API и frozen consumer specs не менялись.

## Проверка и границы

16 focused recovery tests GREEN; 176 tests dependency closure GREEN:
recovery, admission, readiness, downstream, context, item-state, bundle,
deferred reconciliation, delivery, work, repeat. До исправления новые регрессии
давали 5 failures. `git diff --check` GREEN.

Логи последнего кандидата:
`/tmp/skm-order-recovery-v2-final-20261004.log`,
`/tmp/skm-order-dependency-closure-v2-final-20261004.log`,
`/tmp/skm-order-azguard-readonly-v2-final-20261004.log`.

Actual read-only consumer probe импортировал канонический
`packages/task/lib/task/plan_recovery.py`, SHA-256
`ff4829339b6783d58780774fe1a4c95152262c9e60404d82aef438bee2b10c06`.
P4.17 pending = только P4.4; P4.6 отсутствует. Hypothetical GREEN P4.4 допускает
P4.17 и выбирает `bundles/P4.17.json`. Для этой проверки positions и bundle
write/readiness calls заменены в памяти: она подтверждает routing, а не реальное
закрытие P4.4 или полноту будущего bundle. AZGUARD journal, carriers, product и
evidence не изменялись. Независимые concurrent transport edits SKM сохранены.
