---
name: customer-discovery
bucket: founder
version: 0.1.0
description: Систематическое discovery — target profile, interview framework (прошлое не будущее), post-interview анализ 2 списков, asymmetry-check каждые 5 интервью, outreach-автоматизация
risk: draft
persona: founder
tags: [discovery, validation, market]
requires: [idea-discovery]
produces_for: [competitive-analysis, monetization-design, new-project]
outputs: ["docs/01_Business/00_Customer_Discovery.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Customer Discovery

Применять когда: гипотеза из `idea-discovery` сформулирована и прогнана через `adversarial-check`, и нужно **подтвердить её живыми разговорами** до строительства. Idea-стадия, основной источник доказательств problem-solution fit.

Расширяет Mom-Test ядро `idea-discovery` до полного протокола: **кого** спрашивать, **что** спрашивать, **как** анализировать. Качество того, что узнаёшь = (1) качество вопросов × (2) правильность людей.

---

## Когда НЕ применять

- Нет проверяемой гипотезы (сначала `idea-discovery`).
- Решение уже валидировано, идёт MVP — это `pmf-diagnostics`, не discovery.
- Гипотеза не пережила `adversarial-check` (KILL) — discovery не спасёт мёртвую идею.

---

## 1. Кого спрашивать (target profile)

Точный профиль ценнее длинного списка контактов.

- **Job titles** — конкретные роли, переживающие проблему остро (не «бизнес», а «финдир МСБ 50–200 чел»).
- **Company type / size** — сегмент, размер, индустрия.
- **Team structure / seniority** — кто принимает решение, кто страдает (не всегда один человек).
- **Где досягаемы** — сообщества, события, LinkedIn-группы, Slack/Telegram, субреддиты.
- **Prioritization** — кого первым, по близости к проблеме.

Если гипотеза затрагивает >1 роли (например finance manager и CFO) — **разные наборы вопросов** для каждой; единый фреймворк сгладит различие.

## 2. Что спрашивать (interview framework)

**Главное правило: прошлое, не будущее.** Rookie-ошибка — общий вопрос про будущее («использовал бы ты продукт, который…») вместо конкретного запроса прошлого («расскажи про последний раз, когда столкнулся с этим»).

**Открывающие (контекст):**
1. Расскажи про свою роль — как выглядит типичный день?
2. Какие инструменты используешь для [проблемная область]?

**Core (прошлое поведение):**
3. Расскажи про **последний раз**, когда столкнулся с [проблема].
4. Как часто это? Насколько болезненно?
5. Что делаешь сейчас, чтобы справиться? (workaround)
6. Что больше всего раздражает в текущем подходе?

**Probe (на deflection / расплывчатость):**
7. [Расплывчато] «Можешь привести конкретный пример?»
8. [«Не проблема»] «А как другие в команде справляются?»

**❌ Под запретом:**
- «Использовал бы ты…» (future-facing)
- «Насколько важна тебе фича X?» (social desirability)
- «Согласен, что [проблема] существует?» (leading)

## 3. Post-interview analysis

После **каждого** разговора — дебриф: что **подтвердило** гипотезу, что **опровергло**, что **удивило**.

**После каждых 5 интервью — synthesis + asymmetry check:**
- Два списка: evidence FOR гипотезы и evidence AGAINST.
- Recurring themes (звучало 3+ раз), surprises, противоречия.
- **Если FOR значительно длиннее AGAINST — спросить: это реально в данных, или это то, что я хотел услышать?** (см. `adversarial-check`).

## 4. Outreach и расписание (автоматизация)

Операционку — на инструменты (в Brain: MCP / Claude Code; в Cowork: connectors):
- Из target profile → prospect-список с verified-контактами.
- Персонализированные outreach-письма под роль/контекст.
- Расписание (Gmail/Calendar via MCP), follow-up на day-7, tracking-таблица статусов.
- Фаундер фокусируется на **самих разговорах**, не на координации.

---

## Структура output-файла

`docs/01_Business/00_Customer_Discovery.md`:

```markdown
---
project: [ProjectName]
stage: idea
created: YYYY-MM-DD
interviews_done: 0
---

# Customer Discovery — [ProjectName]

## Гипотеза (из idea-discovery)
[проверяемая форма]

## Target profile
- Job title / company / team / seniority / где досягаемы / приоритет

## Interview framework
[вопросы по секциям; разные наборы для разных ролей]

## Лог интервью
| # | Дата | Роль | Подтвердило | Опровергло | Сюрприз |
|---|---|---|---|---|---|

## Synthesis (каждые 5)
- FOR: …
- AGAINST: …
- Asymmetry check: реальный сигнал или wishful thinking?

## Вывод
→ problem-solution fit достигнут? (вход в startup-lifecycle idea-gate)
```

---

## Что агент добавляет сам

- **Аудит черновика вопросов.** Помечает leading / future-facing / too-broad; предлагает follow-up probe для 2–3 моментов, склонных к deflection.
- **Recruit-логика.** Сколько интервью минимум, какие сегменты, где искать.
- **Pattern-matching warning.** Флажит, где собственное прочтение данных может подгоняться под желаемое.

---

## Связанные скиллы

- `founder/idea-discovery` — **requires**: поставляет гипотезу и target-намётку
- `founder/adversarial-check` — synthesis/asymmetry check опирается на него
- `founder/competitive-analysis` — потребитель: подтверждённые боли задают конкурентный фрейм
- `founder/startup-lifecycle` — discovery закрывает Idea-exit (problem-solution fit)
- `pm/pmf-diagnostics` — следующая по времени валидация (уже на MVP, не Idea)
