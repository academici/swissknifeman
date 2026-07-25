# Roadmap исполнения — 2026.07.18-FOREMAN

<!-- Собран после полной детализации всех 8 фаз (P7 — последняя). Отвечает на «какую команду
     дальше?» без анализа всего плана. Живой документ: закрытие фазы / re-design обновляет
     таблицу (+строка в Update Log). Roadmap НЕ переопределяет Routing §3 — только группирует
     запуски. Порядок exec — строго phase-first: P0→P1→P2→P3→P4→P5→P6→P7. -->

**Обновлён:** 2026-07-18 · **Соответствует plan.md:** v0.19.0

> **Статус exec:** P0 исполнена и терминальна (6/6 🟢); контракты P0 **sealed** (Consumed
> plan-protocol v2.8.0@2cf26e8; Exported policy v1 + run-folder v1). P1 reconcile-refined
> (D46/D47) — готова к exec. Следующий шаг — **exec P1.1** (см. handoff.md). §7: журнал P1.1–P1.2
> и decision-лог P5.4 остаются draft (запечатываются своими фазами). Продукт переименован
> foreman→artifex (D48); legacy PLAN-ID FOREMAN и workflow-codename сохранены.

## Карта исполнения

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-run (manual) | opus/high | ✅ имя пакета (OQ-1) | design-item: reuse-гейт + утверждение имени владельцем |
| P0.4 | solo | plan-run (manual) | opus/high | — | снятие [UNVERIFIED] механик — блокирует контракты P0.2/P0.6 |
| P0.2 | solo | plan-run (manual) | opus/high | — | контракт драйвер↔plan-protocol; после P0.4 (механики сняты) |
| P0.6 | solo | plan-run (manual) | opus/high | — | run-folder+мандат; ссылается на журнал P1.1 (reconcile) |
| P0.5 | W-mine | workflow | sonnet/medium (экстракция) + opus (синтез) | ✅ каталог принципов | fan-out дешёвыми моделями; скрипт готов в workflows/ |
| P0.3 | solo | plan-run (manual) | opus/high | — | policy-схема; ПОСЛЕ P0.5 (каталог — сид философия-полей) + P0.6 |
| P1.1 | solo | plan-run (manual) | opus/high | — | схема journal.jsonl — правка канона плановой системы |
| P1.2 | solo | plan-run (manual) | opus/high | — | корневой индекс плана |
| P1.3 | solo | plan-run (manual) | sonnet/high | ✅ contribution в task | механизм записи журнала (close-протокол + хелпер) |
| P1.4 | solo | plan-run (manual) | sonnet/high | ✅ lint-гейт журнала | soft-lint (WARN legacy / ERROR датовые) |
| P1.5 | solo | plan-run (manual) | sonnet/high | ⛔ fail closed до терминальной P2 плана `2026.07.24-AGENT-RELIABILITY` (D49) | re-пин `driver-plan-protocol.md` (сейчас `v2.8.0 @ 2cf26e8` против живых `2.11.0`) + сверка якорей §1–§4; ЗАКРЫВАЕТ фазу P1 |
| P2.1 | solo | plan-exec | sonnet/medium | — | механический каркас пакета |
| P2.2–P2.5 | B-P2 | plan-run серия (manual) | sonnet/high | обзор владельца | ядро драйвера: state-machine→parsing→recovery→resume, сцеплено; review full |
| P3.1 | solo | plan-exec | sonnet/medium | — | settings-фрагмент (mode флагом); security-surface → review full, не батчить |
| P3.2 | solo | plan-exec | sonnet/medium | — | PreToolUse policy-хук; security → review full, solo |
| P3.3 | solo | plan-run (manual) | opus/high | ✅ директивы скилла | авторинг supervisor-protocol — несущий контент |
| P4.1 | B-P4 | plan-exec серия | sonnet/medium | — | канал-агностик notify + envelope |
| P4.2 | B-P4 | plan-exec серия | sonnet/medium | — | эскалация драйвера (пауза+severity-таймаут) |
| P4.4 | B-P4 | plan-exec серия | sonnet/medium | — | репортинг итогов в mAInd |
| P4.3 | solo | plan-run (manual) | opus/high | ✅ OQ-2 (после пилота) | Layer 3 remote-approve — security, ОПЦИОНАЛЬНО (MVP без него) |
| P5.1–P5.4 | B-P5 | plan-run серия (manual) | opus/high | ✅ rulebook (P5.3) | прогресс-движок: модель→логика→rulebook→decision-лог, сцеплено; review full |
| P6.1 | solo | plan-run (manual) | sonnet/high | ✅ contribution harness (OQ-6) | пак artifex + skiller-профиль; config-home fork |
| P6.2 | solo | plan-exec | sonnet/medium | — | доки пакета по готовым контрактам |
| P6.3 | solo | plan-run (manual) | opus/high | ✅ вердикт пилота | боевой unattended-пилот; item НЕ 🟢 без owner-sign-off |
| P7.1–P7.2 | B-P7 | plan-run серия (manual) | sonnet/medium | — | BRAIN-сессии, fan-out; аудит читаемости + практика; lint абсолютным путём |
| P7.3 | solo | plan-run (manual) | opus/high (Fable) | ✅ канон 00-Strategy | стратегический канон vault; Execution Rules — Fable-заход |
| P7.4 | solo | plan-run (manual) | opus/high | ✅ дом скилла (OQ-7) | Brain-скилл-указатель; bucket + опц. раскатка |

