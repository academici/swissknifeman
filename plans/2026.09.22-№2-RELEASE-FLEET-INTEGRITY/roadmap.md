# Roadmap исполнения — 2026.09.22-№2-RELEASE-FLEET-INTEGRITY

**Обновлён:** 2026-09-22 · **Соответствует plan.md:** Layout v2

## Правило группировки

- Единственный item выполняет весь scope непрерывно; независимый read-only discovery параллелен.
- Внутренние checkpoints не являются отдельными Task iterations.
- Финальная проверка пересчитывает evidence и не принимает generated peer как version truth.
- Review означает bounded independent review, а не отдельный phase audit без owner admission.

## Карта исполнения

| Итерация | Item | Batch | Запуск | Model class/Effort | Review | Гейт |
|:--|:--|:--|:--|:--|:--|:--|
| 1 | P1.1 | solo | manual | frontier/high | light | baseline + owning fix + local release + fleet migration + final gates |

## Текущий frontier

P1.1 — единственный runnable item и весь разрешённый workset.

## Гейты владельца (сводно)

| Граница | Когда нужен owner action | Без owner action |
|:--|:--|:--|
| User-owned consumer conflict | Managed command доказывает несовпадающий owner/preimage | Проект остаётся BLOCKED, файл не меняется |
| External release | Push, tag creation/push или GitHub Release | Локальный candidate и fleet могут быть полностью проверены |
