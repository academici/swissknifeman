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

Opt-in env-блок в пресетах harness (merge-only запись, не хардкод endpoint'а). Список
переверифицирован RAG 2026-07-12 (context.claude.com/docs/en/monitoring-usage, официальная
таблица + perplexity-web кросс-проверка) — полнее черновика P5.4:

**Базовое включение:**
```
CLAUDE_CODE_ENABLE_TELEMETRY=1
OTEL_METRICS_EXPORTER=otlp
OTEL_LOGS_EXPORTER=otlp
OTEL_TRACES_EXPORTER=otlp
CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1      # span-трейсинг (бета); алиас ENABLE_ENHANCED_TELEMETRY_BETA
OTEL_LOG_TOOL_DETAILS=1                     # tool-параметры, MCP/skill/workflow имена
OTEL_RESOURCE_ATTRIBUTES=project=<id>       # разрез по проектам, без пробелов в значениях
```

**OTLP-эндпоинт (плейсхолдер, НЕ хардкод):**
```
OTEL_EXPORTER_OTLP_PROTOCOL=grpc|http/json|http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=<коллектор>     # напр. http://localhost:4317
```
Per-signal override при необходимости: `OTEL_EXPORTER_OTLP_{METRICS,LOGS,TRACES}_{PROTOCOL,ENDPOINT}`.

**Детальное логирование (каждое — отдельный opt-in, по умолчанию выключено; ОСТОРОЖНО —
контент промптов/ответов):**
```
OTEL_LOG_USER_PROMPTS=1        # текст промптов пользователя
OTEL_LOG_ASSISTANT_RESPONSES=1 # текст ответов ассистента
OTEL_LOG_TOOL_CONTENT=1        # ввод/вывод тулов в span events (обрезка 60KB, требует трейсинг)
OTEL_LOG_RAW_API_BODIES=1|file:<dir>  # сырые Anthropic Messages API JSON (обрезка 60KB / без обрезки на диск)
```
Harness-пресет НЕ должен включать эту группу по умолчанию даже при `--otel on` — слишком
чувствительно (утечка контента в коллектор); отдельный явный флаг, если вообще заводить.

**Интервалы экспорта (опционально, дефолты обычно ок):** `OTEL_METRIC_EXPORT_INTERVAL`
(60000мс) · `OTEL_LOGS_EXPORT_INTERVAL`/`OTEL_TRACES_EXPORT_INTERVAL` (5000мс).

**Кардинальность метрик (опционально):** `OTEL_METRICS_INCLUDE_SESSION_ID` (true по
умолчанию) · `_INCLUDE_VERSION`/`_INCLUDE_ACCOUNT_UUID`/`_INCLUDE_ENTRYPOINT`/
`_INCLUDE_RESOURCE_ATTRIBUTES`.

**mTLS (если коллектор требует):** `OTEL_EXPORTER_OTLP_CERTIFICATE`/`_CLIENT_CERTIFICATE`/
`_CLIENT_KEY` (gRPC) либо `CLAUDE_CODE_CLIENT_CERT`/`_CLIENT_KEY`/`_CLIENT_KEY_PASSPHRASE`/
`NODE_EXTRA_CA_CERTS` (HTTP).

Применяется через существующий merge-механизм permissions/settings harness (не изобретать
вторую систему записи). Тест: tmpdir settings → env-блок появился, существующее не затёрто.

**Уточнение область действия:** переменные документированы для **Claude Code (CLI)** —
официальная страница НЕ упоминает ограничение по плану (Pro/Team/Enterprise), доступны всем.
Не путать с OTel-мониторингом активности **Claude Cowork** (отдельный продукт — агентский
task-runner в Desktop/web/mobile для non-coding задач) — та org-level телеметрия
документирована только для Team/Enterprise-админов и к нашему CLI-контуру не относится.

## Критерий возврата

Появление реального OTLP-коллектора (self-hosted или SaaS), который кто-то из владельцев
экосистемы готов держать/оплачивать — тогда реализация дешёвая (набросок выше), просто нет
смысла делать её раньше спроса.

## Источник

`plans/2026.07.12-CONTEXT-ECONOMY/phases/P5.md` (P5.4, Inputs: D7) ·
`plans/2026.07.12-CONTEXT-ECONOMY/findings/P0-rag-context-economy.md` (раздел телеметрии) ·
RAG-повторная верификация 2026-07-12 (post-релиз v0.9.0): официальная таблица env-переменных
`code.claude.com/docs/en/monitoring-usage` (WebFetch) + `perplexity-web` (уточнение
Cowork vs Claude Code, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` — существует, но только во
вторичных источниках, не в официальной таблице, в набросок выше не включён по этой причине).
