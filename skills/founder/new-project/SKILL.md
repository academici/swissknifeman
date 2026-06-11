---
name: new-project
bucket: founder
version: 0.1.0
description: Запуск нового стартап-проекта: концепция, конкуренты, риски, полная структура папок
risk: write
persona: founder
tags: [discovery, requirements]
requires: [competitive-analysis, risk-assessment]
produces_for: []
outputs: [ProjectName.md, "01_Business/01_Concept_and_Monetization.md", "01_Business/02_Competitive_Analysis.md", "01_Business/Risk_Register.md", "Открытые вопросы.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: New Project / Concept Analysis

Применять когда: пользователь даёт новую идею, концепцию, стартап, продукт — что угодно требующее оценки и запуска документации.

---

## Шаг 1. Глубокий анализ (обязателен, не пропускать)

Перед любым документированием агент **самостоятельно** выполняет:

1. **JTBD-анализ** — выполнять через `competitive-analysis.md` (начинает с JTBD-фрейма; результат → основа BRD и GTM)

2. **Конкурентный анализ** — 3–5 реальных игроков:
   - Кто они, какой сегмент занимают
   - Конкретные слабые места (UX, цена, охват, технология)
   - Незанятая ниша, в которую может войти продукт
   - Если нужен реальный поиск → использовать Perplexity MCP (`.ai/guidelines/perplexity-mcp.md`)

3. **Риски** — обязательно читать `.ai/skills/founder/risk-assessment.md`:
   - Прогнать через все 5 категорий (технические, рыночные, регуляторные, финансовые, команда)
   - Risk Matrix с оценкой каждого
   - Называть явно: "Если [условие] → то [последствие]"

4. **Улучшения концепции** — предложить то, что не было в ТЗ:
   - Смежные фичи с высоким ROI
   - Альтернативные бизнес-модели
   - Возможные синергии с другими проектами vault (см. карту в CLAUDE.md)

## Шаг 2. Только блокирующие вопросы

Задавать вопросы только если без ответа **нельзя двигаться дальше**.

❌ "Нужен ли мобильный клиент?"
✅ "Продаёте сами или через партнёров? От этого зависит white-label с v1."

Правило: если агент может ответить сам с вероятностью >70% — отвечает сам, документирует решение.

## Шаг 3. Создание документации (стадийно)

Этапы строго последовательны. Каждый этап требует явного «Утверждено» перед следующим.

| Этап | Файл | Скилл | Запрещено |
|:---|:---|:---|:---|
| 1 | `01_Business/01_Concept_and_Monetization.md` | — | Технические детали |
| 2 | `01_Business/02_Competitive_Analysis.md` | `competitive-analysis.md` | — |
| 3 | `01_Business/Risk_Register.md` | `risk-assessment.md` | — |
| 4 | `01_Business/04_Unit_Economics.md` | `unit-economics.md` | SQL, классы |
| 5 | `Открытые вопросы.md` — только блокирующее | — | Отвечать за пользователя |
| 6 | `02_Workflow/` — FSM-процессы | `business-process.md` | Архитектурные решения |
| 7 | `01_Business/06_Go_To_Market.md` | `go-to-market.md` | — |
| 8 | `01_Business/07_Product_Roadmap.md` | `product-roadmap.md` | — |
| 9 | `03_Dev/BRD.md` | `brd.md` | Классы, схемы БД, код |
| 10 | `03_Dev/Architecture*.md` | `architecture.md` | — |
| 11 | `03_Dev/Database_Schema.md` | `data-schema.md` | SQL |
| 12 | `03_Dev/API_Endpoints.md` | `api-design.md` | — |

## Шаг 4. Межпроектные синергии

При создании нового проекта проверить карту vault (CLAUDE.md) на:
- Общие модули, которые можно вынести в `02 - Knowledge/`
- Пересечение аудитории с другим проектом → возможность bundle/partnership
- Общие технические решения → ссылка через `[[файл]]`
