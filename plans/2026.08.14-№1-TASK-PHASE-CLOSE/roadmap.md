# Roadmap исполнения — 2026.08.14-№1-TASK-PHASE-CLOSE

**Обновлён:** 2026-08-14 · **Соответствует plan.md:** v0.1.0

## Правило группировки

P1.1–P1.2 — adjacent producer/consumer с общими package reads, tests, generators и full
validation; они идут batch B1 с item lifecycle внутри одного root. P2.1 начинается
только после committed/audited phase P1 и мутирует другой plan root, поэтому он solo.
Батч не пересекает phase audit/close; оркестрация не заявлена.

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P1.1 | B1 | plan-exec series | implementation/high | — | schema/subject producer |
| P1.2 | B1 | ↑ | implementation/high | — | policy/publication consumer, full validation |
| P2.1 | solo | plan-exec | implementation/high | exact P1 fingerprint/gate | cross-plan recovery after P1 close |

## Готовые semantic launch-block'и

### B1 — assurance, subject and adaptive policy

| Параметр | Значение |
|:--|:--|
| Batch | B1 |
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue-root |
| Суть | Закрыть P1.1–P1.2 с item gates внутри одной package-root сессии |

```text
exec-items: task:plan-exec 2026.08.14-№1-TASK-PHASE-CLOSE P1.1 P1.2
```

### solo — P1 recovery

| Параметр | Значение |
|:--|:--|
| Batch | solo |
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | cold-start-root: audit-root-terminal |
| Суть | Переиспользовать target GREEN audit и закрыть только P1 bookkeeping |

```text
exec-items: task:plan-exec 2026.08.14-№1-TASK-PHASE-CLOSE P2.1
```

## Гейты владельца

| Где | Что утверждает | Блокирует |
|:--|:--|:--|
| P2.1 preflight | Ничего: exact machine gate, owner action не нужен | P2.1 mutation при любом mismatch |

Slice B/C не запускаются автоматически после этого плана; их trigger остаётся в source roadmap.