**Solo-обоснования** (почему не объединять): P0.1–P0.6 — несущие контракты/design под opus/high,
каждый несёт свой вердикт-артефакт (объединение размывает reuse/контракт-решения); P1.1–P1.4 —
правка чужого канона (task) + contribution-обзор владельца; P3.1/P3.2 — security-surface (review
full, D6-инвариант: full-классы не батчатся под skip-confirm); P3.3/P4.3/P6.1/P6.3/P7.3/P7.4 —
опус-design с гейтом владельца посреди (вердикт нельзя объединять с соседним item).

## Готовые launch-block'и групп

### W-mine — P0.5 майнинг принципов (fan-out)

| Параметр | Значение |
|:--|:--|
| Model | сессия-оператор любой (скрипт пинит модели постадийно) |
| Thinking | — (модели заданы в скрипте) |
| Context | NEW SESSION — Workflow-оркестрован |
| Суть | Fan-out дешёвыми экстракторами по истории планов → синтез каталога принципов старшей моделью |

```
Workflow({scriptPath: "05-Projects/03-Packages/Swissknifeman/plans/2026.07.18-FOREMAN/workflows/wf-foreman-principles-mining.js"})
```

### B-P2 — ядро драйвера P2.2–P2.5

| Параметр | Значение |
|:--|:--|
| Model | Sonnet |
| Thinking | high — defensive parsing / crash recovery, effort high обязателен |
| Context | continue (/clear) — ручной item; перед серией /model sonnet + /effort high |
| Суть | Серия P2.2–P2.5 одной сессией (state-machine→parsing→recovery→resume), review full каждого |

```
/task:plan-run 2026.07.18-FOREMAN P2.2-P2.5
```

### B-P4 — эскалация+наблюдаемость P4.1,P4.2,P4.4 (plan-exec серия)

| Параметр | Значение |
|:--|:--|
| Model | Sonnet |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | Серия plan-exec P4.1→P4.2→P4.4 (notify+envelope→эскалация→mAInd-репорт); P4.3 — отдельно (opus, опц.) |

```
/task:plan-exec 2026.07.18-FOREMAN P4.1 P4.2 P4.4
```

### B-P5 — прогресс-движок P5.1–P5.4

| Параметр | Значение |
|:--|:--|
| Model | Opus (Fable по Execution Rules — несущий дизайн) |
| Thinking | high — модель прогресса/rulebook, наращивается с владельцем |
| Context | continue (/clear) — ручной item; /model opus + /effort high перед серией |
| Суть | Серия P5.1–P5.4 (детекция→решающая логика→rulebook→decision-лог); гейт владельца на rulebook P5.3 внутри |

```
/task:plan-run 2026.07.18-FOREMAN P5.1-P5.4
```

### B-P7 — стратегический канон, аудит+практика P7.1–P7.2 (BRAIN)

| Параметр | Значение |
|:--|:--|
| Model | Sonnet |
| Thinking | medium (fan-out дешёвыми, сводная классификация — старшей) |
| Context | continue (/clear) — ручной item; ИСПОЛНЯЕТСЯ В СЕССИИ BRAIN (не SKM) |
| Суть | Серия P7.1 (аудит читаемости) ∥ P7.2 (практика) одной BRAIN-сессией; lint — абсолютным путём + vault-путь плана |

```
/task:plan-run 2026.07.18-FOREMAN P7.1-P7.2
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P0.1 | имя пакета (OQ-1) | префикс путей всего пакета/раскатки |
| P0.5 | каталог принципов | сид философия-полей P0.3 / скилла P3.3 / rulebook P5.3 |
| P1.3–P1.4 | contribution журнала в пакет task | канон журнала для всего флота |
| P2.2–P2.5 | обзор ядра драйвера | — |
| P3.3 | директивы supervisor-protocol | промпты воркеров P2 / эскалация P4 / директивы P5 |
| P4.3 | Layer 3 remote (OQ-2) | опционально, решается по данным пилота P6.3 |
| P5.3 | rulebook прогресс-движка | правила оценки прогресса |
| P6.1 | contribution в harness (OQ-6) | дом rollout-конфигов |
| P6.3 | вердикт пилота (GREEN/ATTENTION) | массовая раскатка на 5 проектов; OQ-2/OQ-4 |
| P7.3 | стратегический канон 00-Strategy | контекст корневого супервизора D11 |
| P7.4 | дом Brain-скилла (OQ-7) | раскатка скилла-указателя в проекты |
