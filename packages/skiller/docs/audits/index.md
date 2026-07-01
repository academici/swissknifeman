# Аудиты каркаса — архив

Прогоны [framework-audit](../workflows/framework-audit) — периодической ревизии
agent-каркаса. По каждому: `*.raw.md` (вывод verbatim, неизменяемый) + `*.md` (триаж).

Решения из триажа уходят в [decisions-ledger](../agent-framework/decisions-ledger);
ledger-строка — в `packages/skiller/references/framework-audits.md`.

## Прогоны

| Дата | Тема | Raw | Триаж | Итог |
|---|---|---|---|---|
| 2026-06-23 | Universal framework (профили, генерация, AI Skills Index, rules, spec-first, task-graph) | [raw](./2026-06-23-universal-framework.raw) | [триаж](./2026-06-23-universal-framework) | absorb: hub-index, rules, spec-writer(опц), validate-agents; reject: движок, нумерация, file-lock, complexity |
| 2026-06-23 | Agent Teams + ponytail | [raw](./2026-06-23-agent-teams-ponytail.raw) | [триаж](./2026-06-23-agent-teams-ponytail) | accept: Agent Teams(v1), ponytail-дисциплина; reject: `extends:`/`@include`, skill-enforcement хук |
| 2026-07-01 | Инцидент: устойчивость workflow к rate-limit (single-browser, StructuredOutput-cap, server throttling) | — (пост-мортем) | [разбор](./2026-07-01-workflow-resilience-ratelimit) | absorb: wall-clock-дедлайн + no-progress watchdog, fail-fast на rate-limit, liveness-проверка оркестратором, малые батчи/solo-fallback, реестр single-instance MCP, честная телеметрия (deferred vs infra-failed) |

## Как добавить прогон

1. `framework-audit` промт в Perplexity (на вход — `framework-overview` + `decisions-ledger`).
2. Вывод → `<YYYY-MM-DD>-<тема>.raw.md` (verbatim).
3. Триаж → `<YYYY-MM-DD>-<тема>.md` (таблица absorb/reject + куда легло).
4. Строка сюда + в `decisions-ledger` + `references/framework-audits.md`.
