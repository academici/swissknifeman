---
name: observability-design
bucket: architect
version: 0.1.0
description: Logging, metrics, tracing, alerting. SLO/SLI, error budget, runbooks для прод-готовности
risk: draft
persona: architect
tags: [observability]
requires: [architecture]
produces_for: []
outputs: ["03_Dev/Observability_Design.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Observability Design

Применять когда: архитектура утверждена, нужно спроектировать прод-наблюдаемость **до** деплоя. Не «прикрутим логи когда упадёт» — спроектировать осознанно.

Покрывает 4 столпа: **logs, metrics, traces, alerts** + SLO/SLI + runbooks.

---

## Когда НЕ применять

- Архитектура не утверждена → отказать, идти на `architecture`.
- Pre-prototype / hello-world — overkill. Применять с момента «есть реальные пользователи».
- OSS-библиотека без deploy (BrainKit как пакет) — не применимо. Для OSS-сервиса (AzGuard как daemon) — применимо.
- Просто «добавить sentry» — это не observability design, это task в roadmap.

---

## 4 столпа observability

### 1. Logs
**Что:** структурированные события с контекстом.
**Решения:**
- Уровни: ERROR / WARN / INFO / DEBUG — когда что писать
- Формат: JSON со схемой (timestamp, level, service, trace_id, user_id, message, attrs)
- Где: stdout → агрегатор (Loki / CloudWatch / Datadog / Better Stack)
- Retention: hot (7d) / warm (30d) / cold (1y по compliance)
- PII в логах: **запретить** или **обязательная маскировка** (см. `security-design`)

### 2. Metrics
**Что:** агрегированные числа во времени.
**Категории:**
- **RED** (для request-driven): Rate, Errors, Duration — на каждый эндпоинт
- **USE** (для resources): Utilization, Saturation, Errors — на CPU/RAM/disk/network/DB-pool
- **Business KPI**: MRR, активные пользователи, конверсия — отдельный dashboard
- **Custom domain**: для AI-проектов — token usage, latency per model, hallucination rate (см. `eval-design`)

### 3. Traces
**Что:** путь одного запроса через все компоненты.
**Решения:**
- Стандарт: OpenTelemetry (по умолчанию)
- Sampling: head-based (1–10%) или tail-based (100% ошибок, 1% успехов)
- Что трейсить обязательно: входящие HTTP, исходящие HTTP, БД-запросы, queue messages, LLM-вызовы
- Trace_id propagation: через все service-границы (включая background jobs)

### 4. Alerts
**Что:** автоматические сигналы о деградации.
**Принципы:**
- Алерт = action required. Если нет действия — не алерт, это дашборд.
- Severity tiers: P1 (paging, 24/7) / P2 (рабочее время) / P3 (тикет)
- Каждому алерту — runbook (см. ниже)
- Запретить flaky alerts: после 3-го ложного срабатывания — переделать или удалить

---

## SLO / SLI / Error budget

Минимум для прод-готовности — определить:

| Сервис | SLI | SLO target | Error budget (30d) |
|:---|:---|:---|:---|
| API gateway | availability | 99.9% | 43.2 мин down |
| API gateway | latency p95 | < 300ms | < 5% запросов выше |
| Background jobs | success rate | 99.5% | 0.5% failed |
| LLM endpoint | success rate | 99% | 1% (модели падают) |

**Error budget policy:**
- Burn rate alerts: если за последний час сожгли >2% бюджета — P1
- Если месячный бюджет исчерпан — стоп фичам, чинить надёжность

---

## Cost-tier планирование

Observability не бесплатна. На pre-seed нельзя ставить Datadog full-stack — обанкротится.

**Tier 0 (pre-MVP, $0/мес):**
- Logs: stdout + cloud-native сборщик (CloudWatch / Vercel logs)
- Metrics: hand-rolled через prometheus exporter
- Traces: skip или 1% sampling в OTel-collector
- Alerts: cron-based health checks

**Tier 1 (MVP в проде, ~$50/мес):**
- Better Stack / Highlight / Sentry — единая платформа
- Trace sampling 10%, retention logs 7d

**Tier 2 (post-PMF, $200–500/мес):**
- Полный OTel stack: Tempo + Loki + Prometheus + Grafana (self-host)
- Или Datadog APM на критичных сервисах

Указать tier явно в Output. Не делать tier-2 на pre-seed.

---

## Runbooks (operational playbook)

Для каждого P1-алерта — runbook `03_Dev/Runbooks/<alert_name>.md`:

```
1. Симптом (что видим)
2. Возможные причины (топ-3)
3. Диагностические команды (curl, SQL, logs query)
4. Mitigation шаги (что сделать сейчас)
5. Root cause investigation (что проверить после)
6. Кому эскалировать
```

Без runbook алерт = panic. Делать runbook до включения алерта в прод.

---

## Что агент добавляет сам

- **AI/LLM-specific метрики.** Для Edufy / Memster / Finbrain — token cost, latency per provider, jailbreak attempts, hallucination eval-failures (см. `eval-design`).
- **Privacy-aware logging.** Связать с `security-design` — PII не должно попадать в логи, маскировать email/phone/PAN.
- **Cost guardrails.** Логи и трейсы умеют генерировать $$$ — указать alert на превышение бюджета observability.
- **Multi-tenant**, если есть — отделить логи и метрики per tenant. Без этого debug одного клиента = ад.

---

## Структура output-файла

`03_Dev/Observability_Design.md`:

```markdown
---
project: [ProjectName]
stage: observability-design
based_on: 03_Dev/Architecture_[Name].md
tier: 0 | 1 | 2
---

# Observability Design — [ProjectName]

## Tier и бюджет
**Tier:** [0/1/2]
**Месячный бюджет:** $[X]

## Logs
- Формат: JSON, поля: ...
- Уровни и правила использования
- Агрегатор: ...
- Retention: ...
- PII policy: ...

## Metrics
### RED (per endpoint)
- ...

### USE (per resource)
- ...

### Business KPI
- ...

### Domain-specific (AI / payments / etc)
- ...

## Traces
- Стандарт: OpenTelemetry
- Sampling: ...
- Обязательные span'ы: ...
- Propagation: ...

## Alerts
| Имя | Severity | Условие | Runbook |
|:---|:---|:---|:---|
| ... | P1 | ... | `03_Dev/Runbooks/...md` |

## SLO / SLI
| Сервис | SLI | Target | Error budget |
|:---|:---|:---|:---|

## Error budget policy
- ...

## Runbooks
[список созданных файлов в 03_Dev/Runbooks/]

## Domain-specific дополнения (агент)
- ...
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Алерт без runbook
- Алерт без severity
- Tier-2 (Datadog full-stack) на pre-seed без обоснования
- PII в логах без маскировки
- "Логи как-нибудь" — структурированный JSON обязателен
- Метрики без named labels / dimensions
- Trace_id не пропагируется через async / queue — ломает debug
