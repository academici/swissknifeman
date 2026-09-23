# Roadmap исполнения — <PLAN-ID>

<!-- execution-sheet/v1 -->

<!-- Живая карта «что запускать дальше», не второй план. Roadmap группирует только ready
     adjacent items с совместимым scope/route; локальный порядок остаётся адаптивным в sealed
     contract. Она не переопределяет Routing §3, owner gates или material-review trigger. -->

**Обновлён:** <YYYY-MM-DD> · **Соответствует plan.md:** v<X.Y.Z>

## Правило группировки

- Сначала ищи связную adjacent-цепочку одной фазы: общий producer/consumer, файлы,
  Required Reads, setup или Validation. Объединяй, когда reuse сокращает время и токены.
- Не атомизируй из-за отдельных коммитов/Deliverables: per-item lifecycle сохраняется внутри batch.
- `solo` допустим только с конкретной причиной: несовместимый Exec, owner/irreversible gate,
  отдельная capability/hard boundary или ожидаемое переполнение контекста.
- Batch не пересекает phase audit/close; launch использует максимум route/review и union capabilities.
- Phase design предлагает группы; design finish пересчитывает их по всему dependency graph.
- Конкретные provider model selectors в Routing запрещены; один semantic maximum
  даёт provider adapter одну модель на весь admission.

## Execution sheet — единственный источник launch-команд

<!-- Finish валидирует exact row для каждого compiled batch. -->

| Command | Unified route | Review |
|:--|:--|:--|
| `task:plan-exec <PLAN-ID> P0.1 P0.2` | `implementation/medium` | `light` |
| `task:plan-run <PLAN-ID> P1.1` | `frontier/high` | `full` |

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P0.1 | B1 | plan-exec серия | implementation/medium | — | ready adjacent scope |
| P0.2 | B1 | ↑ | implementation/medium | — | shared validation boundary |
| P1.1 | solo | plan-run (manual) | frontier/high | ✅ утверждение матрицы | owner gate исключает безопасную цепочку |
| P2.1–P2.3 | W1 | orchestration | implementation/medium | — | independent scope and declared capability |
| … | | | | | |

## Готовые launch-block'и групп

### B1 — <суть батча>

| Параметр | Значение |
|:--|:--|
| Batch | B1 |
| Model class | <economy / implementation / frontier> |
| Effort | <low / medium / high / xhigh> — <причина> |
| Capabilities | <semantic capability IDs> |
| Context | continue-root |
| Суть | Серия <Pn.a>–<Pn.b> одной сессией, гейты между items — внутри сессии |

```
exec-items: task:plan-exec <PLAN-ID> <Pn.a> <Pn.b> <Pn.c>
```

<!-- Батч-серии — ТОЛЬКО через plan-exec (список items): её минимум
     implementation/medium — жёсткий гейт тира. task:plan-run — inherited-plan,
     для manual design-items под проверенным route сессии. -->

### W1 — <суть workflow-группы>

```
kind: orchestration
orchestration_id: <PLAN-ID>:W1
inputs: [plan.md, roadmap.md, phases/<Pn>/<Pn>.md]
required_capabilities: [command.subagents, command.workflow-carrier]
provider_projection: <verified mapping reference>
```

## Гейты владельца (сводно)

| Где | Что утверждает | Блокирует |
|---|---|---|
| <Pn.m> | <артефакт> | <какие batch'и ждут> |
