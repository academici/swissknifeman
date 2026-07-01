# Framework Audits — ledger периодических аудитов каркаса

Реестр прогонов аудита agent-каркаса (см. промт
`docs/skiller/workflows/framework-audit.md`). Дополняет [README](./README.md): тот —
про внешние источники скиллов, этот — про ревизии самого каркаса (агенты/хуки/
воркфлоу/hub) и проверенные факты Claude Code.

Архив прогонов: `docs/skiller/audits/`. Решения: `docs/skiller/agent-framework/decisions-ledger.md`.

## Статусы

| Статус | Значение |
|---|---|
| `triaged` | Прогон разобран, решения в decisions-ledger |
| `partially-absorbed` | Часть absorb-now реализована, часть отложена |
| `absorbed` | Все absorb-now пункты реализованы |

## Прогоны

| Дата | Тема | Архив | Статус | Ключевые решения |
|---|---|---|---|---|
| 2026-06-23 | Universal framework | `audits/2026-06-23-universal-framework` | triaged | absorb: hub-index-фикс, path-rules, spec-writer(опц), validate-agents; reject: Mustache-движок, нумерация файлов, file-lock, complexity-scoring |
| 2026-06-23 | Agent Teams + ponytail | `audits/2026-06-23-agent-teams-ponytail` | triaged | accept: Agent Teams(v1, CC≥2.1.178), ponytail-дисциплина; reject: `extends:`/`@include` агентов, skill-enforcement хук |
| 2026-07-01 | Workflow resilience (rate-limit incident) | `audits/2026-07-01-workflow-resilience-ratelimit` | triaged | accept: честные статусы green/deferred/infra-failed + fail-fast на null + батч-дефолт 2 + текст-маркер; P1 liveness внешним supervisor (доклад ~30 мин + PushNotification, опц. GHA cron-watchdog); reject: in-script wall-clock/`withDeadline` (песочница не даёт `Date.now()`/`setTimeout`/cancel) |

## Внешние источники, всплывшие в аудитах

| Источник | Из аудита | Решение |
|---|---|---|
| github/spec-kit | #1 | дисциплина опц.; внешний тулчейн (см. harness/integrations/spec-kit) |
| eyaltoledano/claude-task-master | #1 | defer; не принимать формат tasks.json |
| VoltAgent/awesome-claude-code-subagents | #1 | паттерны ролей — учтены; нумерация файлов отклонена |
| DietrichGebert/ponytail | #2 | дисциплину впитываем; внешний плагин не ставим (конфликт с boost) |
| Claude Code Agent Teams (офиц.) | #2 | accept v1 (Фаза 6) |
