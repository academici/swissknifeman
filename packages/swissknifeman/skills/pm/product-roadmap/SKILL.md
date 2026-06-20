---
name: product-roadmap
bucket: pm
version: 0.1.0
description: MVP definition, Impact/Effort приоритизация, фазы MVP → v1 → v2 → Backlog, метрики перехода
risk: draft
persona: pm
tags: [requirements, gtm, market]
requires: [brd, go-to-market]
produces_for: []
outputs: ["docs/01_Business/07_Product_Roadmap.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Product Roadmap

Применять когда: задача на roadmap, MVP, фазы продукта, приоритизация фич, scope v1/v2.

---

## Принцип

Roadmap ≠ список всего что хочется. Roadmap = стратегические ставки в хронологии.
MVP = минимум, при котором пользователь получает ценность. Не "минимум работы для команды".

---

## Шаг 1. MVP Definition

Ответить на три вопроса:

1. **Кто** получает ценность от MVP? (конкретный ICP из `[[Go_To_Market]]`)
2. **Какую ценность** — один конкретный job-to-be-done
3. **Как будем знать, что MVP работает?** — метрика успеха

```markdown
## MVP Definition

**Пользователь:** [Кто конкретно]
**Job-to-be-done:** [Что хочет сделать]
**Proof of value:** [Как докажем, что ценность есть]
**Метрика успеха:** [Конкретная цифра через X недель]
**Out of scope MVP:** [Что явно не входит в MVP]
```

---

## Шаг 1.5. Scope guard: feature-amendment criteria

В эпоху agentic coding исчез традиционный forcing function против scope creep — стоимость engineering time. Фича теперь стоит afternoon вместо sprint, поэтому **zero-friction scope creep**: каждое добавление по отдельности защитимо, но продукт расползается за границы → потеря direction и momentum.

Антидот — **scope document до первой строки кода**, сдвигающий decision point:
- ❌ «Стоит ли это добавить?» (на это всегда «ну да, полезно»)
- ✅ «Критическая масса реальных пользователей сказала, что не получает ценности без этого?»

```markdown
## Scope guard
**Продукт делает:** [одно предложение — core]
**Продукт намеренно НЕ делает:** [список — важнее, чем in-scope]
**Feature-amendment criteria:** новая фича добавляется ТОЛЬКО если ___
  (конкретное доказательство от реальных пользователей, не founder-энтузиазм под видом product thinking)
```

Когда всплывает новая идея фичи — прогнать через критерий: это genuine signal от юзеров или энтузиазм? `adversarial-check` помогает отличить.

---

## Шаг 2. Приоритизация фич

Использовать матрицу Impact/Effort:

| Фича | Impact (1-5) | Effort (1-5) | Ratio | Фаза |
|:---|:---|:---|:---|:---|
| [Фича A] | 5 | 1 | 5.0 | ✅ MVP |
| [Фича B] | 4 | 2 | 2.0 | ✅ MVP |
| [Фича C] | 3 | 4 | 0.75 | 🔜 v1 |
| [Фича D] | 2 | 5 | 0.4 | ❌ Backlog |

**Правило:** MVP = всё с Ratio ≥ 2 и Impact ≥ 4.

---

## Шаг 3. Фазы

```markdown
## MVP (0 → первый платящий пользователь)
**Длительность:** [X недель]
**Фичи:**
- [Фича 1] — критично для core job
- [Фича 2] — без неё невозможно

**NOT в MVP:**
- [Перечисление]

---

## v1 (MVP → Product-Market Fit)
**Цель:** Retention ≥ 40% (Day 30), NPS ≥ 40
**Фичи:**
- [Фичи, улучшающие retention]
- [Основные болевые точки из feedback]

---

## v2 (PMF → Growth)
**Цель:** Включить growth-каналы
**Фичи:**
- [Фичи, улучшающие CAC: viral loop, referral, SEO]
- [Монетизация: тарифы, апселл]

---

## Backlog (когда-нибудь)
- [Всё остальное]
```

---

## Формат в документе

Размещать в `docs/01_Business/07_Product_Roadmap.md`

---

## Что агент добавляет сам

- "Quick wins" — фичи с высоким impact и минимальными усилиями, которые пользователь не упомянул
- Явное предупреждение если MVP слишком большой: "Это не MVP, это v1. MVP — это [меньше]"
- Связь с `[[Risk Register]]` — если фаза зависит от внешнего фактора
- Метрики перехода между фазами (когда считать фазу выполненной)

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Roadmap без метрики успеха для каждой фазы
- "Сначала сделаем всё, потом запустим" — запуск с MVP, итерации быстро
- Фичи без обоснования (зачем, для кого, что улучшает)
- Одновременно работать над retention И growth — строго последовательно

---

## Связанные скиллы

- `pm/brd` — вход: функциональные требования, из которых отбираются фичи MVP (требуется ДО roadmap).
- `pm/go-to-market` — источник ICP для MVP Definition и метрик перехода между фазами (требуется ДО roadmap).
- `pm/prd-from-brd` — RICE-приоритизация и версии stories питают разбивку по фазам.
- `pm/unit-economics` — метрики перехода (retention, CAC, LTV) на границах фаз сверять отсюда.
- `pm/pmf-diagnostics` — уточняет MVP-exit: метрика перехода MVP→v1 = genuine PMF (Sean Ellis, retention), не просто «первый платящий».
- `founder/startup-lifecycle` — рамка: MVP scope guard и фазовые ворота = механика Idea→MVP→Launch перехода.
- `founder/adversarial-check` — фильтр feature-amendment: genuine signal vs founder enthusiasm.
- `founder/risk-assessment` — `[[Risk Register]]`: если фаза зависит от внешнего риска, связать явно.
