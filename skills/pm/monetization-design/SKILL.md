---
name: monetization-design
bucket: pm
version: 0.1.0
description: Выбор бизнес-модели (SaaS / marketplace / ads / freemium / hybrid) с trade-off матрицей и обоснованием
risk: draft
persona: pm
tags: [monetization]
requires: [idea-discovery]
produces_for: [unit-economics, go-to-market, brd]
outputs: ["docs/01_Business/03_Monetization_Model.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Monetization Design

Применять когда: нужно **выбрать** модель монетизации до расчёта unit-economics. Не путать с `unit-economics` — там уже считают LTV/CAC при выбранной модели.

Должен быть **выполнен после `idea-discovery`** (нужен JTBD и сегмент) и **до `unit-economics`** (без модели нечего считать).

---

## Когда НЕ применять

- Модель уже зафиксирована в `docs/01_Business/01_Concept_and_Monetization.md` — пропустить.
- Open-source проект без коммерции (BrainKit, AzGuard) — не применимо.
- Пользователь уже знает модель и просит её обосновать — это `unit-economics` + `go-to-market`, не выбор.

---

## 6 базовых моделей (рассматривать как минимум)

| Модель | Когда подходит | Когда НЕ подходит |
|:---|:---|:---|
| **SaaS subscription** | Регулярная боль, retention >40% MoM | Разовая транзакция, B2C low-frequency |
| **Marketplace (take-rate)** | Two-sided, supply есть, GMV растёт | Тонкая маржа поставщика, mono-side |
| **Transactional / pay-per-use** | Спорадичный спрос, низкий commitment | High-frequency без budget cap |
| **Ads / affiliate** | Большой охват, низкая монетизация на user | Премиум-аудитория, B2B, < 100k MAU |
| **Freemium** | Сильный network effect или demo-эффект | Дорогой serving cost, B2B без champion |
| **Open-core / license** | DevTool, infra, OSS-проект с компанией | B2C, SaaS-only |

**Hybrid** допустим (например, freemium + affiliate). Указывать явно какой layer первичен.

---

## Алгоритм выбора (4 шага)

### Шаг 1. Отсев по JTBD
Из `00_Idea_Discovery.md` взять JTBD и частоту:
- **Daily/weekly job** → SaaS / freemium / ads
- **Monthly+ job** → transactional / marketplace
- **Project-based job** → license / per-project

### Шаг 2. Отсев по сегменту
- **B2C mass** → ads / freemium / transactional
- **B2C premium** → SaaS / transactional
- **B2B SMB** → SaaS / freemium
- **B2B Enterprise** → SaaS + license
- **Developer tool** → open-core / SaaS

### Шаг 3. Trade-off матрица (обязательна в output)

Для **минимум 3 моделей**, прошедших отсев, заполнить:

| Критерий | Модель A | Модель B | Модель C |
|:---|:---|:---|:---|
| Time-to-revenue | | | |
| Predictability дохода | | | |
| CAC payback (оценочно) | | | |
| Зависимость от объёма (network effect нужен?) | | | |
| Регуляторные риски | | | |
| Сложность инфры | | | |
| Психология платежа (легко ли платить?) | | | |
| Зрелость аналогов (есть ли на рынке?) | | | |

### Шаг 4. Рекомендация + миграционный путь
- **Стартовая модель** на MVP — одна, явно.
- **Через 6–12 месяцев** — куда мигрировать (если планируется).
- **Триггер миграции** — конкретная метрика (например, «при MAU > 50k и retention > 35% включаем freemium → paid»).

---

## Что агент добавляет сам

- **Антипаттерны для отрасли.** Например, для EdTech (Edufy) — не делать pure-ads; для финтеха (Finbrain) — не делать B2C freemium без compliance.
- **Психология ценообразования.** Anchor, decoy, 9-endings — называть явно когда применимо.
- **Скрытые издержки модели.** Marketplace требует support двух сторон; freemium — high serving cost; ads — рекламные SDK с privacy-проблемами.
- **Влияние на product roadmap.** Какие фичи становятся обязательными при выбранной модели (биллинг, invoicing, paywall, dispute resolution).

---

## Структура output-файла

`docs/01_Business/03_Monetization_Model.md`:

```markdown
---
project: [ProjectName]
stage: monetization-design
requires_input_from: 00_Idea_Discovery.md
produces_input_for: [04_Unit_Economics.md, 06_Go_To_Market.md, BRD.md]
---

# Monetization Model — [ProjectName]

## Контекст
- JTBD: ...
- Сегмент: ...
- Частота job: ...

## Рассмотренные модели
[список после отсева — минимум 3]

## Trade-off матрица
[таблица по критериям]

## Рекомендация
**Стартовая модель:** [X]
**Обоснование:** [3–5 пунктов]

## Миграционный путь
- T0: [модель]
- T+6–12 мес: [модель] при триггере [метрика]

## Анти-паттерны для этого домена (агент)
- ...

## Влияние на roadmap / BRD
- Обязательные фичи: ...
- Compliance-требования: ...

## Следующий шаг
→ `.ai/skills/pm/unit-economics.md` (расчёт LTV/CAC для выбранной модели)
```

---

## Жёсткие запреты на этой стадии

НЕЛЬЗЯ:
- Считать конкретные цены и LTV/CAC — это `unit-economics`
- Расписывать каналы привлечения — это `go-to-market`
- Решать, на каком фреймворке делать биллинг — это `architecture`

Только **выбор модели** и **trade-off обоснование**.
