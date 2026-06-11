---
name: pitch-deck
bucket: founder
version: 0.1.0
description: 10-слайдовая инвесторская дека по канону YC/Sequoia на основе готовых артефактов проекта
risk: draft
persona: founder
tags: [gtm, market]
requires: [competitive-analysis, unit-economics, go-to-market]
produces_for: []
outputs: ["01_Business/08_Pitch_Deck.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Pitch Deck

Применять когда: пользователь просит «деку», «pitch», «питч», «инвесторскую презентацию» или явно идёт на раунд (pre-seed / seed / A).

Скилл пишет **markdown с описанием каждого слайда** — не PPTX. Экспорт в .pptx/.pdf делается отдельно через `document-generator` MCP (если попросят).

---

## Когда НЕ применять

- Нет готовой `competitive-analysis` и `unit-economics` — отказать, отправить пользователя выполнить эти скиллы первыми (дека из воздуха = вред).
- Просят internal deck для команды — это не pitch, делать обычный markdown без 10-slide канона.
- Pre-discovery стадия — дека до JTBD = карго-культ.

---

## Канон 10 слайдов (Sequoia / YC hybrid)

| # | Слайд | Что показать | Источник из vault |
|:---|:---|:---|:---|
| 1 | **Title** | Название, one-liner, контакты, дата | `ProjectName.md` |
| 2 | **Problem** | Кому больно, как сильно, цена нерешения | `00_Idea_Discovery.md` |
| 3 | **Solution** | Один экран MVP + как закрывает боль | `01_Concept_and_Monetization.md` + `BRD.md` |
| 4 | **Why now** | Тренд / технология / регуляция, окно возможностей | `02_Competitive_Analysis.md` + research |
| 5 | **Market size** | TAM / SAM / SOM с источниками | research (Perplexity `search_deep`) |
| 6 | **Competition** | Карта рынка + наш вектор атаки | `02_Competitive_Analysis.md` |
| 7 | **Product** | 2–3 ключевые фичи MVP + screenshot/wireframe | `BRD.md` + `07_Product_Roadmap.md` |
| 8 | **Business model** | Как зарабатываем + unit economics LTV/CAC | `03_Monetization_Model.md` + `04_Unit_Economics.md` |
| 9 | **Traction / GTM** | Что уже есть (пилоты, waitlist, MAU) + план запуска | `06_Go_To_Market.md` + текущие метрики |
| 10 | **Team + Ask** | Кто команда, сколько просим, на что, runway | пользователь |

**Опционально 11–12:**
- Roadmap (фазы из `07_Product_Roadmap.md`)
- Appendix: финмодель, технология deep-dive

---

## Правила слайдов

1. **Один тезис на слайд.** Не пытаться вместить два.
2. **Глаз читает 5 секунд.** Заголовок = главный тезис, не «Problem», а «3 из 4 SMB теряют 8 часов в неделю на X».
3. **Цифры > эпитеты.** «Быстро» = ничего; «3.2× быстрее аналогов» = тезис.
4. **Источники.** Каждое число на слайдах 4, 5, 6, 8, 9 — со ссылкой / приложением.
5. **Visual hierarchy.** Один главный объект, остальное — поддержка.

---

## Опросные вопросы ПЕРЕД написанием

- Стадия раунда (pre-seed / seed / A) — определяет глубину traction-слайда
- Сумма ask + runway (на сколько месяцев) + на что (R&D / GTM / hire)
- Команда: имена, роли, ключевой past experience
- Что есть из traction: MAU/MRR/LOI/пилоты/waitlist — конкретные цифры
- Целевая аудитория деки: VC / angel / accelerator (slight tweak на каждую)

---

## Что агент добавляет сам

- **Hook на слайде Problem.** Если боль формулируется слабо — переписать в формат «X людей теряют Y, потому что Z».
- **Why-now кандидаты.** Из competitive-analysis + research найти 1–2 свежих тренда (AI-волна, регуляторное изменение, плато конкурента).
- **Конкурентный вектор.** Не просто матрица — **одно предложение** в чём наш angle (cheaper / faster / niche / new tech / new model).
- **Risk-acknowledgement slide (опционально).** Если у проекта есть очевидный риск (DMCA для Memster, regulation для Finbrain) — лучше адресовать самим в appendix.

---

## Структура output-файла

`01_Business/08_Pitch_Deck.md`:

```markdown
---
project: [ProjectName]
stage: pitch-deck
round: [pre-seed | seed | series-a]
ask_usd: [сумма]
runway_months: [число]
created: YYYY-MM-DD
---

# Pitch Deck — [ProjectName]

## Slide 1 — Title
- Заголовок: [ProjectName]
- One-liner: [одна строка]
- Контакт: ...

## Slide 2 — Problem
**Тезис:** [главный hook]
- Кому больно: ...
- Цена нерешения: ...
- Источник: [[00_Idea_Discovery]]

## Slide 3 — Solution
**Тезис:** ...
- Что делаем: ...
- Скриншот / wireframe: [ссылка]
- Почему закрывает боль: ...

## Slide 4 — Why now
**Тезис:** ...
- Тренд / технология: ...
- Окно возможностей: ...

## Slide 5 — Market size
- TAM: $X (источник)
- SAM: $Y (источник)
- SOM: $Z (наш taking)

## Slide 6 — Competition
- Карта: [таблица из 02_Competitive_Analysis]
- Наш вектор атаки: [одно предложение]

## Slide 7 — Product
- Фича 1: ...
- Фича 2: ...
- Фича 3: ...

## Slide 8 — Business model
- Модель: [из 03_Monetization_Model]
- LTV: $X, CAC: $Y, payback: Z мес (из 04_Unit_Economics)

## Slide 9 — Traction / GTM
- Текущее: [цифры]
- План GTM: [из 06_Go_To_Market]

## Slide 10 — Team + Ask
- Команда: [имена, роли]
- Ask: $[сумма] на [runway] мес
- На что: [breakdown]

## (Appendix) — Risk acknowledgement
[если применимо]
```

---

## Жёсткие запреты

НЕЛЬЗЯ:
- Цифры без источника
- «Революционно», «уникально», «нет аналогов» — без доказательств
- Слайд «Vision» без traction (отложить на series A+)
- Включать financial projections beyond 24 месяцев на pre-seed
- Прятать ключевой риск — VC всё равно его найдут

---

## Экспорт

Если пользователь просит .pptx или .pdf:
- Использовать `document-generator-mcp` (см. `docs/ai/mcp-servers.md`)
- Markdown остаётся источником истины — `.pptx` собирается из него каждый раз заново, не редактируется отдельно
