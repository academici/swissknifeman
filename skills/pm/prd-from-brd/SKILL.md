---
name: prd-from-brd
bucket: pm
version: 0.1.0
description: Product Requirements Document — разворачивает BRD в детальные user stories с acceptance criteria и приоритизацией
risk: draft
persona: pm
tags: [requirements]
requires: [brd]
produces_for: [architecture, product-roadmap, api-design]
outputs: ["docs/03_Dev/PRD.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: PRD from BRD

Применять когда: BRD написан и утверждён, нужен следующий слой — детальные user stories с acceptance criteria, UX-вопросы, edge cases, готовые к передаче в архитектуру и разработку.

**BRD ≠ PRD.** BRD = ЧТО + БИЗНЕС-КОНТЕКСТ. PRD = ЧТО + ПОЛЬЗОВАТЕЛЬСКИЙ ОПЫТ + ГРАНИЦЫ КАЧЕСТВА. Архитектура — это уже ТРЕТИЙ слой (КАК).

---

## Когда НЕ применять

- BRD ещё не существует → отказать, отправить на `brd`.
- BRD существует, но не утверждён пользователем → не писать PRD «вперёд паровоза».
- Уже есть PRD и нужны точечные правки → редактировать, не переписывать с нуля.
- Проект OSS-библиотека без UX (BrainKit, AzGuard) — PRD не нужен, идти на `api-design`.

---

## Что PRD добавляет к BRD

| Уровень | BRD | PRD |
|:---|:---|:---|
| User stories | Каркас («как X, я хочу Y») | Полные с AC, edge cases, error states |
| UX | Не описано | Flow, состояния экрана, empty/loading/error |
| Приоритизация | MoSCoW грубый | RICE / MoSCoW + версия (v1/v1.1/v2) |
| Метрики успеха фичи | Бизнес-уровень | Per-feature success metric |
| Зависимости | Между модулями | Между stories + внешние |
| Out-of-scope | Кратко | Явный список «что НЕ делаем в v1» |

---

## Структура PRD

```
1. TL;DR (3–5 строк) — что и для кого выпускаем
2. Цели и не-цели (in-scope / out-of-scope)
3. User personas (детали поверх BRD)
4. User flows (mermaid + текстовое описание)
5. Detailed user stories
   - Для каждой:
     - User story (как роль, я хочу..., чтобы...)
     - Acceptance criteria (Given / When / Then)
     - Edge cases / error states
     - Success metric
     - Приоритет (RICE score + версия)
     - Зависимости (другие stories или внешние)
6. UX requirements
   - Состояния экрана: empty / loading / success / error / partial
   - Accessibility minimum (WCAG 2.1 AA если применимо)
   - Mobile breakpoints (если веб)
7. Метрики запуска (north star + per-feature)
8. Открытые UX-вопросы (для дизайнера)
9. Out of scope для v1 (явный список)
```

---

## Опросные вопросы ПЕРЕД написанием

Задавать только то, чего нет в BRD:

- Целевые платформы (web/mobile/desktop) — если в BRD не зафиксировано
- Дизайн-система (своя / Tailwind UI / Material / shadcn) — влияет на UX-spec
- Метрики успеха продукта в целом (north star metric)
- Кто будет дизайнить (есть ли дизайнер или сами) — определяет уровень детализации UX-секции
- Версия запуска (v1 = MVP, или сразу v1.1 с расширением)

---

## Acceptance criteria — обязательный формат

Каждая user story в PRD должна иметь AC в формате Given/When/Then:

```
Given [предусловие],
When [действие пользователя],
Then [ожидаемый результат].
```

Минимум 1 happy path + 2 edge cases на story.

**Антипаттерны AC:**
- ❌ «Кнопка работает» (что значит работает?)
- ❌ «Форма красивая» (не верифицируемо)
- ❌ Implementation-detail в AC («использует Redux store»)
- ✅ «When user clicks Save with empty Email field, Then form shows error 'Email required' next to the field and Save button stays disabled.»

---

## Приоритизация — RICE

Для каждой story посчитать:
- **Reach** — сколько user/мес затронуто (число)
- **Impact** — 0.25 / 0.5 / 1 / 2 / 3
- **Confidence** — 50% / 80% / 100%
- **Effort** — person-weeks

`RICE = (Reach × Impact × Confidence) / Effort`

Сортировать по RICE descending. Версия (v1 / v1.1 / v2) = группировка по cutoff.

---

## Что агент добавляет сам

- **Edge cases по умолчанию для каждой story:**
  - Что если пользователь офлайн?
  - Что если данные невалидны?
  - Что если параллельный запрос изменил состояние?
  - Что если внешняя интеграция недоступна?
- **Empty / loading / error состояния** для каждого экрана — даже если пользователь не упомянул.
- **Accessibility-минимум:** keyboard navigation, focus management, ARIA labels (если веб).
- **Конфликты со BRD** — называть явно. Если в PRD появляется требование, противоречащее BRD, остановиться и спросить.

---

## Структура output-файла

`docs/03_Dev/PRD.md`:

```markdown
---
project: [ProjectName]
stage: prd
version: v1
based_on_brd: docs/03_Dev/BRD.md
requires_input_from: [docs/03_Dev/BRD.md]
produces_input_for: [Architecture, Product_Roadmap, API_Endpoints]
created: YYYY-MM-DD
---

# PRD — [ProjectName] v1

## TL;DR
[3–5 строк]

## In-scope / Out-of-scope
**In:** ...
**Out (v1):** ...

## Personas
[детали поверх BRD]

## User flows
```mermaid
[flow diagrams]
```

## User stories

### US-001: [короткое название]
**Story:** Как [роль], я хочу [действие], чтобы [цель].

**AC:**
- Given ..., When ..., Then ...
- Given ..., When ..., Then ...
- Given ..., When ..., Then ...

**Edge cases:**
- ...

**Success metric:** ...

**RICE:** R=___, I=___, C=___, E=___ → score=___
**Version:** v1

**Depends on:** US-XXX, external API X

---

[повторить для каждой story]

## UX requirements
### Состояния экрана (общий чек-лист)
- empty / loading / success / error / partial — для каждого экрана

### Accessibility
- WCAG 2.1 AA минимум
- Keyboard nav: ...
- ARIA: ...

### Breakpoints (если веб)
- mobile / tablet / desktop

## Метрики запуска
- **North Star:** ...
- **Per-feature:** ...

## Открытые UX-вопросы
- ...

## Out of scope для v1
- ...
```

---

## Жёсткие запреты на стадии PRD

НЕЛЬЗЯ:
- Выбирать стек, фреймворк, БД — это `architecture`
- Расписывать SQL-схему — это `data-schema`
- Определять REST-эндпоинты — это `api-design`
- Делать визуальный дизайн (цвета, типографика, компоненты) — это работа дизайнера/Figma
- Писать код в AC

PRD остаётся продуктовым документом — границы между **что нужно** и **как реализовано** держать жёстко.
