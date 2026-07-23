# Индекс — 2026.07.23-FLEET-DUAL-PROVIDER

**Обновлён:** 2026-07-23

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мастер-план и статусы |
| `phases/` | исполнимые фазы |
| `handoff.md` | rolling-указатель следующего шага |
| `journal.jsonl` | append-only история plan-операций |
| `brief/` | исходный запрос владельца |
| `findings/` | dry-run evidence |
| `research/` | синтез rollout-механизма |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `findings/00-fleet-dry-run-2026-07-23.md` | findings | `P0` | наблюдаемый Codex connect blocker и безопасные границы |
| `research/00-rollout-design.md` | research | `P0.1` | последовательность fix-forward rollout |
