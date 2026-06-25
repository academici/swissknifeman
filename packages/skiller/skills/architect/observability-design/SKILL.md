---
name: observability-design
bucket: architect
version: 0.1.0
description: Logging, metrics, tracing, alerting. SLO/SLI, error budget, runbooks для прод-готовности
risk: draft
persona: architect
tags: [observability, logging, metrics, tracing, alerting, slo, runbook]
requires: [architecture]
produces_for: [runbook, incident-response, capacity-planning]
outputs: ["docs/03_Dev/Observability_Design.md"]
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

4 столпа observability (logs/metrics/traces/events) подробно — [references/four-pillars.md](references/four-pillars.md).

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

Для каждого P1-алерта — runbook `docs/03_Dev/Runbooks/<alert_name>.md`:

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

`docs/03_Dev/Observability_Design.md`:

```markdown
---
project: [ProjectName]
stage: observability-design
based_on: docs/03_Dev/Architecture_[Name].md
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
| ... | P1 | ... | `docs/03_Dev/Runbooks/...md` |

## SLO / SLI
| Сервис | SLI | Target | Error budget |
|:---|:---|:---|:---|

## Error budget policy
- ...

## Runbooks
[список созданных файлов в docs/03_Dev/Runbooks/]

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

---

## Связанные скиллы

- `architect/architecture` — утверждённая архитектура как предусловие.
- `architect/security-design` — PII-policy в логах, маскировка email/phone/PAN.
- `architect/eval-design` — AI/LLM-метрики (token cost, hallucination rate) кормят прод-мониторинг (вход этого скилла).
- `operator/runbook` — детальный operational runbook на каждый P1/P2-алерт, спроектированный здесь (выход).
- `operator/incident-response` — процесс реагирования, опирающийся на severity и алерты отсюда (выход).
- `operator/capacity-planning` — что мониторить для масштабирования, на основе USE-метрик отсюда.
- `php/health-checks` — Laravel-реализация liveness/readiness (spatie/laravel-health) для дизайна отсюда.
