---
name: unit-economics
bucket: pm
version: 0.1.0
description: Unit economics: LTV, CAC, payback, churn, break-even, 3 сценария
risk: draft
persona: pm
tags: [monetization]
requires: []
produces_for: [pitch-deck]
outputs: ["docs/01_Business/04_Unit_Economics.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Unit Economics

Применять когда: задача на unit economics, финансовую модель, LTV/CAC, break-even, монетизацию.

---

## Принцип

Unit economics = экономика одной единицы (1 пользователь, 1 заказ, 1 подписка).
Если unit economics отрицательная — масштабирование только ускоряет потерю денег.

---

## Обязательные метрики по модели монетизации

### SaaS / Подписка
| Метрика | Формула | Цель |
|:---|:---|:---|
| MRR | Платящих × ARPU | Рост MoM |
| LTV | ARPU × (1 / Churn%) | LTV > 3×CAC |
| CAC | Расходы на привлечение / Новые клиенты | Как можно ниже |
| LTV/CAC | LTV ÷ CAC | Цель: ≥ 3:1 |
| Payback period | CAC ÷ (ARPU × Gross margin%) | Цель: < 12 мес |
| Churn | Отток / База × 100 | < 5% monthly для SMB |

### Marketplace
| Метрика | Формула |
|:---|:---|
| GMV | Объём транзакций |
| Take rate | Комиссия / GMV |
| Net revenue | GMV × Take rate |
| CAC (supply / demand) | Отдельно для каждой стороны |

### Freemium / Consumer
| Метрика | Формула |
|:---|:---|
| Conversion rate | Платящие / Все пользователи |
| ARPU | Revenue / MAU |
| Revenue per cohort | Сколько приносит каждая когорта за 12 мес |

---

## Шаг 1. Текущее состояние

Заполнить таблицу с тем, что известно. Неизвестные = гипотезы с пометкой [оценка].

---

## Шаг 2. Break-even анализ

```
Break-even = Fixed costs / (Unit price - Variable cost per unit)
```

Показать: при каком числе пользователей/транзакций проект выходит в 0.
Добавить временную шкалу — через сколько месяцев при текущем темпе роста.

---

## Шаг 3. Сценарии

| Сценарий | Churn | CAC | Conversion | Break-even |
|:---|:---|:---|:---|:---|
| Пессимистичный | +50% | +50% | -30% | [мес] |
| Базовый | [текущее] | [текущее] | [текущее] | [мес] |
| Оптимистичный | -30% | -20% | +50% | [мес] |

---

## Формат в документе

Размещать в `docs/01_Business/04_Unit_Economics.md`

Структура:
```markdown
# Unit Economics: ProjectName

## Бизнес-модель: [тип]
## Ключевые метрики (текущие / прогноз)
[таблица]
## Break-even анализ
## Сценарный анализ
## Выводы: что нужно сделать для улучшения unit economics
```

---

## Красные флаги (называть явно)

- LTV < CAC → убыточный рост
- Payback period > 18 месяцев → проблемы с cash flow
- Churn > 10% monthly → "дырявое ведро"
- Gross margin < 40% → нет места для продаж и маркетинга
- Единственный канал привлечения → риск зависимости

---

## Что агент добавляет сам

- Сравнение с бенчмарками отрасли (SaaS: LTV/CAC ≥ 3, Churn < 5%)
- Предложение: какую метрику улучшить в первую очередь и как
- Связь с риском: если unit economics отрицательная → ссылка на `[[Risk Register]]`
