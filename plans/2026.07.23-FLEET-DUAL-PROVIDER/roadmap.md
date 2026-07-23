# Roadmap исполнения — 2026.07.23-FLEET-DUAL-PROVIDER

**Обновлён:** 2026-07-23 · **Соответствует plan.md:** v0.3.0

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-run | frontier/high | — | 🟢 attempt 3 закрыт: generated core содержит runtime tree; объединять нельзя |
| P0.2 | solo | plan-run | implementation/high | — | меняет fleet eligibility semantics |
| P1.1 | solo | plan-run | implementation/high | — | D6 owning repair, D7 no-write selection, один external consumer apply |
| P1.2 | conditional solo | plan-run | implementation/high | D6/frozen-contract change only | только новый defect после D6; retry того же selected project |
| P2.1 | solo | plan-run | implementation/high | — | последовательный external-state loop с stop-on-defect |

## Готовые launch-block'и групп

### P0.2 — regression и fleet dry-run

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | Проверить package regression и повторить no-write fleet dry-run с provider-qualified skip evidence. |

```
$ task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P0.2
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P1.2 escalation | Только изменение frozen provider contract | P2 до новой D-записи |

### P1.1 — replacement pilot

**Next:** run-items: task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P1.1

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | same-session — item |
| Суть | Реализовать D6, выбрать первый D7-compatible external pilot и применить только его. |

```text
$ task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P1.1
```
