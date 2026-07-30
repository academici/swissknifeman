---
name: new-project
bucket: founder
version: 0.1.0
description: Используй при запуске нового стартап-проекта: концепция, конкуренты, риски, полная структура папок.
risk: write
persona: founder
tags: [discovery, requirements, market, gtm]
requires: [idea-discovery, competitive-analysis, risk-assessment, ecosystem-reuse-gate]
produces_for: []
outputs: [ProjectName.md, "docs/01_Business/01_Concept_and_Monetization.md", "docs/01_Business/02_Competitive_Analysis.md", "docs/01_Business/Risk_Register.md", "Открытые вопросы.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: New Project / Concept Analysis

Применять когда: пользователь даёт новую идею, концепцию, стартап, продукт — что угодно требующее оценки и запуска документации.

---

## Шаг 0. Idea-gate (до документирования)

Прежде чем городить структуру папок — убедиться, что идея **заслуживает** строительства (Founder's Playbook: главный риск стадии — *mistaking building for validating*). Если приходит сырая идея или первичный отчёт:

1. `idea-discovery` — заострить гипотезу до проверяемой формы.
2. `adversarial-check` — pressure-test до коммита (AI подтвердит что угодно; нужен обратный вектор).
3. `customer-discovery` — если доказательств из живых разговоров ещё нет, спланировать их (для serious-проекта — собрать; для быстрой валидации — хотя бы фреймворк).
4. **Problem-solution fit (3 «да»):** проблема реальна+специфична+частотна? решение бьёт по реальной проблеме? сигнала достаточно для MVP? (`startup-lifecycle` Idea-exit).

Только при прохождении gate — заводить документацию. Не прошло → не скаффолдить, вернуть на discovery/pivot.

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

## Шаг 2.5. Ecosystem reuse-gate (до скаффолда)

Перед созданием структуры папок прогнать `ecosystem-reuse-gate` против радара экосистемы — не переизобретать то, что уже есть в других проектах/пакетах.

## Шаг 3. Создание документации (стадийно)

При создании control-tower `ProjectName.md` выставить во frontmatter **`stage: idea`** (бизнес-стадия валидации; новый проект всегда стартует с idea). Стадия поднимается через stage-gate review (`startup-lifecycle`), не вручную по настроению.

Этапы строго последовательны. Каждый этап требует явного «Утверждено» перед следующим.

| Этап | Файл | Скилл | Запрещено |
|:---|:---|:---|:---|
| 1 | `docs/01_Business/01_Concept_and_Monetization.md` | — | Технические детали |
| 2 | `docs/01_Business/02_Competitive_Analysis.md` | `competitive-analysis.md` | — |
| 3 | `docs/01_Business/Risk_Register.md` | `risk-assessment.md` | — |
| 4 | `docs/01_Business/04_Unit_Economics.md` | `unit-economics.md` | SQL, классы |
| 5 | `Открытые вопросы.md` — только блокирующее | — | Отвечать за пользователя |
| 6 | `docs/02_Workflow/` — FSM-процессы | `business-process.md` | Архитектурные решения |
| 7 | `docs/01_Business/06_Go_To_Market.md` | `go-to-market.md` | — |
| 8 | `docs/01_Business/07_Product_Roadmap.md` | `product-roadmap.md` | — |
| 9 | `docs/03_Dev/BRD.md` | `brd.md` | Классы, схемы БД, код |
| 10 | `docs/03_Dev/Architecture*.md` | `architecture.md` | — |
| 11 | `docs/03_Dev/Database_Schema.md` | `data-schema.md` | SQL |
| 12 | `docs/03_Dev/API_Endpoints.md` | `api-design.md` | — |

## Шаг 4. Межпроектные синергии

При создании нового проекта проверить карту vault (CLAUDE.md) на:
- Общие модули, которые можно вынести в `02 - Knowledge/`
- Пересечение аудитории с другим проектом → возможность bundle/partnership
- Общие технические решения → ссылка через `[[файл]]`

---

## Связанные скиллы

Этот скилл — оркестратор: он не дублирует доменные скиллы, а вызывает их по этапам. Цепочка:

- `founder/startup-lifecycle` — рамка стадий: new-project ставит `stage: idea` и прогоняет idea-gate
- `founder/idea-discovery` — этап 0: discovery сырой идеи (JTBD, гипотеза, kill-criteria) до концепции
- `founder/adversarial-check` — idea-gate: pressure-test гипотезы до скаффолда
- `founder/customer-discovery` — idea-gate: доказательства problem-solution fit живыми интервью
- `architect/ecosystem-reuse-gate` — шаг 2.5: сверка с радаром экосистемы до скаффолда
- `founder/competitive-analysis` — этап 2: рынок, конкуренты, вектор атаки
- `founder/risk-assessment` — этап 3: 5 категорий рисков, Risk Register
- `pm/unit-economics` — этап 4: LTV/CAC/payback
- `pm/business-process` — этап 6: FSM-процессы
- `pm/go-to-market` — этап 7: GTM-стратегия
- `pm/product-roadmap` — этап 8: MVP → v1 → v2
- `pm/brd` — этап 9: Business Requirements Document
- `architect/architecture`, `architect/data-schema`, `architect/api-design` — этапы 10–12: технический дизайн
- `pm/monetization-design` — смежный: выбор бизнес-модели перед unit-economics
- `roles/solo-founder`, `roles/startup-cto` — персоны, которые активируют эту цепочку
