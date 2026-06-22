---
name: defensibility
bucket: founder
version: 0.1.0
description: Moat-анализ для Scale-стадии — accumulated depth, data flywheel, workflow lock-in, domain-as-context, moat narrative one-pager
risk: draft
persona: founder
tags: [market, validation]
requires: []
produces_for: [pitch-deck, go-to-market]
outputs: ["docs/01_Business/Defensibility_Moat.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Defensibility / Moat

Применять когда: продукт нашёл PMF и масштабируется; нужно построить **defensible moat через accumulated depth**. Scale-стадия. Лакмус Founder's Playbook: *«Если бы well-funded incumbent скопировал продукт сегодня — пользователи остались бы?»*

Ключевой сдвиг эпохи AI: построить продукт легко и быстро (для всех) → **сама по себе функциональность больше не моат**. Моат = то, что компаундируется со временем и что нельзя купить.

---

## Когда НЕ применять

- Нет PMF (стадия idea/mvp) — преждевременно; сначала `pmf-diagnostics`. Моат без retention — фантазия.
- Нужен разовый конкурентный обзор — это `competitive-analysis`, не moat-стратегия.

---

## 4 источника моата (аудит по каждому)

### 1. Accumulated depth
Глубина, накопленная в продукте: интеграция с инструментами/платформами, на которые опираются пользователи; проприетарные системные данные и workflow. Фаундеры, кто строил последовательно в одном направлении на consistent-инфраструктуре, получают то, что **структурно трудно повторить**.

### 2. Data flywheel (compounding user data)
Пользователи генерят поведенческие сигналы (что приняли / что отвергли) → это кормит roadmap. Со временем узнаёшь специфические паттерны, предпочтения, edge cases своей базы. **Каждое улучшение делает продукт полезнее → больше usage → больше feedback → больше улучшений.**
Эти данные time-locked, context-specific и невоспроизводимы копикэтом: нельзя купить поведенческий отпечаток тысяч юзеров, шлифовавших workflow внутри продукта.

### 3. Workflow lock-in
Compounding data делает продукт труднее повторить; workflow lock-in делает труднее **уйти**. Чем дольше пользователи гоняют продукт в daily-операциях — тем глубже он вшит: автоматизации поверх, обученные люди, подключённые источники данных, отлаженные prompts/workflows/outputs. Switching → из «product decision» в «full-scale operational project».
**Аудит integration depth:** по топ-N клиентам — какие workflow построили поверх, от каких интеграций зависят, оценка switching cost. Где залипли, где на поверхности → что построить/включить, чтобы углубить.

### 4. Domain expertise → AI context
Externalize знание основателя (industry jargon, регуляторные gotchas, edge cases, почему «очевидные» решения не работают) в structured, searchable context. Skills кодифицируют повторяющиеся workflow в reusable-рутины. За месяцы это становится proprietary knowledge substrate, который generalist-AI не повторит. Пример: «medical billing ломается на 340B-claims» → специальный test case в продукте.

---

## Output: moat narrative

One-pager для product marketing / инвесторов:

```markdown
---
project: [ProjectName]
stage: scale
created: YYYY-MM-DD
---

# Defensibility / Moat — [ProjectName]

## Accumulated depth
Что построено последовательно, что трудно повторить: …

## Data flywheel
Какие сигналы собираем, как долго, какие 3 highest-signal паттерна → как кормят улучшение: …

## Workflow lock-in (integration depth)
| Клиент | Workflow поверх | Зависимые интеграции | Switching cost |
|---|---|---|---|
Что построить, чтобы углубить: …

## Domain moat
Edge cases / regulatory gotchas, закодированные в продукт (которых нет у generic-конкурента): …

## Moat narrative (для GTM/инвесторов)
История data flywheel: как работает, как долго крутится, почему well-resourced конкурент, стартующий сегодня, не повторит за <2 года.

## Лакмус
«Incumbent скопировал сегодня — пользователи остались бы?» → ответ + почему.
```

---

## Что агент добавляет сам

- **Реализм моата.** Если «моат» = просто фичи — назвать прямо: это не защищает.
- **Связь с domain-проектами портфеля.** Agelto (ЕИС edge cases), CoreX (integration lock-in), AxiomaErpSdk (domain depth) — кандидаты, где domain→context особенно силён.
- **Time-to-replicate оценка.** Сколько реально займёт у конкурента — честно, не маркетингово.

---

## Связанные скиллы

- `founder/startup-lifecycle` — Scale-стадия; defensibility — её основная работа
- `founder/competitive-analysis` — поставляет ландшафт; defensibility отвечает «почему мы держимся»
- `pm/go-to-market` — потребитель: moat narrative кормит messaging для инвесторов/enterprise
- `founder/pitch-deck` — потребитель: moat-слайд
- `pm/pmf-diagnostics` — предусловие: моат имеет смысл только после PMF
