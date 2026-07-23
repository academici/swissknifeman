# Roadmap исполнения — 2026.07.23-FLEET-DUAL-PROVIDER

**Обновлён:** 2026-07-23 · **Соответствует plan.md:** v0.2.0

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | solo | plan-run | frontier/high | — | 🟡 attempt 3: owning generated core runtime tree; объединять нельзя |
| P0.2 | solo | plan-run | implementation/high | — | меняет fleet eligibility semantics |
| P1.1 | solo | plan-run | implementation/high | — | один consumer, внешнее состояние |
| P1.2 | conditional solo | plan-run | implementation/high | — | запускается только при P1.1 defect; retry того же project |
| P2.1 | solo | plan-run | implementation/high | — | последовательный external-state loop с stop-on-defect |

## Готовые launch-block'и групп

### P0.1 — carrier design

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | skills.repository |
| Context | same-session — item |
| Суть | Спроектировать project-scoped Codex connect carrier без global install. |

```
$ task:plan-run 2026.07.23-FLEET-DUAL-PROVIDER P0.1
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| P1.2 escalation | Только изменение frozen provider contract | P2 до новой D-записи |
