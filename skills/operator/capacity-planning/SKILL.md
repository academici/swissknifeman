---
name: capacity-planning
bucket: operator
version: 0.1.0
description: Планирование capacity — load forecasting, headroom, autoscaling policy, cost budget, что мониторить, когда масштабироваться вверх/вниз
risk: draft
persona: operator
tags: [ops, observability]
requires: []
produces_for: []
outputs: ["03_Dev/Capacity_Plan.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Capacity Planning

Применять когда: сервис в проде, есть метрики нагрузки за ≥ 1 месяц, и стоит вопрос «выдержим ли мы next quarter / Black Friday / маркетинговую кампанию». Также — при подозрении на дорогую недогрузку (плати́м за idle железо).

Не применять: pre-prod, MVP без realistic traffic, либо при наличии корпоративного capacity-management процесса (используем, не дублируем).

---

## Когда НЕ применять

- < 1 месяц данных в проде (статистика ненадёжна)
- MVP с ручным масштабированием раз в полгода — overhead не оправдан
- Полностью serverless с pay-per-request и без bottleneck'ов от downstream (capacity = деньги, не ресурсы)
- Внутренний tool с предсказуемой нагрузкой (10 юзеров, одинаковый паттерн) — достаточно одной оценки

---

## Шаг 1. Что вообще измерять

Capacity ≠ «сколько CPU». Это N измерений одновременно.

| Ресурс | Что меряем | Bottleneck признак |
|:---|:---|:---|
| **CPU** | % утилизации (avg + p95) | > 70% sustained |
| **Memory** | RSS / heap utilization | > 80% либо OOM kills |
| **Network** | bandwidth in/out, connections | > 70% NIC, либо port exhaustion |
| **Disk I/O** | IOPS, throughput, queue depth | queue depth растёт |
| **Disk space** | free GB + growth rate | < 30 days runway |
| **DB connections** | active / max | > 80% |
| **External rate limits** | requests vs quota | > 70% quota |
| **Latency under load** | p50/p95/p99 vs RPS | p99 нелинейно растёт |

**Правило:** capacity всегда multi-dimensional. Авто-scaling по одной метрике (CPU) — частая ошибка.

---

## Шаг 2. Headroom — сколько запаса

| Тип нагрузки | Headroom | Обоснование |
|:---|:---:|:---|
| Steady predictable | 30% | Защита от minor spike |
| Bursty (B2C, ритейл) | 50-70% | Burst может быть x3-5 |
| Сезонный (Black Friday, налоговый период) | 100%+ за 2 недели до | Не растягиваем масштабирование на день X |
| Critical (платежи, login) | ≥ 50% всегда | Цена downtime > цена headroom |
| Background / batch | 10-20% | Не критично, перезапустится |

**Trade-off:** headroom = деньги. Слишком много — жжём бюджет. Слишком мало — page on-call.

---

## Шаг 3. Load forecasting

3 горизонта прогноза:

| Горизонт | Метод | Источники |
|:---|:---|:---|
| **Tactical** (1-2 недели) | Тренд + сезонность из метрик | Дашборд + business calendar |
| **Quarterly** | Growth rate × current peak | Метрики + sales / marketing pipeline |
| **Annual** | Бизнес-план + capacity per unit | Business plan + per-user resource cost |

**Простая модель:**
```
forecast_peak = current_peak × (1 + monthly_growth)^months × seasonal_factor
required_capacity = forecast_peak × (1 + headroom)
```

Где `seasonal_factor` для известных событий (BF, Q4, launches) — из истории либо консервативная оценка x2-x3.

---

## Шаг 4. Autoscaling policy

| Policy | Когда | Подводные камни |
|:---|:---|:---|
| **Manual** | Стабильная нагрузка, малые амплитуды | Page on-call при spike |
| **Reactive (HPA по CPU/mem)** | Стандартный B2C | Лаг масштабирования + cold start |
| **Predictive scheduled** | Известные паттерны (рабочий день, BF) | Не помогает при unexpected spike |
| **Predictive ML** | Большие amplitudes, есть данные | Сложно поддерживать |
| **Гибрид (scheduled + reactive)** | Production-серьёзный | Самый сложный для дебага |

**Параметры autoscaling — обязательно фиксировать:**
- Trigger metric (что замеряем)
- Threshold (когда срабатывает)
- Cooldown (между scale events)
- Min replicas / max replicas (защита от runaway scaling — и вниз, и вверх)
- Scale-down policy жёстче чем scale-up (не дёргать)

**Runaway risks:**
- Авто-scale без max limit → один кривой запрос даст $10K в час AWS bill
- Авто-scale-down при метрике, которая drop'ается из-за инцидента → cascading failure
- HPA + cluster autoscaler без quota → выедают availability zone

---

## Шаг 5. Cost budget — связка с capacity

Capacity-планирование без бюджета — академия.

| Стоит замерять | Зачем |
|:---|:---|
| Cost per request / cost per user | Unit economics для PM/founder |
| Cost per service per month | Bottom-up бюджет |
| Cost share idle vs working | Headroom efficiency |
| Cost growth rate vs revenue growth rate | Здоровье бизнес-модели |

**Связка:** capacity_plan → required spend → должно укладываться в budget от founder/PM. Если не укладывается — вверх по эскалации (это решение о бизнес-модели, не операционное).

---

## Шаг 6. Pre-event protocol (запуск, BF, marketing push)

За **2 недели до** ожидаемого spike:

1. **Forecast:** ожидаемая пиковая нагрузка x2 от прогноза (запас)
2. **Pre-scale:** поднять capacity до forecast уровня заранее (не доверять авто-скейлу на cold start)
3. **Load test:** прогнать synthetic нагрузку на realistic данных
4. **Failure injection:** chaos engineering на ключевых компонентах
5. **Game day:** табличный обход сценариев с командой
6. **War room:** на момент запуска — выделенный channel, IC заранее, runbook'и под рукой
7. **Stand-by autoscaling:** max replicas повышен временно
8. **Post-event review:** что фактически случилось vs прогноз — для калибровки следующего раза

---

## Что агент добавляет сам

- Конкретная формула forecast с подстановкой текущих метрик (если переданы)
- Рекомендация autoscaling policy под стек (Kubernetes HPA / AWS ASG / serverless)
- Связка с `observability-design`: какие SLO метрики используем для capacity decisions
- Связка с `incident-response`: incident'ы из-за capacity issues — отдельная классификация в postmortem
- Чек-лист «pre-event readiness» (8 пунктов выше — готовый чек-бокс)
- Подсказка про cost monitoring: AWS Cost Explorer / GCP Billing / Datadog Cost Management — выбор по стеку

---

## Структура output-файла `Capacity_Plan.md`

```markdown
# Capacity Plan: [ProjectName] — [Quarter/Year]

## 1. Текущая нагрузка (snapshot по 8 measurement dimensions)
## 2. Bottleneck analysis (где упрёмся первым)
## 3. Headroom policy (per service)
## 4. Forecast (tactical / quarterly / annual)
## 5. Autoscaling policy (per service)
## 6. Cost budget (current spend + projected)
## 7. Pre-event protocols (для известных событий — BF, launches)
## 8. Review cadence (как часто пересматриваем — обычно quarterly)
## 9. Open risks / known limits (что не сможем масштабировать — например, monolithic DB)
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Авто-scaling без `max replicas` (runaway cost)
- Capacity planning без cost component (только техническая часть)
- Forecast на основе одного месяца данных (нет сезонности)
- Принимать capacity-решение которое нарушает SLO (если headroom меньше — обозначить как risk)
- Пытаться предсказать ML-моделями без устойчивой baseline-модели сначала (overfitting)
- Pre-event без load test (надежда — не план)
- Игнорировать downstream rate limits (свой сервис горизонтально масштабировали — vendor нас прибьёт rate limit'ом)
- Считать что serverless = «нет capacity-проблем» (есть: concurrent executions, downstream connections, cost)
