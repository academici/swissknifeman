---
name: pmf-diagnostics
bucket: pm
version: 0.1.0
description: Диагностика product-market fit — measurement framework до launch, Sean Ellis test (>40%), effort test, retention D1/7/30, false-positive паттерны, pivot-диагностика
risk: draft
persona: pm
tags: [validation, market]
requires: [product-roadmap]
produces_for: []
outputs: ["docs/01_Business/PMF_Diagnostics.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: PMF Diagnostics

Применять когда: MVP в руках реальных пользователей и нужно понять, **достигнут ли PMF** (exit-критерий MVP-стадии) — или это false positive. Также: настроить measurement framework **до** первого пользователя.

Главная ловушка: те, кто mis-identify early traction как PMF — обычно те, кто начал мерить **после** launch, выбрав метрики «что работало», а не «что нет». **Antidote: measurement framework до первого юзера.**

---

## Когда НЕ применять

- Ещё нет работающего MVP с реальными юзерами (стадия idea) — это `customer-discovery`.
- Нужен roadmap/scope, а не диагностика — это `product-roadmap`.

---

## 1. Measurement framework (ставить ДО launch)

До первого пользователя определить:
- **Retention benchmarks** под тип продукта.
- **Activation criteria** — что считается «активирован».
- **Day 1 / Day 7 / Day 30 targets** — конкретные числа заранее.
- **Что есть false positive именно для этого продукта** (см. ниже).

Когда данные придут — попросить AI построить **adversarial-кейс против** собственной traction: «что сказал бы скептик про эти числа?» (`adversarial-check`).

## 2. Сигналы PMF (настоящие)

- **Sean Ellis test:** «как бы ты себя чувствовал, если бы больше не мог пользоваться продуктом?» → **>40% "very disappointed"** = осмысленный PMF-индикатор.
- **Effort test:** pre-PMF retention требует constant intervention (частый outreach, incentives, личный follow-up, героическая энергия фаундера). Post-PMF — продукт **тянет сам** (pulling, не pushing). Сдвиг от push к pull = один из чистейших сигналов.
- **Retention plateau:** кривая удержания выходит на плато (а не падает в ноль) на нескольких когортах.
- Organic referral без incentive; пользователи находят use cases, которых не планировали.

> Ни одна точка не подтверждает PMF — это **паттерн через несколько iteration-циклов**.

## 3. False positives (anti-patterns)

- **Signups без activation.**
- **Revenue без retention** (single-purchase, нет повтора).
- **Enthusiasm без repeat usage.**
- **Launch spike ≠ sustained interest** — энергия от друзей фаундера, portfolio-компаний инвестора, Hacker News headline. Ничто из этого не предсказывает неделю 6/12.

## 4. Iterate toward evidence, not completeness

MVP-стадия кончается при genuine evidence PMF — независимо от того, насколько «законченным» ощущается продукт. Декларация PMF = judgement, комбинирующий founder intuition с собранными доказательствами, через **несколько** iteration cycles.

## 5. Pivot-диагностика (если 3+ итерации без движения к PMF)

Скормить retention-данные + user feedback + исходную гипотезу проблемы и задать **3 вопроса**:
1. Есть ли сегмент, реагирующий **иначе** остальных? (может, правильная аудитория уже в данных, просто underweighted)
2. Gap между designed value и experienced value — это **positioning** проблема или **product** проблема? (разные стратегии fix)
3. Что должно быть правдой, чтобы текущий продукт нашёл genuine PMF — и реалистично ли это?

Ответы определяют: **adjust** (onboarding/messaging/emphasis) / **pivot** (сегмент или гипотеза) / **return to Idea stage**.
Несовпадение результатов с ожиданием — **не провал, а работающая система**: MVP-стадия для того и спроектирована, чтобы вскрыть это до over-invest в неверный ответ.

---

## Структура output-файла

`docs/01_Business/PMF_Diagnostics.md`:

```markdown
---
project: [ProjectName]
stage: mvp
created: YYYY-MM-DD
---

# PMF Diagnostics — [ProjectName]

## Measurement framework (до launch)
- Activation: … | Retention D1/D7/D30 targets: … | False positive = …

## Текущие данные
| Метрика | Target | Факт | Вердикт |
|---|---|---|---|
| Sean Ellis "very disappointed" | >40% | … | … |
| Effort: push vs pull | pull | … | … |
| Retention D30 | … | … | … |

## False-positive check
- signups без activation? revenue без retention? launch spike? → …

## Adversarial (скептик про эти числа)
- …

## Вердикт
PMF достигнут / не достигнут / нужна pivot-диагностика
[если 3+ итерации без движения — 3 вопроса + adjust/pivot/return]
```

---

## Что агент добавляет сам

- **Realistic benchmarks по типу продукта** (B2B SaaS vs consumer vs marketplace — разные нормы retention).
- **Flag метрик тщеславия.** Если фокус на signups/downloads — переориентировать на retention/activation.
- **Связь с roadmap.** Если PMF не достигнут — какой scope-эксперимент следующий (`product-roadmap`).

---

## Связанные скиллы

- `pm/product-roadmap` — **requires**: фазовые ворота и success-метрики; pmf-diagnostics уточняет MVP-exit
- `founder/customer-discovery` — предшественник (Idea-валидация); pmf-diagnostics — её MVP-аналог
- `founder/adversarial-check` — adversarial-кейс против собственной traction
- `founder/startup-lifecycle` — pmf-diagnostics закрывает MVP→Launch gate
- `pm/unit-economics` — смежные метрики (LTV/CAC) для Launch-готовности
