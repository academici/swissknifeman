# Roadmap: OTEL-пресет harness — opt-in телеметрия Claude Code

**Статус:** ⛔ Skipped by decision (D7, план `2026.07.12-CONTEXT-ECONOMY` P5.4, 2026-07-12) —
вынесено сюда стабом вместо реализации.

**Дом (при реализации):** `packages/harness` — пресет env-блока (по месту существующих
env-пресетов в `configs/claude-code/`), только opt-in.

## Проблема

Enhanced OTEL-traces Claude Code дают атрибуцию токенов per-хук/per-скилл/per-субагент —
то, что в инциденте `2026.07.12-CONTEXT-ECONOMY` пришлось восстанавливать вручную
(косвенной декомпозицией run-report/jsonl). Официальный стек (RAG:✅ 2026-07-12
`plans/2026.07.12-CONTEXT-ECONOMY/findings/P0-rag-context-economy.md`) закрыл бы это нативно.

## Почему отложено, а не сделано (D7)

1. Env-переменные без работающего OTLP-коллектора не дают эффекта — нужна отдельная
   инфраструктура (self-hosted Jaeger/Prometheus/Grafana либо облачный SaaS), которую
   `harness` (stdlib-only, без рантайм-зависимостей) не поставляет и не может поставлять.
2. На момент решения коллектор не развёрнут — фича была бы «готова», но неиспользуема:
   мёртвый код с тестом/доками, который со временем разъедется с апстримом (набор
   `OTEL_*`-переменных Claude Code может меняться между версиями).
3. Часть той же проблемы (кто ест токены) в релизе `2026.07.12-CONTEXT-ECONOMY` уже закрыта
   без внешней инфры — `skiller budget --first-turn` (P5.1), `maind doctor --context` (P5.2),
   `analyst sessions` (P5.3).
4. Соответствует общей философии репо: «Спекулятивное — в `roadmap/`. Фичу внедряем по
   факту измеренной проблемы, не на упреждение» (root `CLAUDE.md`).

## Набросок реализации (при возврате к item'у)

Opt-in env-блок в пресетах harness (merge-only запись, не хардкод endpoint'а):

```
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
OTEL_LOG_TOOL_DETAILS=1
OTEL_RESOURCE_ATTRIBUTES=project=<id>
```

`OTEL_EXPORTER_OTLP_ENDPOINT` — плейсхолдер-переменная, НЕ хардкод; без него/без запущенных
exporter'ов телеметрия не шлётся. Применяется через существующий merge-механизм
permissions/settings harness (не изобретать вторую систему записи). Тест: tmpdir settings →
env-блок появился, существующее не затёрто.

## Критерий возврата

Появление реального OTLP-коллектора (self-hosted или SaaS), который кто-то из владельцев
экосистемы готов держать/оплачивать — тогда реализация дешёвая (набросок выше), просто нет
смысла делать её раньше спроса.

## Источник

`plans/2026.07.12-CONTEXT-ECONOMY/phases/P5.md` (P5.4, Inputs: D7) ·
`plans/2026.07.12-CONTEXT-ECONOMY/findings/P0-rag-context-economy.md` (раздел телеметрии).
