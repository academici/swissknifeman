> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: sales-super-skill
bucket: sales
version: 1.0.0
description: Comprehensive end-to-end sales skill merging Perplexity Computer's 6 built-in sales skills with Claude Code's customer interview analysis, brand voice analysis, content research, RICE prioritization, and UX research. Covers the full sales cycle from prospecting to close. Use when doing account research, call prep, competitive intelligence, outreach drafting, asset creation, daily briefings, customer interview analysis, deal prioritization, or prospect research.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

# Sales Super-Skill (Супер-скилл продаж)

Полноценная операционная система продаж — объединяет 6 встроенных скиллов продаж Perplexity Computer с фреймворками Claude Code по продакт-менеджменту, UX-исследованиям, бренд-войсу и контенту. Покрывает полный цикл от поиска клиентов до закрытия сделки, от исследования аккаунта до приоритизации сделок, от конкурентной разведки до создания персонализированных материалов.

---

## Оглавление

1. [Таблица анализа пробелов](#section-1-gap-analysis-table)
2. [Исследование аккаунта и разведка по клиенту](#section-2-account-research--prospect-intelligence)
3. [Подготовка к звонку и готовность к встрече](#section-3-call-prep--meeting-readiness)
4. [Конкурентная разведка и позиционирование](#section-4-competitive-intelligence--positioning)
5. [Аутрич и создание контента](#section-5-outreach--content-creation)
6. [Материалы продаж и поставляемые артефакты](#section-6-sales-assets--deliverables)
7. [Приоритизация сделок и управление пайплайном](#section-7-deal-prioritization--pipeline-management)
8. [Уникальные возможности Perplexity Computer](#section-8-unique-perplexity-computer-capabilities)

---

## Как запустить этот скилл

Используйте этот скилл, когда слышите любую из этих фраз:

| Фраза | Раздел для выполнения |
|--------|--------------------|
| "Research [company]" / "Intel on [company]" | Раздел 2 — Исследование аккаунта |
| "Prep me for my call with [company]" | Раздел 3 — Подготовка к звонку |
| "Build battlecard for [competitor]" | Раздел 4 — Конкурентная разведка |
| "Draft outreach to [person/company]" | Раздел 5 — Аутрич |
| "Create an asset / landing page / one-pager" | Раздел 6 — Материалы продаж |
| "Morning briefing" / "Start my day" | Раздел 7 — Дневной брифинг |
| "Prioritize my pipeline / deals" | Раздел 7 — Приоритизация пайплайна |
| "Analyze interview transcript" | Раздел 2 — Анализ клиентского интервью |
| "Build customer persona" | Раздел 2 — Разработка персоны |
| "Analyze brand voice" | Разделы 4 и 5 — Анализ бренд-войса |
| "Map user journey" | Раздел 2 — Картирование пути |

---

## Раздел 1: Таблица анализа пробелов

### Что вносит каждая система

| Возможность | Perplexity Computer | Claude Code | Объединённый супер-скилл |
|------------|---------------------|-------------|-------------------|
| **Исследование компании** | Веб-поиск, живые данные, интеграции enrichment/CRM | Только статичные фреймворки | Живое + структурированное — веб-данные в реальном времени вместе с PM-фреймворками интервью |
| **Исследование человека/контакта** | Поиск в LinkedIn, enrichment-API | Генератор персон из JSON-данных | Живой LinkedIn + синтез персон на основе данных |
| **Анализ клиентского интервью** | Базовое извлечение Q&A | NLP-извлечение болей/JTBD/тональности с оценкой серьёзности | Полный конвейер обработки интервью, напрямую питающий квалификацию в продажах |
| **Разработка персоны клиента** | Тезисы для разговора по роли | Генератор персон по 4 архетипам (Power User, Business User, Casual, Mobile-First) | UX-архетипы персон, отображённые на роли покупателя для гипер-таргетированных сообщений |
| **Подготовка к звонку** | Бриф подготовки к встрече с повесткой + возражениями | Фреймворки discovery, шаблоны ревью PRD | Подготовка под конкретный тип встречи (discovery/демо/переговоры/QBR) + более глубокие банки вопросов discovery |
| **Конкурентная разведка** | HTML-батлкарта с talk track'ами, вопросами-минами, анализом win/loss | Нет нативной | Батлкарта + анализ позиционирования по бренд-войсу для каждого конкурента |
| **Составление аутрича** | AIDA-письмо, LinkedIn, последовательности фоллоу-апов | Шаблоны контент-фреймворков, SEO-оптимизированный текст | Аутрич AIDA «сначала исследование» + проверка консистентности бренд-войса |
| **Анализ бренд-войса** | Недоступно | Оценка формальности/тональности/читабельности | Применяется к бренду клиента (для подгонки материалов) и к бренду конкурента (для позиционирования) |
| **Создание материалов продаж** | Лендинги, деки, one-pager'ы, демо рабочих процессов | Блог/контент-фреймворки, шаблоны email-кампаний | 7-фазное создание материалов + матрица переиспользования контента |
| **Приоритизация сделок** | Эвристики ранжирования приоритетов | Фреймворк скоринга RICE с портфельным анализом | RICE, адаптированный под сделки — скоринг Reach/Impact/Confidence/Effort на каждую возможность |
| **Дневной брифинг** | Алерты по пайплайну, подготовка к встречам, приоритеты писем | Недоступно | Брифинг + фокус на топ-3 сделках по RICE-скору |
| **Картирование пути** | Недоступно | Полное картирование пути B2B SaaS (Awareness → Advocacy) | Опыт покупателя, размеченный по пути, питающий вопросы discovery |
| **Usability/UX-исследования** | Недоступно | 4 фреймворка методов исследования, таблицы размера выборки | Переводится в продажи: понимание того, как покупатели оценивают продукты |
| **Контент-календарь** | Недоступно | Соотношение пилларов 40/25/25/10, рабочий процесс пакетного создания | Последовательности контента для фоллоу-апа с каденцией на основе пилларов |
| **Аналитика кампаний** | Недоступно | Атрибуция, анализ воронки, ROI-калькулятор | Постсделочный анализ с использованием логики модели атрибуции |
| **Живое веб-исследование** | Да — в реальном времени | Нет | Только Perplexity Computer |
| **Мониторинг соцсетей** | Да — поиск по X/Twitter | Нет | Только Perplexity Computer |
| **Генерация изображений/видео** | Да | Нет | Только Perplexity Computer |
| **Деплой сайтов** | Да — Netlify/Vercel | Нет | Только Perplexity Computer |
| **Интеграции приложений (CRM/email/календарь)** | Да — 400+ приложений | Нет | Только Perplexity Computer |
| **Запланированный мониторинг** | Да — алерты по конкурентам | Нет | Только Perplexity Computer |

### Что добавляет объединение, чего не было ни у одной системы по отдельности

1. **Конвейер «Интервью → Исследование аккаунта»** — результаты анализа клиентского интервью напрямую питают исследование аккаунта и сигналы квалификации
2. **Мост «UX-персона → Персона покупателя»** — UX-архетипы (Power User, Business User) отображаются на роли экономического покупателя, обогащая сообщения
3. **Пайплайн сделок со скорингом RICE** — PM-фреймворк приоритизации, применённый к сделкам: Reach = аккаунты, Impact = размер сделки, Confidence = вероятность выигрыша, Effort = требуемые усилия продаж
4. **Аутрич с учётом бренд-войса** — каждый черновик письма можно проверить на соответствие профилю бренд-войса клиента перед отправкой
5. **Discovery, размеченный по пути** — стадии пути покупателя B2B (Awareness → Advocacy) задают банки вопросов discovery для каждого типа встречи
6. **Конкурентное позиционирование через бренд-войс** — анализ бренд-войса конкурента (формальность, тональность) выявляет пробелы в позиционировании, которые можно использовать

---

## Раздел 2: Исследование аккаунта и разведка по клиенту

### Обзор

```
┌─────────────────────────────────────────────────────────────────┐
│              ИССЛЕДОВАНИЕ АККАУНТА И РАЗВЕДКА ПО КЛИЕНТУ          │
├─────────────────────────────────────────────────────────────────┤
│  ВСЕГДА (работает автономно через веб-поиск)                     │
│  ✓ Обзор компании: чем занимаются, размер, индустрия            │
│  ✓ Свежие новости: раунды финансирования, смены руководства     │
│  ✓ Сигналы найма: открытые вакансии, индикаторы роста           │
│  ✓ Ключевые люди: команда руководства, профили LinkedIn         │
│  ✓ Анализ клиентского интервью: боли, JTBD, тональность         │
│  ✓ Разработка UX-персоны из исследовательских данных            │
│  ✓ Картирование пути покупателя по стадиям                      │
├─────────────────────────────────────────────────────────────────┤
│  УСИЛЕНО (когда вы подключаете свои инструменты)                 │
│  + Enrichment: верифицированные email, телефон, техстек, оргсхема│
│  + CRM: прошлые отношения, прошлые возможности, контакты         │
└─────────────────────────────────────────────────────────────────┘
```

### Триггерные фразы

- "Research [Company]" / "Look up [Company]"
- "Intel on [Company or domain]"
- "Who is [Name] at [Company]?"
- "Analyze this interview transcript"
- "Build a persona for [segment]"
- "Map the buyer journey for [persona]"

---

### 2.1 Рабочий процесс исследования компании

**Шаг 1: Разбор запроса**

```
Определите, что исследовать:
- "Research Stripe"                    → Исследование компании
- "Look up Jane Smith at Acme"         → Человек + компания
- "Who is the CTO at Notion"           → Поиск по роли
- "Intel on acme.com"                  → Поиск по домену
- "Analyze this transcript [file]"     → Анализ клиентского интервью
```

**Шаг 2: Веб-поиск (всегда)**

Запустите эти поиски параллельно:
1. `"[Company name]"` → Главная страница, страница «о компании», продукт
2. `"[Company name] news"` → Свежие анонсы (последние 90 дней)
3. `"[Company name] funding"` → История инвестиций, стадия
4. `"[Company name] careers"` → Сигналы найма, зоны роста
5. `"[Person name] [Company] LinkedIn"` → Информация профиля
6. `"[Company name] customers"` → Кого они обслуживают
7. `"[Company name] technology stack"` → Разведка по инструментам

**Шаг 3: Enrichment (если подключено)**

```
Если доступны инструменты enrichment:
1. Enrich company → Фирмографика, финансирование, техстек
2. Search people  → Оргсхема, список контактов
3. Enrich person  → Email, телефон, бэкграунд
4. Get signals    → Данные о намерениях, скорость найма
```

**Шаг 4: Проверка CRM (если подключено)**

```
Если доступна CRM:
1. Поиск аккаунта по домену
2. Получение связанных контактов и истории
3. Получение истории возможностей (won/lost)
4. Получение таймлайна активностей и заметок
```

**Шаг 5: Синтез**

```
1. Объедините все источники
2. Приоритет данных enrichment над вебом (точнее)
3. Добавьте контекст CRM, если доступен
4. Определите сигналы квалификации (позитивные, опасения, неизвестное)
5. Сгенерируйте тезисы для разговора по каждому контакту
6. Порекомендуйте подход и точку входа
```

---

### 2.2 Формат вывода исследования аккаунта

```markdown
# Research: [Company or Person Name]

**Generated:** [Date]
**Sources:** Web Search [+ Enrichment] [+ CRM]

---

## Quick Take

[2-3 sentences: Who they are, why they might need you, best angle for outreach]

---

## Company Profile

| Field | Value |
|-------|-------|
| **Company** | [Name] |
| **Website** | [URL] |
| **Industry** | [Industry] |
| **Size** | [Employee count] |
| **Headquarters** | [Location] |
| **Founded** | [Year] |
| **Funding** | [Stage + amount if known] |
| **Revenue** | [Estimate if available] |

### What They Do
[1-2 sentence description of their business, product, and customers]

### Recent News
- **[Headline]** — [Date] — [Why it matters for your outreach]
- **[Headline]** — [Date] — [Why it matters]

### Hiring Signals
- [X] open roles in [Department]
- Notable: [Relevant roles like Engineering, Sales, AI/ML]
- Growth indicator: [Hiring velocity interpretation]

---

## Key People

### [Name] — [Title]
| Field | Detail |
|-------|--------|
| **LinkedIn** | [URL] |
| **Background** | [Prior companies, education] |
| **Tenure** | [Time at company] |
| **Email** | [If enrichment connected] |

**Talking Points:**
- [Personal hook based on background]
- [Professional hook based on role]

---

## Tech Stack [If Enrichment Connected]

| Category | Tools |
|----------|-------|
| **Cloud** | [AWS, GCP, Azure, etc.] |
| **Data** | [Snowflake, Databricks, etc.] |
| **CRM** | [Salesforce, HubSpot, etc.] |
| **Other** | [Relevant tools] |

**Integration Opportunity:** [How your product fits their stack]

---

## Prior Relationship [If CRM Connected]

| Field | Detail |
|-------|--------|
| **Status** | [New / Prior prospect / Customer / Churned] |
| **Last Contact** | [Date and type] |
| **Previous Opps** | [Won/Lost and why] |
| **Known Contacts** | [Names already in CRM] |

---

## Qualification Signals

### Positive Signals
- ✅ [Signal and evidence]

### Potential Concerns
- ⚠️ [Concern and what to watch for]

### Unknown (Ask in Discovery)
- ❓ [Gap in understanding]

---

## Recommended Approach

**Best Entry Point:** [Person and why]
**Opening Hook:** [What to lead with based on research]

**Discovery Questions:**
1. [Question about their current situation]
2. [Question about pain points or priorities]
3. [Question about decision process and timeline]

---

## Sources
- [Source 1](URL)
- [Source 2](URL)
```

---

### 2.3 Фреймворк анализа клиентского интервью

Используйте, когда у вас есть транскрипты интервью, записи звонков или заметки из разговоров с клиентами. Напрямую питает исследование аккаунта и сигналы квалификации.

**Триггер:**
- "Analyze this interview transcript"
- "Extract pain points from this call recording"
- "What did this customer say about their workflow?"

**Процесс анализа:**

```
Step 1: Code the data (закодируйте данные)
Промаркируйте каждую точку данных тегом:
- [GOAL]     — Чего они хотят достичь
- [PAIN]     — Что их фрустрирует (извлеките серьёзность: HIGH/MEDIUM/LOW)
- [BEHAVIOR] — Что они реально делают (а не что говорят, что сделали бы)
- [CONTEXT]  — Когда/где используют продукт или сталкиваются с проблемами
- [QUOTE]    — Прямые слова пользователя (золото для персонализированного аутрича)
- [JTBD]     — Паттерн jobs-to-be-done (Когда я... я хочу... чтобы я мог...)
- [COMP]     — Упоминания конкурентов
- [BUDGET]   — Сигналы по бюджету или индикаторы готовности платить

Step 2: Extract pattern frequency (извлеките частоту паттернов)
- 3+ упоминания по интервью = подтверждённый паттерн
- 1-2 упоминания = гипотеза для проверки

Step 3: Map to opportunity areas (отобразите на зоны возможностей)
- Сгруппируйте боли → тематические кластеры
- Оцените по: Frequency × Severity × Solvability (Частота × Серьёзность × Решаемость)

Step 4: Generate sales intelligence (сгенерируйте разведданные для продаж)
- Боли → банк вопросов discovery
- Упоминания конкурентов → триггеры обновления батлкарты
- Сигналы по бюджету → уверенность в квалификации
- Паттерны JTBD → уточнение ценностного предложения
```

**Вывод анализа интервью:**

```
============================================================
CUSTOMER INTERVIEW ANALYSIS
============================================================

📋 INTERVIEW METADATA
Customer: [Name, Title, Company]
Date: [Date]
Segments found: [N]

😟 PAIN POINTS ([N] found)

1. [HIGH] [Pain point]
   "[Direct quote from customer]"
   Sales implication: [How to use this in outreach/discovery]

2. [MEDIUM] [Pain point]
   "[Direct quote]"
   Sales implication: [How to use this]

💡 FEATURE REQUESTS / PRIORITIES ([N] found)
1. [Request] — Priority: High
2. [Request] — Priority: Medium

🎯 JOBS TO BE DONE

When [context/trigger]
I want [capability or outcome]
So I can [goal or result]

📊 SENTIMENT ANALYSIS
Overall: [Positive/Neutral/Negative]
Key emotions: [Frustration, Time pressure, Excitement, etc.]
Engagement level: [High / Medium / Low]

💬 KEY QUOTES (for personalized outreach)
• "[Quote 1]"
• "[Quote 2]"

🏷️ THEMES
- [Theme 1]
- [Theme 2]

🏢 COMPETITOR MENTIONS
- [Competitor] — Context: [What they said]

💰 BUDGET/BUYING SIGNALS
- [Signal] — Implication: [How to use in sales process]
```

---

### 2.4 Разработка персоны из исследовательских данных

Используйте при построении персон покупателя из клиентских данных (аналитика, опросы, интервью). Связывает UX-исследования с таргетингом в продажах.

**Формат входа (JSON):**
```json
[
  {
    "user_id": "user_1",
    "role": "VP Engineering",
    "company_size": "Series B",
    "usage_frequency": "daily",
    "features_used": ["dashboard", "reports", "export"],
    "primary_device": "desktop",
    "usage_context": "work",
    "tech_proficiency": 7,
    "pain_points": ["slow reporting", "no API access"],
    "deal_size": 45000,
    "sales_cycle_days": 62
  }
]
```

**Классификация архетипов для продаж:**

| Архетип | Сигналы | Фокус продаж | Угол discovery |
|-----------|---------|-------------|-----------------|
| **Power User / Champion** | Ежедневное использование, 10+ фич, продвинутые потребности | Эффективность, кастомизация, доступ к API | "What would you automate first?" |
| **Economic Buyer** | Рабочий контекст, командное использование, осознание бюджета | ROI, влияние на бизнес, снижение риска | "How do you measure success?" |
| **Technical Evaluator** | Высокая техническая компетентность, вопросы по безопасности | Архитектура, интеграции, комплаенс | "Walk me through your current stack" |
| **Casual / End User** | Еженедельное использование, базовые потребности, фокус на простоте | Простота, онбординг, поддержка | "What's the hardest part today?" |

**Шаблон вывода персоны:**

```
============================================================
BUYER PERSONA: [Name] the [Archetype]
============================================================

📝 One-line summary: [Daily/weekly] user who [primary use case]

Archetype: [Power User / Economic Buyer / Technical Evaluator / End User]
Confidence: [High / Medium / Low] — based on [N] users

👤 Demographics:
  • Role Range: [e.g., VP Engineering, CTO, Director of Data]
  • Company Stage: [Seed / Series A / Series B / Enterprise]
  • Tech Proficiency: [Advanced / Intermediate / Beginner]

🎯 Goals & Needs:
  • [Primary goal]
  • [Secondary goal]
  • [Functional need]

😤 Frustrations (with frequency):
  • [Pain 1] ([N]/[total] users)
  • [Pain 2] ([N]/[total] users)

💼 Sales Implications:
  → Lead with: [angle most relevant to this persona]
  → Proof point: [type of evidence that resonates]
  → Objection to expect: [common pushback]
  → Discovery question: [best question to qualify]

📈 Deal Profile:
  • Average deal size: $[X]
  • Typical sales cycle: [N] days
  • Key stakeholders in decision: [roles]
```

---

### 2.5 Картирование пути покупателя

Картируйте стадии, которые проходят ваши покупатели от осведомлённости до адвокации. Используйте, чтобы построить вопросы discovery для каждой стадии и определить, где сделки буксуют.

**Путь покупателя B2B SaaS:**

```
Awareness → Evaluation → Onboarding → Adoption → Advocacy
```

**Разведка по стадиям:**

| Стадия | Действия покупателя | Точки касания | Эмоции | Ваша роль в продажах | Вопросы discovery |
|-------|---------------|-------------|----------|-----------------|---------------------|
| **Awareness** | Исследование боли, просмотр контента, рекомендации коллег | Блог, LinkedIn, G2, конференции | Фрустрация, любопытство | Создать срочность, быть катализатором | "What made you start looking at this now?" |
| **Evaluation** | Запросы демо, триалы, RFP, сравнение вендоров | Демо продукта, триалы, звонки продаж | Аналитичность, осторожность | Убрать барьеры, выстроить уверенность | "What does your evaluation process look like?" |
| **Onboarding** | Внедрение, обучение, настройка | Customer success, поддержка | Тревожность, надежда | Обеспечить быстрые победы | "What would success look like in 30 days?" |
| **Adoption** | Регулярное использование, раскатка на команду, интеграции | Аналитика использования, QBR | Уверенность, вовлечённость | Расширять использование, доказывать ROI | "Who else in your org could benefit from this?" |
| **Advocacy** | Кейсы, рекомендации, отзывы | Reference-звонки, отзывы на G2 | Гордость, лояльность | Активировать референсы, расширяться | "Who else do you know that has this problem?" |

**Opportunity Score (оценка возможности):** Frequency × Severity × Solvability (от 1 до 5 каждый)

**Где сделки буксуют (типичные узкие места):**

| Стадия | Типичная причина застоя | Интервенция |
|-------|--------------------|-----------------------------|
| Awareness → Evaluation | Не установлена срочность | Привязать к триггерному событию (новости, найм, инициатива) |
| Evaluation → Decision | Рассогласование между стейкхолдерами | Собрать кит для чемпиона + executive one-pager |
| Decision → Close | Задержка legal/закупок | Запустить бумаги раньше; использовать шаблон order form |
| Onboarding → Adoption | Плохое внедрение | Назначить CSM при подписании контракта |

---

### 2.6 Вариации исследования

| Тип исследования | Фокус | Ключевой вывод |
|--------------|-------|------------|
| **Company Research** | Обзор бизнеса, новости, найм, руководство | Профиль компании + рекомендуемый подход |
| **Person Research** | Бэкграунд, роль, активность в LinkedIn, тезисы | Бриф по контакту + зацепки |
| **Competitor Research** | Сравнение продуктов, позиционирование, win/loss | Питает батлкарту из Раздела 4 |
| **Pre-Meeting Research** | Бэкграунды участников, свежие новости, история отношений | Питает подготовку к звонку из Раздела 3 |
| **Customer Interview Analysis** | Боли, JTBD, тональность, упоминания конкурентов | Сигналы квалификации + банк вопросов discovery |

---

## Раздел 3: Подготовка к звонку и готовность к встрече

### Обзор

```
┌─────────────────────────────────────────────────────────────────┐
│                        ПОДГОТОВКА К ЗВОНКУ                        │
├─────────────────────────────────────────────────────────────────┤
│  ВСЕГДА (работает автономно)                                     │
│  ✓ Вы сообщаете: компания, тип встречи, участники              │
│  ✓ Веб-поиск: свежие новости, финансирование, смены руководства │
│  ✓ Вывод: бриф подготовки с повесткой, вопросами, возражениями  │
│  ✓ Вопросы discovery с учётом стадии пути                       │
│  ✓ Тезисы по каждому участнику, размеченные по персоне          │
├─────────────────────────────────────────────────────────────────┤
│  УСИЛЕНО (когда вы подключаете свои инструменты)                 │
│  + CRM: история аккаунта, контакты, возможности, активности     │
│  + Email: свежие треды, открытые вопросы, обязательства         │
│  + Chat: внутренние обсуждения, инсайты коллег                  │
│  + Transcripts: записи прошлых звонков, ключевые моменты        │
│  + Calendar: авто-поиск встречи, подтягивание участников        │
└─────────────────────────────────────────────────────────────────┘
```

### Триггерные фразы

- "Prep me for my call with [Company]"
- "I'm meeting with [Company], prep me"
- "Call prep [Company]"
- "Get me ready for [Meeting type] with [Company]"

---

### 3.1 Сбор контекста

**Обязательные входные данные:**
- Название компании или контакта
- Тип встречи (discovery / демо / переговоры / check-in / QBR)

**Полезно, если доступно:**
- Имена и должности участников
- Прошлые заметки, письма или контекст для вставки
- Чего вы хотите добиться ("I want to get them to agree to a pilot")
- Известные опасения ("They mentioned budget is tight")

**Если коннекторы активны, подтянуть автоматически:**

```
1. Calendar → Найти ближайшую встречу, совпадающую по названию компании
   Подтянуть: заголовок, время, участников, описание, вложения

2. CRM → Запросить аккаунт
   Подтянуть: детали аккаунта, все контакты, открытые возможности
   Подтянуть: последние 10 активностей, заметки по аккаунту, поле конкурента

3. Email → Поиск свежих тредов
   Запрос: письма с доменом компании (последние 30 дней)
   Извлечь: ключевые темы, открытые вопросы, обязательства

4. Chat → Поиск внутренних обсуждений
   Запрос: упоминания названия компании (последние 30 дней)
   Извлечь: инсайты коллег, конкурентную разведку, красные флаги

5. Transcripts → Найти прошлые звонки
   Подтянуть: записи звонков с этим аккаунтом
   Извлечь: ключевые моменты, поднятые возражения, охваченные темы
```

---

### 3.2 Плейбуки по типам встреч

#### Discovery-звонок
- **Цель:** Понять их мир, квалифицировать возможность
- **Акцент повестки:** Вопросы > Говорение (соотношение 70/30)
- **Ключевой вывод:** Сигналы квалификации, предложение следующего шага
- **Длительность:** 30–45 минут

**Банк вопросов discovery (размечен по стадиям пути):**

```
Situation Questions (понять текущее состояние):
1. "Walk me through your current process for [relevant workflow]."
2. "How long has this been the way you've handled [area]?"
3. "Who else is involved in [process]?"

Problem Questions (выявить боль):
4. "What's the hardest part about [current process]?"
5. "What happens when [pain scenario] occurs?"
6. "How much time does your team spend on [area] each week?"

Implication Questions (усилить влияние):
7. "What does that cost you in terms of [time/money/opportunity]?"
8. "How does that affect [downstream team or goal]?"
9. "If nothing changes, where does that leave you in [6–12 months]?"

Need-Payoff Questions (будущее состояние):
10. "If you could [solve the problem], what would that mean for your team?"
11. "What would a successful outcome look like?"
12. "How would you measure whether this was working?"

Qualification Questions (процесс/полномочия/сроки/бюджет):
13. "How are decisions like this typically made here?"
14. "Who else needs to be involved in evaluating a solution?"
15. "Is there a timeline driving this initiative?"
16. "Do you have budget allocated, or is this exploratory?"
```

#### Демо / Презентация
- **Цель:** Показать релевантные возможности, получить техническую/бизнес-валидацию
- **Акцент повестки:** Подогнанные кейсы, их язык, контрольные точки обратной связи
- **Ключевой вывод:** Подтверждены технические требования, установлены сроки

**Чек-лист перед демо:**
- [ ] Знать топ 2–3 болей, вокруг которых строить демо
- [ ] Подготовить отраслевые примеры, не дженерик
- [ ] Определить, какие фичи демонстрировать на основе их заявленных приоритетов
- [ ] Подготовить сценарий «что если» для вероятных возражений
- [ ] Явно задать повестку в начале: "I've prepared X, Y, Z — is that still the right focus?"

**Структура демо:**
```
1. Подтвердить повестку + их приоритеты (5 мин)
2. Настроить сценарий — "Here's the situation we'll walk through" (2 мин)
3. Demo section 1 → пауза, сверка: "How does that compare to today?" (10 мин)
4. Demo section 2 → пауза, сверка: "Is this relevant to what [Name] mentioned?" (10 мин)
5. Demo section 3 → привязать к ROI: "What would this mean for your team?" (10 мин)
6. Следующие шаги (3 мин)
```

#### Переговоры / Ревью предложения
- **Цель:** Снять опасения, обосновать ценность, закрыть пробелы
- **Акцент повестки:** Обработать возражения, прояснить условия, найти путь к соглашению
- **Ключевой вывод:** Согласованный путь вперёд, чёткие следующие шаги с датами

**Подготовка к переговорам:**
```
По каждому открытому вопросу подготовьте:
- Нашу позицию
- Их вероятное опасение
- Наш ответ / размен
- Приемлемый компромисс
- Линию отказа (walk-away line)

Типичные сценарии переговоров:
- Давление по цене → обоснование ROI, скидка за многолетку, сокращение скоупа
- Опасение по срокам → поэтапное внедрение, сначала пилот
- Legal/условия → предодобренные правки (redlines), эскалация к legal-контакту
- Сравнение с конкурентом → talk track дифференциации (см. Раздел 4)
```

#### Check-in / QBR
- **Цель:** Продемонстрировать доставленную ценность, выявить возможности расширения
- **Акцент повестки:** Обзор побед, согласование по использованию, выявление новых потребностей
- **Ключевой вывод:** Уверенность в продлении, пайплайн апсейла, потенциал референса

**Структура QBR:**
```
1. Обзор метрик с прошлого QBR
   - Данные использования vs. базовая линия
   - Достигнутые бизнес-результаты
   - Расчёт ROI (используйте их метрики)

2. Подсветить победы
   - Конкретные примеры из их команды
   - Цитата от внутренних чемпионов

3. Открыто обсудить вызовы
   - Возникшие проблемы
   - Предпринятые / запланированные действия

4. Стратегическое согласование
   - Их приоритеты на следующий период
   - Как ваш роадмап их поддерживает

5. Обсуждение расширения
   - Дополнительные кейсы
   - Другие команды / отделы
   - Грядущие фичи, релевантные им

6. Подтвердить продление / следующие шаги
```

---

### 3.3 Фреймворк исследования участников

По каждому участнику встречи исследуйте:

```
1. Веб-поиск: "[Name] [Title] [Company] LinkedIn"
2. Извлечь: прошлые компании, образование, стаж, опубликованный контент
3. Определить: их функциональный приоритет (выручка / затраты / риск / эффективность)
4. Отобразить на архетип персоны (Раздел 2.4)
5. Сгенерировать: 1 личную зацепку + 1 профессиональную зацепку
```

**Отображение ролей участников:**

| Паттерн должности | Вероятная роль в сделке | Что им важно | Лучшее сообщение |
|--------------|---------------------|----------------------|--------------|
| C-suite (CEO, CFO, COO) | Economic Buyer | ROI, риск, стратегическое соответствие | Бизнес-результаты, не фичи |
| CTO, VP Engineering | Technical Evaluator | Архитектура, безопасность, масштабируемость | Глубина интеграции, надёжность |
| VP Sales, RevOps | Champion/строитель чемпиона | Влияние на выручку, адопшн | Время до ценности, лёгкость раскатки |
| Director, Manager | Чемпион на каждый день | Простота использования, продуктивность команды | Улучшение рабочего процесса, качество поддержки |
| IT/Procurement | Гейткипер | Комплаенс, стоимость, контракты | Безопасность, стабильность вендора, условия |

---

### 3.4 Формат вывода подготовки к звонку

```markdown
# Call Prep: [Company Name]

**Meeting:** [Type] — [Date/Time if known]
**Attendees:** [Names with titles]
**Your Goal:** [What you want to accomplish]

---

## Account Snapshot

| Field | Value |
|-------|-------|
| **Company** | [Name] |
| **Industry** | [Industry] |
| **Size** | [Employees / Revenue if known] |
| **Status** | [New prospect / Active opportunity / Customer] |
| **Last Touch** | [Date and summary] |

---

## Who You're Meeting

### [Name] — [Title]
- **Background:** [Career history, education if found]
- **LinkedIn:** [URL]
- **Persona Archetype:** [Economic Buyer / Technical Evaluator / Champion / End User]
- **Role in Deal:** [Decision maker / Champion / Evaluator]
- **Last Interaction:** [Summary if known]
- **Talking Point:** [Personal or professional hook]

---

## Context & History

**What's happened so far:**
- [Key point from prior interactions]
- [Open commitments or action items]
- [Any concerns or objections raised]

**Recent news about [Company]:**
- [News item 1 — why it matters]
- [News item 2 — why it matters]

**Buyer Journey Stage:** [Awareness / Evaluation / Negotiation / Onboarding / Adoption]

---

## Suggested Agenda

1. **Open** — [Reference last conversation or trigger event]
2. **[Topic 1]** — [Discovery question or value discussion]
3. **[Topic 2]** — [Address known concern or explore priority]
4. **[Topic 3]** — [Demo section / Proposal review / etc.]
5. **Next Steps** — [Propose clear follow-up with timeline]

---

## Discovery Questions

Prioritized for this meeting type and buyer stage:

1. [Situation question]
2. [Problem question]
3. [Implication question]
4. [Need-payoff question]
5. [Qualification question]

---

## Potential Objections

| Objection | Suggested Response |
|-----------|-------------------|
| [Likely objection] | [How to address it] |
| [Common objection for this stage] | [How to address it] |

---

## Internal Notes

[Any internal chat context, colleague insights, or competitive intel]

---

## After the Call

Run call-follow-up to:
- Extract action items and commitments
- Update CRM with outcome and next step
- Draft follow-up email
- Identify any new qualification signals
```

---

### 3.5 Фреймворк фоллоу-апа после звонка

```
Сразу после звонка (в течение 2 часов):
1. Залогировать заметки в CRM:
   - Исход встречи (позитивный / нейтральный / негативный)
   - Выявленные боли
   - Поднятые возражения и как обработаны
   - Обязательства, взятые обеими сторонами
   - Согласованный следующий шаг с датой

2. Отправить письмо-фоллоу-ап:
   - Тема: "Following up — [Company] + [Your Company]"
   - Поблагодарить за время
   - Резюмировать топ-3 вывода
   - Перечислить все action items с ответственными и датами
   - Подтвердить следующий шаг

3. Обновить стадию сделки, если уместно
4. Обновить записи контактов новыми разведданными
5. Пометить любые новые упоминания конкурентов для обновления батлкарты
```

---

## Раздел 4: Конкурентная разведка и позиционирование

### Обзор

```
┌─────────────────────────────────────────────────────────────────┐
│                  КОНКУРЕНТНАЯ РАЗВЕДКА                           │
├─────────────────────────────────────────────────────────────────┤
│  ВСЕГДА (работает автономно через веб-поиск)                     │
│  ✓ Глубокий разбор продукта конкурента: фичи, цены, позиционир. │
│  ✓ Свежие релизы: что они выкатили за последние 90 дней         │
│  ✓ Релизы вашей компании: что вы выкатили в ответ               │
│  ✓ Матрица дифференциации: где вы выигрываете vs. где они        │
│  ✓ Talk track'и продаж: как позиционироваться против каждого    │
│  ✓ Вопросы-мины: естественно обнажают их слабости               │
│  ✓ Анализ бренд-войса: их тон vs. ваш тон                       │
├─────────────────────────────────────────────────────────────────┤
│  ВЫВОД: Интерактивная HTML-батлкарта                             │
│  ✓ Обзорная матрица сравнения                                    │
│  ✓ Кликабельные вкладки по каждому конкуренту                   │
│  ✓ Тёмная тема, профессиональная стилизация                     │
│  ✓ Оверлей позиционирования по бренд-войсу                      │
├─────────────────────────────────────────────────────────────────┤
│  УСИЛЕНО (когда вы подключаете свои инструменты)                 │
│  + CRM: данные win/loss, упоминания конкурентов в закрытых сделк.│
│  + Docs: существующие батлкарты, конкурентные плейбуки          │
│  + Chat: внутренняя разведка, полевые отчёты от коллег          │
│  + Transcripts: упоминания конкурентов в клиентских звонках     │
└─────────────────────────────────────────────────────────────────┘
```

### Триггерные фразы

- "Build battlecard for [Competitor]"
- "Research competitors"
- "How do we compare to [Competitor]"
- "Competitive intel"
- "What's new with [Competitor]"
- "Analyze [Competitor]'s brand voice"

---

### 4.1 Методология исследования конкурентов

**Фаза 1: Собрать контекст продавца**

```
Если впервые:
1. Спросить: "What company do you work for?"
2. Спросить: "What do you sell? (one line)"
3. Спросить: "Who are your main competitors? (up to 5)"
4. Сохранить контекст для будущих сессий

Если вернувшийся пользователь:
1. Подтвердить: "Still at [Company] selling [Product]?"
2. Спросить: "Same competitors, or any new ones to add?"
```

**Фаза 2: Исследовать вашу компанию**

```
Веб-поиски:
1. "[Your company] product"           → Текущие предложения
2. "[Your company] pricing"           → Ценовая модель
3. "[Your company] news"              → Свежие анонсы (90 дней)
4. "[Your company] changelog releases" → Что вы выкатили
5. "[Your company] vs [competitor]"    → Существующие сравнения
```

**Фаза 3: Исследовать каждого конкурента**

```
По каждому конкуренту запустить:
1. "[Competitor] product features"          → Что они предлагают
2. "[Competitor] pricing"                   → Как берут плату
3. "[Competitor] news"                      → Свежие анонсы
4. "[Competitor] changelog releases"        → Что выкатили (90 дней)
5. "[Competitor] reviews G2 Capterra TrustRadius" → Тональность клиентов
6. "[Competitor] vs alternatives"           → Как позиционируются
7. "[Competitor] customers"                 → Кто их использует
8. "[Competitor] careers"                   → Сигналы найма (их стратегия)
9. "[Competitor] brand voice about page"    → Стиль тона и сообщений
```

**Фаза 4: Анализ бренд-войса по каждому конкуренту**

```
По каждому конкуренту проанализируйте текст их сайта и маркетинг на:
- Уровень формальности (формальный ↔ casual, оценка 1–100)
- Характеристики тона: профессиональный, разговорный, технический, смелый, дружелюбный
- Перспектива: 1-е лицо ("we"), 2-е лицо ("you"), 3-е лицо
- Ключевые пиллары сообщений (что они повторяют)
- Эмоциональный посыл: страх, амбиция, эффективность, сообщество
- Читабельность: сложный/технический vs. доступный

Сравните со своим бренд-войсом:
- Где они звучат похоже на вас? (риск дифференциации)
- Где они противоположны вам? (используйте контраст)
- Какую эмоциональную территорию они занимают? (избегать или оспаривать)
```

**Фаза 5: Подтянуть подключённые источники (если доступны)**

```
Если подключена CRM:
1. Запросить closed-won сделки с полем конкурента = [Competitor]
2. Запросить closed-lost сделки с полем конкурента = [Competitor]
3. Извлечь паттерны win/loss и win rate

Если подключены docs:
1. Поиск "battlecard [competitor]"
2. Подтянуть существующие документы позиционирования

Если подключён chat:
1. Поиск упоминаний "[Competitor]" (последние 90 дней)
2. Извлечь полевую разведку и инсайты коллег

Если подключены transcripts:
1. Поиск в звонках упоминаний "[Competitor]"
2. Извлечь возражения и клиентские цитаты о конкуренте
```

---

### 4.2 Структура данных конкурента

```yaml
competitor:
  name: "[Name]"
  website: "[URL]"
  profile:
    founded: "[Year]"
    funding: "[Stage + amount]"
    employees: "[Count]"
    target_market: "[Who they sell to]"
    pricing_model: "[Per seat / usage / etc.]"
    market_position: "[Leader / Challenger / Niche]"

  what_they_sell: "[Product summary]"
  their_positioning: "[How they describe themselves]"

  brand_voice:
    formality_score: "[0-100]"
    tone: "[Professional / Conversational / Technical / Bold]"
    perspective: "[We / You / Third person]"
    key_pillars: ["[Pillar 1]", "[Pillar 2]", "[Pillar 3]"]
    emotional_appeal: "[Fear / Ambition / Efficiency / Community]"
    vs_your_voice: "[How to exploit the contrast]"

  recent_releases:
    - date: "[Date]"
      release: "[Feature/Product]"
      impact: "[Why it matters]"

  where_they_win:
    - area: "[Area]"
      advantage: "[Their strength]"
      how_to_handle: "[Your counter]"

  where_you_win:
    - area: "[Area]"
      advantage: "[Your strength]"
      proof_point: "[Evidence]"

  pricing:
    model: "[How they charge]"
    entry_price: "[Starting price]"
    enterprise: "[Enterprise pricing]"
    hidden_costs: "[Implementation, overage, etc.]"
    talk_track: "[How to discuss pricing comparison]"

  talk_tracks:
    early_mention: "[Strategy if they come up early in deal]"
    displacement: "[Strategy if customer currently uses them]"
    late_addition: "[Strategy if added late to eval]"
    voice_contrast: "[Emphasize your voice/positioning contrast]"

  objections:
    - objection: "[What customer says]"
      response: "[How to handle]"

  landmines:
    - "[Question that exposes their weakness naturally]"
    - "[Question about hidden cost or implementation complexity]"

  win_loss:  # If CRM connected
    win_rate: "[X]%"
    common_win_factors: "[What predicts wins against them]"
    common_loss_factors: "[What predicts losses against them]"
    key_battleground_deals: "[Deal types where this matters most]"
```

---

### 4.3 Анализ паттернов win/loss

Запускайте после 10+ конкурентных сделок, чтобы выявить паттерны:

```
Win Patterns (сделки, выигранные против Competitor X):
- Типичная персона покупателя: [какой архетип выигрывает]
- Типичный размер сделки: [диапазон $X–$Y]
- Типичный кейс, склонивший чашу: [конкретная возможность]
- Типичный профиль чемпиона: [должность/роль]
- Типичное снятое возражение: [что мы преодолели]

Loss Patterns (сделки, проигранные Competitor X):
- Типичный сценарий проигрыша: [что спровоцировало проигрыш]
- Решающий пробел в фичах: [что у них было, чего не было у нас]
- Решающий пробел в цене: [требовавшаяся скидка]
- Чемпион, который не адвокировал: [почему не стал]
- Конкурентный ход, сработавший против нас: [их тактика]

Countermeasures (контрмеры):
- Для сценариев выигрыша: удвоить ставку на [сильную сторону], вести с [угла]
- Для сценариев проигрыша: дисквалифицировать раньше, улучшить [область], добавить [proof point]
```

---

### 4.4 Структура HTML-батлкарты

Батлкарта — это самодостаточный HTML-файл со следующим:

**Стартовый вид — Матрица сравнения:**
- Сетка сравнения фич (вы vs. каждый конкурент)
- Таблица сравнения цен
- Диаграмма рыночного позиционирования
- Индикаторы win rate (если подключена CRM)
- Быстрый гид win/loss по каждому конкуренту

**Вкладки конкурентов (клик для раскрытия каждой):**
- Профиль компании (размер, финансирование, целевой рынок)
- Сводка бренд-войса + контраст с вашим
- Свежие релизы (последние 90 дней)
- Где они выигрывают vs. где выигрываете вы
- Разведка по ценам + обнажение скрытых издержек
- Talk track'и (early mention / displacement / late addition)
- Карточка обработки возражений
- Вопросы-мины

**Визуальный дизайн:**
```css
:root {
    --bg-primary: #0a0d14;
    --bg-elevated: #0f131c;
    --bg-surface: #161b28;
    --text-primary: #ffffff;
    --text-secondary: rgba(255, 255, 255, 0.7);
    --accent: #3b82f6;
    --you-win: #10b981;
    --they-win: #ef4444;
    --tie: #f59e0b;
}
```

**Каденция обновления:**

| Триггер | Действие |
|---------|--------|
| Ежемесячно | Быстрое обновление — релизы, новости, цены |
| Перед крупной сделкой | Глубокое обновление по конкретному конкуренту |
| После win/loss | Обновить паттерны |
| Анонс конкурента | Немедленное обновление |

---

### 4.5 Шаблоны talk track'ов

#### Когда конкурент всплывает рано (клиент упоминает его проактивно)

```
"[Competitor] is a solid option and I'd expect them to be on your list.
Here's what I'd suggest — let's first make sure we're aligned on what
you actually need to solve. Then you'll have a clear lens to evaluate
both of us on what matters. Does that make sense?

[If they push on comparison]

The biggest differences I hear from customers who've evaluated both:
[Difference 1 in their language, not yours]
[Difference 2 tied to their specific pain point]

The best way to make this concrete is [landmine question]."
```

#### Вытеснение (клиент сейчас использует конкурента)

```
"I appreciate you sharing that. A lot of our customers came from
[Competitor]. Can I ask — what's prompting you to look at alternatives
right now? [Let them answer]

[After they answer]
That makes sense. That's actually one of the areas where [your product]
was designed differently — [specific differentiator in their context].
Mind if I show you how that works?"
```

#### Конкурентные вопросы-мины (примеры)

```
По сложности ценообразования:
"How does [Competitor]'s pricing scale as your usage grows?"

По внедрению:
"What does the typical implementation timeline look like with [Competitor]?"

По поддержке:
"When something breaks at 2am, how does support work with [Competitor]?"

По владению данными:
"If you were to switch away from [Competitor], how easy is it to export your data?"

По роадмапу:
"Have you had a chance to talk to [Competitor] about their roadmap for [area you win in]?"
```

---

## Раздел 5: Аутрич и создание контента

### Обзор

```
┌─────────────────────────────────────────────────────────────────┐
│                   АУТРИЧ И СОЗДАНИЕ КОНТЕНТА                     │
├─────────────────────────────────────────────────────────────────┤
│  ВСЕГДА (работает автономно через веб-поиск)                     │
│  ✓ Сначала исследование — никогда не шлите дженерик-аутрич      │
│  ✓ Структура письма AIDA с персонализированной зацепкой         │
│  ✓ Запрос на коннект в LinkedIn + сообщение-фоллоу-ап           │
│  ✓ Последовательность фоллоу-апов (Day 3, Day 7, Day 14 break-up)│
│  ✓ Валидация бренд-войса перед отправкой                        │
│  ✓ Планирование каденции на основе контент-пилларов            │
├─────────────────────────────────────────────────────────────────┤
│  УСИЛЕНО (когда вы подключаете свои инструменты)                 │
│  + Enrichment: верифицированный email, телефон, детали бэкграунда│
│  + CRM: контекст прошлых отношений, существующие контакты       │
│  + Email: создание черновика прямо в вашем инбоксе              │
└─────────────────────────────────────────────────────────────────┘
```

### Триггерные фразы

- "Draft outreach to [Person/Company]"
- "Write cold email to [Prospect]"
- "Reach out to [Name]"
- "Create follow-up sequence for [Company]"
- "Check brand voice of this email"

---

### 5.1 Методология аутрича «сначала исследование»

**Никогда не составляйте черновик до исследования.** Всегда выполняйте в этом порядке:

```
Step 1: Research (всегда происходит первым)
  ├── Веб-поиск: компания + человек
  ├── + Enrichment: верифицированная контактная инфо, бэкграунд (если подключено)
  └── + CRM: прошлые отношения (если подключено)

Step 2: Identify Hook (порядок приоритета)
  1. Триггерное событие (финансирование, новый найм, запуск продукта, новости) → Самое своевременное
  2. Общий контакт → Социальное доказательство
  3. Их контент (пост, статья, доклад, подкаст) → Показывает, что вы исследовали
  4. Инициатива компании (новый продукт, экспансия, отчётность) → Релевантна роли
  5. Боль по роли (универсальна для их функции) → Наименее личная, но валидна

Step 3: Draft (на основе исследования + зацепки)
  ├── Персонализированное открытие (из исследования)
  ├── Релевантная зацепка (их заявленные приоритеты)
  ├── Proof point (результат похожей компании)
  └── Низкофрикционный CTA

Step 4: Brand Voice Validation
  ├── Соответствует ли тон вашим бренд-гайдлайнам?
  ├── Уместна ли формальность для их уровня?
  ├── Только plain text (без markdown в письмах)?
  └── Меньше 150 слов для холодного аутрича?

Step 5: Deliver
  ├── Черновик письма (если доступен email-коннектор)
  ├── Шаблон LinkedIn-сообщения
  └── Копия в буфер обмена
```

---

### 5.2 Структура письма AIDA

**Правила темы письма:**
- Меньше 50 символов
- Персонализирована (их компания, роль или инициатива)
- Без спам-триггерных слов (FREE, LIMITED TIME, URGENT)
- Движима любопытством, а не питчем

**Структура тела:**

```
ATTENTION: [Личная зацепка — 1 предложение, показывающее, что вы их исследовали]
           Ссылка: новости, финансирование, контент, общий контакт, найм

INTEREST:  [Их вероятный вызов в 1-2 предложениях]
           Обрамите вокруг их роли и индустрии, не вашего продукта

DESIRE:    [Краткий proof point — похожая компания, конкретный результат]
           "We helped [Similar company] achieve [Specific outcome]"
           Держите конкретно: сэкономленное время, добавленная выручка, снижение затрат

ACTION:    [Одна чёткая, низкофрикционная просьба]
           Опции: "Worth a 15-min call?", "Open to a quick look?",
                    "Can I send over more detail?", "Happy to share a demo?"

SIGNATURE: [Имя, должность, компания, опционально одна строка с ценностным предложением]
```

**Пример — Холодный аутрич:**

```
Subject: Notion's AI scaling + a thought

Hi David,

Saw Notion's AI rollout is gaining serious traction — congrats.
With 5 ML roles open, seems like you're scaling fast.

Curious how you're thinking about inference infrastructure as usage
grows. We helped [Similar Company] cut their AI serving costs 40%
while improving latency.

Worth a 15-min call to see if relevant to your roadmap?

Best,
[Name]
```

**Чего НЕ делать:**
- "I hope this email finds you well" → Удалить
- "I'm reaching out because..." → Удалить
- "I wanted to introduce myself..." → Удалить
- Использовать **bold** или *italic* в теле письма (markdown не отрендерится)
- Больше одного CTA
- Перечислять 5 фич в теле
- "Congrats on your role" без какого-либо конкретного контекста

---

### 5.3 Сообщения в LinkedIn

**Запрос на коннект (< 300 символов):**

```
Hi [Name], [Mutual connection / shared interest / specific observation].
Would love to connect. No pitch — just find your work on [topic] interesting.
```

**Сообщение-фоллоу-ап (после коннекта, через 24–48 часов):**

```
Thanks for connecting! Saw you're working on [initiative] at [Company].

[Value-first: relevant insight, article, framework related to their work]

Happy to share more context if useful. No pressure either way.

[Name]
```

**Правила:**
- Никогда не питчите в запросе на коннект
- Ведите фоллоу-ап ценностью, не просьбой
- Держите запрос на коннект меньше 300 символов
- Ссылайтесь на что-то конкретное — никаких "I came across your profile"

---

### 5.4 Последовательность фоллоу-апов

После первого письма следуйте этой каденции, если нет ответа:

**Day 3 — Follow-Up 1 (новый угол):**

```
Subject: Re: [Original subject line]

Hi [Name],

Wanted to add one thing I forgot to mention — [new insight or value add].

If it's not relevant right now, no worries at all. Just thought it might
be useful given [specific context from research].

[Name]
```

**Day 7 — Follow-Up 2 (другое ценностное предложение):**

```
Subject: [Company] + [your product]: quick question

Hi [Name],

I'll keep this short. [Different angle than email 1 — different use case
or different pain point relevant to their role].

We saw [result] with [similar company] by [specific approach].

Worth 15 minutes?

[Name]
```

**Day 14 — Break-Up письмо:**

```
Subject: Closing the loop

Hi [Name],

I've reached out a few times — I'm guessing the timing isn't right,
which is completely fine.

I'll stop following up, but if [trigger event — initiative, goal, problem]
becomes a priority, I'd love to reconnect.

[Name]
```

---

### 5.5 Шаблоны сценариев аутрича

#### Тёплый аутрич (встречались / общий контакт)

```
Subject: Following up from [Context — event, intro, conversation]

Hi [Name],

[Reference to how you know them or who connected you — specific detail].

[Why reaching out now — their news, trigger, or your relevance to a
current initiative they're running].

[Specific value you can offer in this context].

[CTA]

[Name]
```

#### Реактивация (пропал после активного разговора)

```
Subject: [Short, curiosity-driven — not guilt-inducing]

Hi [Name],

It's been a while. I noticed [something new and relevant at their company
— news, hire, launch, announcement].

Thought it might be a good time to reconnect — [brief reason tied to that
trigger].

Are you still thinking about [original pain point / initiative]?

[Name]
```

#### Фоллоу-ап после мероприятия

```
Subject: Great [meeting/conversation] at [Event]

Hi [Name],

Really enjoyed [specific topic or moment from your conversation] — the
point about [their insight] was something I'm still thinking about.

[Value-add: article, intro, resource connected to what you discussed]

Would love to continue the conversation — [soft CTA for 30-min call].

[Name]
```

---

### 5.6 Анализ бренд-войса для аутрича

Перед отправкой любого аутрича проверьте его на соответствие профилю вашего бренд-войса:

```
Brand Voice Dimensions (измерения бренд-войса):
1. Formality Score (оценка формальности): [0-100]
   - 0-30: Casual/дружелюбный ("Hey!", сокращения, сленг)
   - 31-60: Полуформальный (профессиональный, но доступный)
   - 61-100: Формальный (титулы, без сокращений, структурированный)

2. Tone Attributes (атрибуты тона, выберите 2-3):
   - Professional | Conversational | Technical | Bold | Empathetic | Direct

3. Perspective (перспектива): First person (we) / Second person (you-focused) / Mixed

4. Readability Target (целевая читабельность): [уместная для аудитории]
   - C-suite: Чётко и хлёстко (Flesch score 60+)
   - Technical: Может быть детальнее (Flesch score 40-60)
   - Operations: Процедурная ясность (Flesch score 50-70)

Validation Checklist (чек-лист валидации):
- [ ] Формальность уместна для уровня получателя
- [ ] Тон консистентен с бренд-гайдлайнами
- [ ] You-focused (о их проблеме, не о вашем продукте)
- [ ] Только plain text (без markdown-форматирования)
- [ ] Меньше 150 слов для холодного аутрича
- [ ] Только один CTA
- [ ] Личная зацепка показывает реальное исследование
```

---

### 5.7 Планирование каденции на основе контент-пилларов

Для аккаунтов в активном пайплайне спланируйте контент-движимую мульти-касательную каденцию:

**Соотношение контент-пилларов (40/25/25/10):**

| Пиллар | % касаний | Пример |
|--------|--------------|---------|
| **Education** | 40% | Отраслевой инсайт, исследование, фреймворк, который они могут использовать |
| **Social Proof** | 25% | Кейс от похожей компании, цитата клиента |
| **Product Insight** | 25% | Демо кейса, фича, релевантная их боли |
| **Direct Ask** | 10% | Явный CTA — запрос встречи, предложение демо |

**Пример 4-недельной контент-каденции:**

```
Week 1, Touch 1: Education — "Here's a trend in [their industry]..."
Week 1, Touch 3: Social Proof — "A company like yours did [result]..."
Week 2, Touch 5: Product Insight — "This is how [feature] solves [their pain]..."
Week 2, Touch 7: Direct Ask — "Worth 15 minutes this week?"
Week 3, Touch 9: Education — "Thought you'd find this relevant..."
Week 3, Touch 11: Social Proof — "[Relevant customer quote]..."
Week 4, Touch 13: Direct Ask — "Break-up email..."
```

**Оптимизация под конкретную платформу:**

| Платформа | Тон | Длина | Частота |
|----------|------|--------|-----------|
| **Email** | Полуформальный, прямой | <150 слов cold / <250 warm | Макс 2–3 раза в неделю |
| **LinkedIn** | Профессиональный, вдумчивый | 300 символов коннект / 500 фоллоу-ап | 1–2 раза в неделю |
| **LinkedIn DM** | Разговорный | Меньше 300 символов | Скупо после коннекта |

---

### 5.8 Формат вывода аутрича

```markdown
# Outreach Draft: [Person] @ [Company]
**Generated:** [Date] | **Research Sources:** [Web, Enrichment, CRM]

---

## Research Summary

**Target:** [Name], [Title] at [Company]
**Hook:** [Why reaching out now — personalized angle]
**Goal:** [What you want from this outreach]

---

## Email Draft

**To:** [email if known]
**Subject:** [Personalized subject line]

---

[Email body — AIDA structure, plain text]

---

**Subject Line Alternatives:**
1. [Option 2]
2. [Option 3]

---

## LinkedIn Message (backup / parallel)

**Connection Request (< 300 chars):**
[Short, no-pitch connection request]

**Follow-up Message (after connected):**
[Value-first message under 300 chars]

---

## Why This Approach

| Element | Based On |
|---------|----------|
| Opening | [Research finding] |
| Hook | [Their priority/pain point] |
| Proof | [Relevant customer story] |
| CTA | [Low-friction ask] |

---

## Brand Voice Validation

| Check | Pass? |
|-------|-------|
| Formality appropriate | [Y/N] |
| You-focused tone | [Y/N] |
| Plain text only | [Y/N] |
| Under 150 words | [Y/N] |
| Single CTA | [Y/N] |

---

## Follow-up Sequence

**Day 3:**
[New angle follow-up]

**Day 7:**
[Different value prop]

**Day 14:**
[Break-up email]
```

---

## Раздел 6: Материалы продаж и поставляемые артефакты

### Обзор

Генерируйте кастомные материалы продаж, подогнанные под вашего клиента, аудиторию и цели. Поддерживает интерактивные лендинги, презентационные деки, executive one-pager'ы и демо рабочих процессов/архитектуры.

### Триггерные фразы

- "Create an asset / landing page / one-pager for [Company]"
- "Build a demo for [Prospect]"
- "Make a workflow demo for [Company]"
- "Create a deck for my meeting with [Company]"

---

### 6.1 Типы материалов

| Формат | Описание | Лучше всего для | Время сборки |
|--------|-------------|----------|------------|
| **Interactive Landing Page** | Многовкладочная HTML-страница с демо, метриками, калькуляторами | Согласование с руководством, интро, ценностное предложение | Среднее |
| **Deck-Style** | Линейные слайды, готовые к презентации | Формальные встречи, большие аудитории | Среднее |
| **One-Pager** | Одностраничное executive-резюме (один скролл) | Раздаточные материалы, быстрые резюме | Быстро |
| **Workflow / Architecture Demo** | Интерактивная анимированная диаграмма | Технические глубокие погружения, POC-демо, интеграции | Медленно |

---

### 6.2 7-фазный процесс создания материалов

#### Фаза 0: Определение контекста и сбор входных данных

**Определить контекст продавца:**
```
1. Извлечь домен из email пользователя
2. Поиск: "[domain]" company products services
3. Если компания с одним продуктом → авто-заполнить
4. Если мультипродукт → спросить: "Which product is this asset for?"
5. Если неизвестно → спросить: "What are you selling?"
```

**Собрать контекст клиента:**

| Поле | Промт | Обязательно |
|-------|--------|----------|
| Company | "Which company is this asset for?" | Да |
| Key contacts | "Who are the key contacts? (names, roles)" | Нет |
| Deal stage | "What stage is this deal?" | Да |
| Pain points | "What pain points have they shared?" | Нет |
| Materials | "Upload transcripts, emails, or notes" | Нет |

**Стадии сделки:**
- Intro / First meeting → Осведомлённость/discovery
- Discovery → Квалификация проблемы
- Evaluation / Technical review → Сравнение фич
- POC / Pilot → Proof of concept
- Negotiation → Обоснование ценности
- Close → Финальное обязательство

**Собрать контекст аудитории:**

| Тип аудитории | Главная забота | Ведущий раздел |
|--------------|-----------------|--------------|
| Executive (C-suite, VPs) | ROI / Влияние на бизнес | Strategic Fit → Business Impact |
| Technical (Architects, Engineers) | Архитектура / Безопасность | Integration → Security → Performance |
| Operations (IT, Procurement) | Рабочий процесс / Управление изменениями | Implementation → Support |
| Mixed / Cross-functional | Баланс стратегического + тактического | Баланс с вкладочными уровнями глубины |

**Выбрать формат:**

```
"What format works best for this?"
→ Interactive landing page / Deck-style / One-pager / Workflow demo
```

#### Фаза 1: Исследование (адаптивное)

**Оценить насыщенность контекста:**

| Уровень | Индикаторы | Глубина исследования |
|-------|------------|----------------|
| Rich | Загружены транскрипты, детальные боли | Лёгкое — только заполнить пробелы |
| Moderate | Какой-то контекст, нет транскриптов | Среднее — компания + индустрия |
| Sparse | Только название компании | Глубокое — полный проход исследования |

**Всегда исследовать:**
1. `"[Company]" annual report CEO strategy priorities 2025 2026`
2. `"[Company]" CEO CTO CIO 2025` — извлечь имена, должности, цитаты
3. `"[Company]" brand guidelines` — первичные/вторичные цвета
4. Отраслевые тренды: `"[Industry]" challenges trends 2025 2026`

**Если moderate/sparse, также исследовать:**
5. Технологический ландшафт: `"[Company]" technology stack tools`
6. Конкурентный контекст: `"[Company]" vs [your competitors]`

**Если загружены транскрипты/материалы:**
7. Извлечь заявленные боли, критерии решения, возражения, сроки
8. Подтянуть точные клиентские цитаты (используйте их язык в материале)
9. Отметить конкретную терминологию, акронимы, внутренние названия проектов

#### Фаза 2: Решение по структуре

**Интерактивный лендинг по цели:**

| Цель | Рекомендуемый порядок разделов |
|---------|--------------------------|
| Intro / Первое впечатление | Company Fit → Solution Overview → Use Cases → Why Us → Next Steps |
| Discovery follow-up | Their Priorities → How We Help → Relevant Examples → ROI Framework → Next Steps |
| Технический глубокий разбор | Architecture → Security → Integration → Performance → Support |
| Согласование с руководством | Strategic Fit → Business Impact → ROI Calculator → Risk Mitigation → Partnership |
| POC-предложение | Scope → Success Criteria → Timeline → Team → Investment → Next Steps |
| Закрытие сделки | Value Summary → Pricing → Implementation Plan → Terms → Sign-off |

**Структура One-Pager:**

```
┌─────────────────────────────────────────────────────────┐
│ HERO: "[Prospect Goal] with [Product]"                  │
│ Subhead: [Tied to their stated priority]                │
├─────────────────────────────────────────────────────────┤
│ KEY POINT 1    │ KEY POINT 2    │ KEY POINT 3           │
│ [Icon + 2-3    │ [Icon + 2-3    │ [Icon + 2-3           │
│ sentences]     │ sentences]     │ sentences]            │
├─────────────────────────────────────────────────────────┤
│ PROOF POINT: [Metric, quote, or case study]             │
├─────────────────────────────────────────────────────────┤
│ CTA: [Clear next action]  │  [Contact info]             │
└─────────────────────────────────────────────────────────┘
```

**Структура Workflow Demo (по сложности):**

| Сложность | Компоненты | Структура |
|------------|------------|-----------| 
| Simple | 3–5 | Однопанельная диаграмма с аннотациями к шагам |
| Medium | 5–10 | Масштабируемый холст с пошаговым прохождением |
| Complex | 10+ | Многослойная (обзор → детали) с гид-туром |

#### Фаза 3: Генерация контента

**Базовые принципы для всех материалов:**
- Ссылайтесь на **конкретные боли** из входных данных или транскриптов
- Используйте **их язык** — их терминологию, их приоритеты, их акронимы
- Явно отображайте ваш продукт на их потребности
- Включайте **proof points** (кейсы, метрики, цитаты клиентов)
- Должно ощущаться подогнанным, не шаблонным

**Шаблоны разделов:**

```
Hero / Intro:
Headline: "[Prospect's Goal] with [Seller's Product]"
Subhead: Привязать к их заявленному приоритету или топ-вызову индустрии
Metrics: 3-4 ключевых факта о клиенте (показывает проделанную работу)

Their Priorities (только для discovery follow-up):
- Используйте по возможности точные слова из их транскрипта/заметок
- Покажите, что вы слушали; свяжите каждый с тем, как вы помогаете

Solution Mapping:
По каждой боли:
├── Вызов (в их словах)
├── Как [Product] его адресует
├── Proof point или пример
└── Исход / выгода (квантифицированный)

ROI / Business Case:
Интерактивный калькулятор:
├── Inputs: релевантные их бизнесу из исследования
│   ├── Количество пользователей/команд
│   ├── Текущие затраты или потраченное время
│   └── Ожидаемое улучшение %
├── Outputs:
│   ├── Годовая ценность / экономия
│   ├── Стоимость решения
│   ├── Чистый ROI и срок окупаемости
└── Допущения чётко заявлены (редактируемые)

Next Steps / CTA:
├── Чёткое действие, согласованное с целью
├── Конкретный следующий шаг (не расплывчатое "let's chat")
├── Контактная информация
├── Предлагаемые сроки
└── Что происходит после того, как они действуют
```

#### Фаза 4: Визуальный дизайн (только для не-веб выводов)

Для деков, one-pager'ов и демо рабочих процессов:

```css
:root {
    /* Prospect brand colors (extracted from research) */
    --brand-primary: #[extracted];
    --brand-secondary: #[extracted];

    /* Dark theme */
    --bg-primary: #0a0d14;
    --bg-surface: #161b28;
    --text-primary: #ffffff;
    --text-secondary: rgba(255, 255, 255, 0.7);
    --accent: var(--brand-primary);
    --success: #10b981;
    --warning: #f59e0b;
}
```

**Типографика:**
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
h1: 2.5rem, font-weight: 700
h2: 1.75rem, font-weight: 600
body: 1rem, line-height: 1.6
```

**Запасные бренд-цвета по индустрии:**

| Индустрия | Primary | Secondary |
|----------|---------|-----------|
| Technology | #2563eb | #7c3aed |
| Finance | #0f172a | #3b82f6 |
| Healthcare | #0891b2 | #06b6d4 |
| Manufacturing | #ea580c | #f97316 |
| Retail | #db2777 | #ec4899 |
| Default | #3b82f6 | #8b5cf6 |

> **Для интерактивных лендингов:** Загрузите скилл `website-building` для всего визуального дизайна, типографики, цветовых систем и CSS.

#### Фаза 5: Уточняющие вопросы (всегда спрашивайте перед сборкой)

Перед сборкой покажите, что вы поняли, и подтвердите:

```
"Here's what I'm planning to build:

Asset: [Format] for [Prospect Company]
Audience: [Type] — specifically [roles if known]
Goal: [Purpose] → driving toward [desired action]
Key themes: [2-3 main points to emphasize]

[For workflow demos:]
Components: [List of systems]
Flow: [Step 1] → [Step 2] → [Step 3] → ...
```

**Стандартные вопросы (все форматы):**
1. "Does this match your vision?"
2. "What's the ONE thing this must nail to succeed?"
3. "Tone preference? (Bold & confident / Consultative / Technical & precise)"
4. "Focused and concise, or comprehensive?"

**Максимум 2 раунда вопросов.** Если всё ещё неоднозначно, решите и отметьте: "I went with X — easy to adjust if you prefer Y."

#### Фаза 6: Сборка и поставка

**Формат вывода:**
- Самодостаточный HTML-файл (весь CSS и JS инлайн)
- Без внешних зависимостей, кроме Google Fonts
- Один файл для лёгкого шеринга
- Именование файла: `[ProspectName]-[format]-[YYYY-MM-DD].html`

**Сообщение о поставке:**

```markdown
## ✓ Asset Created: [Prospect Name]

[View your asset]

---

Summary:
- Format: [Interactive Page / Deck / One-Pager / Workflow Demo]
- Audience: [Type and roles]
- Purpose: [Goal] → [Desired action]
- Sections/Steps: [Count]

---

Deployment Options:
- Static hosting: Upload to Netlify, Vercel, GitHub Pages, AWS S3
- Password protection: Available on most hosting platforms
- Direct share: Send the HTML file — fully self-contained
```

#### Фаза 7: Поддержка итераций

| Запрос пользователя | Действие |
|--------------|--------|
| "Change the colors" | Перегенерировать с новой палитрой, контент сохранить |
| "Add a section on X" | Вставить новый раздел, сохранить поток |
| "Make it shorter" | Сжать, приоритизировать ключевые точки |
| "The flow is wrong" | Перестроить архитектуру из правки |
| "Use our brand instead" | Переключить с бренда клиента на бренд продавца |
| "Add more detail on step 3" | Расширить именно этот раздел |
| "Can I get this as a PDF?" | Предоставить версию, оптимизированную под печать |

---

### 6.3 Чек-лист качества

**Контент:**
- [ ] Название компании клиента написано правильно везде
- [ ] Имена руководства актуальны (не устаревшие)
- [ ] Боли точно отражают входные данные/транскрипты
- [ ] Не осталось текста-заглушки
- [ ] Proof points точны и со ссылкой на источник

**Визуал:**
- [ ] Бренд-цвета применены корректно
- [ ] Весь текст читаем (достаточный контраст)
- [ ] Анимации плавные, не отвлекающие
- [ ] Адаптивность под мобильные (если интерактивная страница)

**Функционал:**
- [ ] Все вкладки/разделы загружаются корректно
- [ ] Интерактивные элементы работают (калькуляторы, демо)
- [ ] Навигация интуитивна
- [ ] CTA чёткий и кликабельный

**Профессионализм:**
- [ ] Тон соответствует аудитории
- [ ] Нет опечаток или грамматических ошибок
- [ ] Ощущается подогнанным, не шаблонным

---

## Раздел 7: Приоритизация сделок и управление пайплайном

### Обзор

```
┌─────────────────────────────────────────────────────────────────┐
│              ПРИОРИТИЗАЦИЯ СДЕЛОК И УПРАВЛЕНИЕ ПАЙПЛАЙНОМ         │
├─────────────────────────────────────────────────────────────────┤
│  ВСЕГДА (работает автономно)                                     │
│  ✓ Дневной брифинг из предоставленных встреч и сделок           │
│  ✓ Приоритизация сделок со скорингом RICE для фокуса пайплайна  │
│  ✓ Предложенные топ-3 действия на день                          │
│  ✓ Режим резюме конца дня                                       │
│  ✓ Режим быстрого брифинга (< 2 минут)                          │
├─────────────────────────────────────────────────────────────────┤
│  УСИЛЕНО (когда вы подключаете свои инструменты)                 │
│  + Calendar: авто-подтягивание сегодняшних встреч с участниками │
│  + CRM: открытый пайплайн, скоро закрываются, застойные, задачи │
│  + Email: непрочитанные от ключевых аккаунтов, ждут ответа      │
│  + Enrichment: ночные сигналы по вашим аккаунтам                │
└─────────────────────────────────────────────────────────────────┘
```

### Триггерные фразы

- "Morning briefing" / "Start my day" / "Daily brief"
- "What's on my plate today?"
- "Prioritize my deals / pipeline"
- "Quick brief" / "tldr my day"
- "Wrap up my day" / "End of day summary"

---

### 7.1 Рабочий процесс дневного брифинга

**Шаг 1: Собрать контекст**

```
Если коннекторы активны:
1. Calendar → Получить сегодняшние внешние встречи
   Подтянуть: время, участников, заголовок, описание
2. CRM → Запросить ваш пайплайн
   Подтянуть: открытые возможности, сделки, закрывающиеся в 7 дней, застойные (7+ дней без активности)
   Подтянуть: просроченные задачи, грядущие задачи на сегодня
3. Email → Приоритетные сообщения
   Подтянуть: непрочитанные с доменов контактов возможностей
   Подтянуть: отправленные сообщения без ответа (3+ дня)
4. Enrichment → Ночные сигналы
   Подтянуть: финансирование, найм, новости по открытым аккаунтам

Если коннекторов нет:
Спросить пользователя:
1. "What meetings do you have today?"
2. "What deals are you focused on? Any closing soon or needing attention?"
3. "Anything urgent I should know about?"
```

**Шаг 2: Ранжирование приоритетов**

```
Уровни приоритета:
1. URGENT:  Сделка закрывается сегодня/завтра, ещё не выиграна
2. HIGH:    Встреча сегодня со сделкой >$50K или стратегической
3. HIGH:    Непрочитанное письмо от лица, принимающего решения (>3 дней)
4. MEDIUM:  Сделка закрывается на этой неделе
5. MEDIUM:  Застойная сделка (7+ дней без активности)
6. LOW:     Задачи к концу недели

Логика приоритета #1:
- Если встреча с высокоценной сделкой сегодня → подготовить эту встречу
- Если сделка закрывается сегодня → сфокусироваться на активности закрытия
- Если срочное письмо от покупателя → ответить первым делом
- Иначе → самая высокоценная застойная сделка
```

**Шаг 3: Сгенерировать брифинг**

Собрать на основе доступных данных:
1. #1 Priority — Всегда включать
2. Today's Numbers — Если подключена CRM
3. Today's Meetings — Из календаря или ввода пользователя
4. Pipeline Alerts — Если подключена CRM
5. Email Priorities — Если подключён email
6. Suggested Actions — Всегда включать топ-3

---

### 7.2 Формат вывода дневного брифинга

```markdown
# Daily Briefing | [Day, Month Date]

---

## #1 Priority

**[Most important thing to do today]**
[Why it matters and what to do about it]

---

## Today's Numbers

| Open Pipeline | Closing This Month | Meetings Today | Action Items |
|---------------|-------------------|----------------|--------------|
| $[X]          | $[X]              | [N]            | [N]          |

---

## Today's Meetings

### [Time] — [Company] ([Meeting Type])
**Attendees:** [Names]
**Context:** [One-line: deal status, last touch, what's at stake]
**Prep:** [Quick action before this meeting]
**RICE Priority Score:** [Deal score from 7.3]

Run `call-prep [company]` for detailed meeting prep

---

## Pipeline Alerts

### Needs Attention
| Deal | Stage | Amount | Alert | Action |
|------|-------|--------|-------|--------|
| [Deal] | [Stage] | $[X] | [Why flagged] | [What to do] |

### Closing This Week
| Deal | Close Date | Amount | Confidence | Blocker |
|------|------------|--------|------------|---------|
| [Deal] | [Date] | $[X] | [H/M/L] | [If any] |

---

## Email Priorities

### Needs Response
| From | Subject | Received |
|------|---------|----------|
| [Name @ Company] | [Subject] | [Time] |

### Waiting On Reply
| To | Subject | Sent | Days Waiting |
|----|---------|------|--------------|
| [Name @ Company] | [Subject] | [Date] | [N] |

---

## Suggested Actions

1. **[Action]** — [Why now]
2. **[Action]** — [Why now]
3. **[Action]** — [Why now]

---

Run `call-prep [company]` before your meetings
Run `call-follow-up` after each call
```

---

### 7.3 Фреймворк RICE для приоритизации сделок

Адаптирован из PM-фреймворка приоритизации RICE (Reach × Impact × Confidence ÷ Effort) под управление пайплайном продаж.

**Скоринг сделок по RICE:**

| Измерение | Определение в продажах | Скоринг |
|-----------|-----------------|---------|
| **Reach** | Число стейкхолдеров / аккаунтов, которые открывает эта сделка (потенциал рефералов, расширение платформы) | Шкала 1–10 или оценочное число пользователей |
| **Impact** | Размер сделки × стратегическая ценность × качество логотипа клиента | Скоринг ниже |
| **Confidence** | Вероятность выигрыша на основе сигналов квалификации | % в виде десятичной дроби (0.1–1.0) |
| **Effort** | Оценочные усилия продаж, оставшиеся до закрытия (встречи, работа над POC, legal и т.д.) | Человеко-дни или недели |

**Формула RICE-скора:**
```
RICE Score = (Reach × Impact × Confidence) / Effort
```

**Таблица скоринга Impact (для продаж):**

| Impact Score | Эквивалент размера сделки | Стратегическая ценность |
|-------------|----------------------|-----------------|
| 4 (Massive) | >$250K ARR | Платформенная сделка, референсный логотип |
| 3 (High) | $50K–$250K ARR | Растущий аккаунт, сильный потенциал референса |
| 2 (Medium) | $10K–$50K ARR | Солидная сделка, ограниченное расширение |
| 1 (Low) | <$10K ARR | Транзакционная, низкая стратегическая ценность |
| 0.5 (Minimal) | <$5K ARR | Длинный хвост, высокие накладные расходы |

**Таблица скоринга Effort:**

| Effort Level | Метка | Описание |
|-------------|-------|-------------|
| 0.5 | XS | Готова к закрытию — только бумаги |
| 1 | S | 1–2 недели — мелкие финальные шаги |
| 2 | M | 2–4 недели — демо, legal, утверждение |
| 4 | L | 1–2 месяца — POC, мультистейкхолдер |
| 8 | XL | 2+ месяца — сложный enterprise |

**Пример скоринга сделок по RICE:**

```
Deal: Acme Corp
  Reach: 4 (платформенная сделка, может расшириться на 3 подразделения)
  Impact: 3 (high — $120K ARR, сильный логотип)
  Confidence: 0.7 (хороший чемпион, бюджет подтверждён, 70% вероятность выигрыша)
  Effort: 2 (medium — нужен 3-недельный финальный рывок)

  RICE Score = (4 × 3 × 0.7) / 2 = 4.2

Deal: Beta Inc
  Reach: 1 (один отдел, ограниченное расширение)
  Impact: 1 (low — $8K ARR)
  Confidence: 0.9 (чёткий сигнал покупки, чемпион вовлечён)
  Effort: 0.5 (XS — только бумаги)

  RICE Score = (1 × 1 × 0.9) / 0.5 = 1.8

Deal: Gamma Co (Strategic)
  Reach: 8 (отраслевой логотип, кейс готов)
  Impact: 4 (massive — $400K ARR + партнёрская экосистема)
  Confidence: 0.4 (ранняя стадия, чемпион ещё формируется)
  Effort: 8 (XL — сложный enterprise, 3 месяца впереди)

  RICE Score = (8 × 4 × 0.4) / 8 = 1.6
```

**Портфельный анализ для пайплайна:**

```
Quick Wins (высокий Confidence + низкий Effort):
- Beta Inc (RICE 1.8) → Закрыть на этой неделе

Big Bets (высокий Reach + Impact, более низкий Confidence):
- Gamma Co (RICE 1.6) → Инвестировать в формирование чемпиона

Core Focus (сбалансированные оценки):
- Acme Corp (RICE 4.2) → Топ-приоритет на эту неделю
```

---

### 7.4 Вывод скоринга пайплайна

```
============================================================
PIPELINE PRIORITIZATION — RICE SCORING
============================================================

Top Prioritized Deals

1. Acme Corp
   RICE Score: 4.2
   Reach: 4 | Impact: High ($120K) | Confidence: 70% | Effort: Medium
   Status: Final proposal sent, legal review pending
   Action: Follow up with VP Procurement on contract timeline

2. Delta Systems
   RICE Score: 3.1
   Reach: 3 | Impact: High ($85K) | Confidence: 65% | Effort: Small
   Status: Demo complete, champion building business case
   Action: Send champion kit + exec one-pager for internal approval

3. Zeta Corp
   RICE Score: 2.8
   Reach: 2 | Impact: Medium ($35K) | Confidence: 80% | Effort: XS
   Status: Verbal yes, paperwork not started
   Action: Send order form today

Portfolio Analysis:
  Total Pipeline: $[X]
  Quick Wins: [N] deals (close in <2 weeks)
  Big Bets: [N] deals (>$200K, need champion investment)
  Stale: [N] deals (7+ days no activity, needs re-engagement)

Today's Focus (RICE top 3):
  Q1 Actions: Close Zeta Corp, advance Acme legal, build Delta champion
```

---

### 7.5 Режим быстрого брифинга

Триггер: "quick brief" или "tldr my day"

```markdown
# Quick Brief | [Date]

**#1:** [Priority action — one sentence]

**Meetings:** [N] — [Company 1], [Company 2]

**Top Deal Alert:** [Deal] — [What needs to happen]

**Do Now:** [Single most important action with ETA]
```

---

### 7.6 Режим конца дня

Триггер: "wrap up my day" или "end of day summary"

```markdown
# End of Day | [Date]

**Completed:**
- [Meeting 1] — [Outcome: positive / neutral / negative, next step]
- [Meeting 2] — [Outcome]

**Pipeline Changes:**
- [Deal] moved to [Stage]
- [Deal] — new blocker surfaced: [description]

**RICE Score Updates:**
- [Deal] Confidence updated: [old%] → [new%] — reason: [why]
- [Deal] Effort updated: [old] → [new] — reason: [discovery meeting, POC started, etc.]

**Tomorrow's Focus (RICE-ranked):**
1. [Priority 1 — deal + action]
2. [Priority 2 — deal + action]
3. [Priority 3 — deal + action]

**Open Loops:**
- [ ] [Unfinished item with owner + due date]
- [ ] [Follow-up promised to prospect]
```

---

### 7.7 Индикаторы здоровья сделки

**Green (в графике):**
- Активный чемпион адвокирует внутри
- Бюджет подтверждён или выделен
- Сроки определены
- Согласованный следующий шаг в пределах 7 дней
- Вовлечённость нескольких стейкхолдеров

**Yellow (наблюдать):**
- Чемпион затихает (>5 дней без ответа)
- Сроки сдвинулись без объяснения
- Новый стейкхолдер добавлен поздно в процессе
- Упомянут конкурент, которого раньше не было
- Задержки закупок

**Red (под угрозой):**
- Нет контакта 10+ дней
- Сменилось лицо, принимающее решения
- Бюджет перемещён или сокращён
- Конкурент выбран для POC
- Legal-ревью застопорилось >2 недель

**Плейбук интервенций по цвету:**

| Статус | Интервенция |
|--------|-------------|
| Yellow — чемпион затих | Письмо реактивации чемпиона + аутрич к руководству |
| Yellow — сроки сдвинулись | Разговор "What changed?"; переквалифицировать срочность |
| Yellow — новый стейкхолдер | Быстро исследовать его (Раздел 2); получить интро от чемпиона |
| Red — нет контакта 10+ дней | Break-up письмо; реактивация через другой контакт |
| Red — конкурент в POC | Ускорить ваш POC; запросить совместную техническую сессию |
| Red — бюджет перемещён | ROI-разговор со стейкхолдером из финансов |

---

## Раздел 8: Уникальные возможности Perplexity Computer

Возможности, которые существуют только в Perplexity Computer и не могут быть воспроизведены в оффлайн/статичных средах вроде Claude Code.

---

### 8.1 Живое веб-исследование с данными в реальном времени

**Что делает:** Ищет по живому вебу в реальном времени, возвращая текущую информацию, опубликованную в течение часов или дней.

**Почему это важно для продаж:**
- Поймать анонсы финансирования в день, когда они случаются → запустить аутрич немедленно
- Найти смены руководства до того, как они появятся в LinkedIn (часто сначала анонсируют в прессе)
- Мониторить запуски продуктов конкурентов по мере их выхода
- Обнаруживать всплески найма, сигнализирующие о новой инициативе (они строят X → продавайте им Y)
- Подтягивать текущие цены с сайтов конкурентов (цены меняются; статичное знание — нет)

**Кейсы для продаж:**
```
Обнаружение триггерных событий:
- "[Company] funding announcement this week"
- "[Company] news today"
- "[Executive name] leaving [Company]"

Сигналы найма в реальном времени:
- "[Company] site:lever.co OR site:greenhouse.io"
- "[Company] VP of [function] new hire"

Живая разведка по конкурентам:
- "[Competitor] pricing 2026"
- "[Competitor] new features released"
```

---

### 8.2 Поиск по соцсетям (X/Twitter)

**Что делает:** Ищет по живым постам, тредам и ответам в X (бывший Twitter).

**Почему это важно для продаж:**
- Находить жалобы на конкурентов от реальных пользователей в реальном времени
- Выявлять клиентов, публично обсуждающих боли, которые вы решаете
- Отслеживать thought leadership руководителей для персонализации аутрича
- Мониторить анонсы конкурентов до того, как они попадут в мейнстрим-прессу

**Кейсы для продаж:**
```
Тональность по конкуренту:
from:[competitor_handle] product -is:retweet

Боли клиента:
"[pain point keyword]" "[competitor product]" is:reply

Мониторинг руководителя:
from:[prospect_ceo_handle] -is:retweet

Отраслевая беседа:
#[industry_hashtag] from:[prospect_company]
```

---

### 8.3 Деплой сайтов для материалов продаж

**Что делает:** Деплоит HTML-материалы продаж на живые URL (Netlify, Vercel и т.д.) прямо из разговора.

**Почему это важно для продаж:**
- Поделиться кастомным URL для клиента вместо вложения в письмо
- Защитить материалы паролем для конфиденциальных предложений
- Отслеживать открытия и вовлечённость (если добавлена аналитика)
- Обновлять материалы в реальном времени до и после встреч

**Опции деплоя:**
- Мгновенный деплой Netlify → `https://[your-company]-[prospect].netlify.app`
- Защита паролем для чувствительного контента по ценам или роадмапу
- Кастомный домен, если доступен

---

### 8.4 AI-генерация изображений и видео для материалов

**Что делает:** Генерирует оригинальные изображения и короткие видеоклипы с помощью AI-моделей.

**Почему это важно для продаж:**
- Создавать кастомные hero-изображения для лендингов под индустрию клиента
- Генерировать диаграммы рабочих процессов без необходимости в дизайнере
- Производить короткие видеоклипы-демо продукта для вложений в письма
- Создавать инфографику для резюме ROI или one-pager'ов

**Кейсы для продаж:**
```
Изображения:
- Hero-изображение для индустрии [Prospect] с вашим продуктом в фокусе
- Диаграмма рабочего процесса, показывающая процесс [Prospect] до/после
- Инфографика, визуально резюмирующая расчёт ROI

Видео:
- 8-секундный тизер продукта для футера письма
- Анимированное демо рабочего процесса (альтернатива интерактивному HTML)
- Персонализированное интро-видео "Hi [Prospect]"
```

---

### 8.5 400+ интеграций приложений (CRM, Email, Календарь, Чат)

**Что делает:** Подключается нативно к CRM-системам (Salesforce, HubSpot), email (Gmail, Outlook), календарю (Google, Outlook), чату (Slack, Teams) и 400+ другим приложениям.

**Почему это важно для продаж:**

| Интеграция | Что открывает |
|-------------|-----------------|
| **CRM (Salesforce, HubSpot)** | Авто-чтение истории аккаунта, записей контактов, пайплайна возможностей, лога активностей |
| **Email (Gmail, Outlook)** | Составление аутрича прямо в инбоксе, чтение контекста треда, отправка фоллоу-апов |
| **Calendar (Google, Outlook)** | Авто-определение сегодняшних встреч, подтягивание участников, планирование брифов подготовки |
| **Slack / Teams** | Чтение внутренних обсуждений аккаунта, выявление упоминаний конкурентов, тегирование коллег |
| **LinkedIn** | Обогащение профилей клиентов, поиск общих контактов, выявление общего контента |
| **Enrichment (Apollo, Clay, ZoomInfo)** | Верифицированные email, телефоны, оргсхемы, сигналы намерений |
| **Document storage (Notion, Confluence)** | Чтение существующих батлкарт, плейбуков, кейсов |
| **Call transcripts (Gong, Chorus, Otter)** | Подтягивание записей прошлых звонков, извлечение возражений и упоминаний конкурентов |

**Не требуется ручного копипаста.** Каждый рабочий процесс в этом скилле становится полностью автоматизированным, когда коннекторы активны.

---

### 8.6 Запланированный мониторинг (алерты по конкурентам, алерты по сделкам)

**Что делает:** Запускает повторяющиеся автоматизированные поиски по расписанию (ежедневно, еженедельно) и выявляет изменения с последнего запуска.

**Почему это важно для продаж:**

| Тип алерта | Расписание | За чем следить |
|-----------|----------|---------------|
| Новости конкурентов | Еженедельно | Новые фичи, изменения цен, финансирование, руководство |
| Сигналы по клиенту | Ежедневно (горячие аккаунты) | Финансирование, наймы, новости, вакансии |
| Здоровье сделки | Ежедневно | Активность чемпиона в LinkedIn, новости компании |
| Триггеры win/loss | Еженедельно | Закрытые сделки конкурентов, reference-проверки |

**Настройка рабочего процесса мониторинга:**
```
"Monitor [Competitor] for product releases and pricing changes.
Alert me every Monday morning with anything new."

"Watch [Prospect Company] for funding announcements and executive
changes. Alert me immediately when something happens."
```

---

### 8.7 Широкое параллельное исследование по множеству сущностей

**Что делает:** Запускает десятки веб-поисков одновременно по множеству компаний, людей или тем и синтезирует результаты.

**Почему это важно для продаж:**
- Исследовать 20 аккаунтов перед prospecting-блицем за минуты (не часы)
- Построить полный ландшафт территории — всех конкурентов, всех ключевых игроков
- Запустить исследование аккаунтов по каждому участнику перед крупной конференцией
- Оценить и ранжировать весь список входящих лидов по фирмографическому соответствию

**Примеры промтов параллельного исследования:**
```
"Research all 15 companies from my lead list and score them
by [ICP criteria]. Output a ranked table."

"Build a competitive landscape of all 8 vendors in [category].
Compare them on pricing, features, and recent releases."

"Research all attendees at [Conference] from [Target Industry]
and find the top 10 most relevant prospects for my product."
```

---

### 8.8 Сводка сравнения возможностей

| Возможность | Perplexity Computer | Claude Code (оффлайн) | Заметки |
|------------|--------------------|-----------------------|-------|
| Живой веб-поиск | ✅ В реальном времени | ❌ Граница знаний | Критично для триггерных событий |
| Поиск по соцсетям | ✅ X/Twitter live | ❌ | Разведка по конкурентам, боли клиента |
| Интеграция CRM | ✅ 400+ приложений | ❌ | Нативное подтягивание данных |
| Интеграция Email | ✅ Черновик + отправка | ❌ | Автоматизация аутрича |
| Интеграция календаря | ✅ Авто-подтягивание | ❌ | Автоматизация подготовки к встрече |
| Генерация изображений | ✅ AI-модели | ❌ | Создание материалов |
| Генерация видео | ✅ AI-модели | ❌ | Демо-клипы |
| Деплой сайтов | ✅ Netlify/Vercel | ❌ | Хостинг материалов |
| Запланированный мониторинг | ✅ Повторяющийся | ❌ | Алерты по конкурентам |
| Параллельное исследование | ✅ Много сущностей сразу | Ограничено | Исследование территории |
| Логика приоритизации RICE | ✅ | ✅ | Обе могут выполнять |
| Анализ интервью | ✅ | ✅ | Обе могут выполнять |
| Анализ бренд-войса | ✅ | ✅ | Обе могут выполнять |
| Картирование пути | ✅ | ✅ | Обе могут выполнять |
| Генерация батлкарт | ✅ | Ограничено | Perplexity добавляет живые данные |
| Создание материалов | ✅ | Ограничено | Perplexity добавляет живое исследование + деплой |

---

## Быстрая справка: индекс команд

| Что вы хотите | Что сказать | Раздел |
|--------------|-------------|---------|
| Исследовать компанию перед аутричем | "Research [Company]" | 2.1 |
| Исследовать конкретного человека | "Look up [Name] at [Company]" | 2.1 |
| Проанализировать клиентское интервью | "Analyze this transcript [paste/attach]" | 2.3 |
| Построить персону покупателя | "Build a persona for [segment]" | 2.4 |
| Картировать путь покупателя | "Map buyer journey for [persona/product]" | 2.5 |
| Полная подготовка к встрече | "Prep me for my call with [Company]" | 3.1 |
| Подготовить именно discovery-звонок | "Prep me for discovery call with [Company]" | 3.2 |
| Подготовить демо | "Prep me for my demo with [Company]" | 3.2 |
| Построить конкурентную батлкарту | "Build battlecard for [Competitor]" | 4.1 |
| Проанализировать бренд-войс конкурента | "Analyze [Competitor]'s brand voice" | 4.1 |
| Получить вопросы-мины | "Give me landmine questions for [Competitor]" | 4.5 |
| Составить холодное письмо-аутрич | "Draft outreach to [Person] at [Company]" | 5.1 |
| Написать LinkedIn-сообщение | "LinkedIn message to [Name] at [Company]" | 5.3 |
| Создать последовательность фоллоу-апов | "Create follow-up sequence for [Company]" | 5.4 |
| Валидировать бренд-войс письма | "Check brand voice of this email" | 5.6 |
| Построить лендинг | "Create landing page for [Company]" | 6.1 |
| Построить one-pager | "One-pager for [Company]" | 6.2 |
| Построить демо рабочего процесса | "Workflow demo for [Company]" | 6.2 |
| Получить дневной брифинг | "Morning briefing" / "Start my day" | 7.1 |
| Быстрый брифинг | "Quick brief" / "tldr my day" | 7.5 |
| Резюме конца дня | "Wrap up my day" | 7.6 |
| Приоритизировать пайплайн через RICE | "Prioritize my deals" | 7.3 |
| Оценить конкретную сделку | "Score this deal with RICE: [details]" | 7.3 |
| Проверить здоровье сделки | "What's the health of my [Company] deal?" | 7.7 |

---

## Справка по интеграциям

### CRM-системы
| CRM | Доступные ключевые данные | Использовать в |
|-----|-------------------|--------|
| Salesforce | Аккаунты, контакты, возможности, активности, кастомные поля | Все разделы |
| HubSpot | Контакты, сделки, таймлайн, письма, встречи | Все разделы |
| Pipedrive | Сделки, персоны, организации, активности | Разделы 3, 7 |
| Outreach/Salesloft | Последовательности, каденции, записи звонков | Разделы 5, 7 |

### Инструменты Enrichment
| Инструмент | Предоставляемые данные | Использовать в |
|------|--------------|--------|
| Apollo | Верифицированные email, телефоны, оргсхемы, техстек | Разделы 2, 5 |
| Clay | Мультиисточниковый enrichment, сигналы намерений, AI-обогащение | Разделы 2, 7 |
| ZoomInfo | Фирмографика, сигналы покупки, оргсхема | Разделы 2, 7 |

### Исследование и разведка
| Инструмент | Предоставляемые данные | Использовать в |
|------|--------------|--------|
| LinkedIn Sales Navigator | Профили, сигналы, смены работы | Разделы 2, 3, 5 |
| G2/Capterra | Отзывы о конкурентах, тональность пользователей | Раздел 4 |
| Gong/Chorus | Транскрипты звонков, разведка по сделкам | Разделы 3, 4 |

### Контент и коммуникация
| Инструмент | Назначение | Использовать в |
|------|---------|--------|
| Gmail/Outlook | Составление и отправка аутрича | Раздел 5 |
| Slack/Teams | Внутренняя разведка, обсуждения аккаунта | Разделы 3, 4 |
| Notion/Confluence | Батлкарты, плейбуки, кейсы | Разделы 4, 6 |

---

## Типичные ловушки, которых стоит избегать

| Ловушка | Описание | Профилактика |
|---------|-------------|------------|
| **Generic outreach** | Не исследовать перед отправкой | Всегда выполняйте Step 1 research перед составлением |
| **Feature dumping** | Вести с фич продукта, а не с боли клиента | Ведите с их проблемы, не с вашего решения |
| **Stale battlecards** | Использовать устаревшую конкурентную разведку в сделках | Обновляйте батлкарты ежемесячно или перед крупными сделками |
| **One-size personas** | Относиться ко всем покупателям одинаково | Отображайте на архетип (Раздел 2.4) для каждого ключевого контакта |
| **RICE paralysis** | Переусердствовать со скорингом вместо продаж | Скоринг занимает 5 минут; используйте его, чтобы выбрать топ-3 и двигаться |
| **Asset without context** | Строить дженерик-лендинг | Всегда завершайте сбор контекста Фазы 0 (Раздел 6.2) |
| **Post-call amnesia** | Не логировать инсайты после звонков | Выполняйте фреймворк после звонка в течение 2 часов (Раздел 3.5) |
| **Ignoring brand voice** | Отправлять письма, не соответствующие вашему войсу | Проверяйте по чек-листу бренд-войса (Раздел 5.6) |
| **Missing the champion** | Фокусироваться только на экономическом покупателе | Отображайте всех стейкхолдеров на персоны; стройте внутреннюю коалицию |
| **Skipping discovery** | Идти сразу к демо без квалификации | Всегда сначала завершайте банк вопросов discovery (Раздел 3.2) |

---

## Сводка лучших практик

**Исследование аккаунта:**
- Включайте домен ("research acme.com") для лучшей точности
- Уточняйте человека ("look up Jane Smith, VP Sales at Acme")
- Заявляйте свою цель ("research Stripe before my demo call")
- Запускайте анализ интервью по всем записям звонков (Раздел 2.3)

**Подготовка к звонку:**
- Больше контекста = лучше подготовка — вставляйте письма, заметки, что угодно
- Называйте всех участников с должностями; даже просто должности помогают
- Явно заявляйте цель встречи ("I want to get them to agree to a pilot")
- Помечайте известные опасения заранее ("They mentioned budget is tight")

**Конкурентная разведка:**
- Будьте честны о слабостях — авторитет требует признания, где конкуренты сильны
- Фокусируйтесь на результатах, не на фичах — "клиенты достигают результата Y" сильнее, чем "у них есть фича X"
- Закладывайте мины, не очерняйте — задавайте вопросы, естественно обнажающие слабости
- Обновляйтесь с полей — лучшая разведка приходит из разговоров с клиентами, не с сайтов

**Аутрич:**
- Никогда не отправляйте, пока не сделано исследование
- Только один CTA
- Только plain text в письмах (без markdown)
- Меньше 150 слов для холодного аутрича
- Следуйте структуре AIDA: сначала зацепка, затем проблема, потом доказательство, в конце просьба

**Создание материалов:**
- Используйте их язык, их метрики, их приоритеты
- Должно ощущаться подогнанным, не шаблонным — никаких дженерик-заглушек
- Всегда задавайте уточняющие вопросы перед сборкой
- Итерация Фазы 7 ожидаема — первый черновик не финальный

**Приоритизация сделок:**
- Оценивайте каждую сделку по RICE раз в неделю
- Фокусируйтесь на топ-3 по скору — игнорируйте остальное в этот день
- Обновляйте Confidence сразу после любой встречи или сигнала
- Используйте портфельный вид для баланса быстрых побед vs. больших ставок

---

*Sales Super-Skill v1.0 — Объединяет 6 встроенных скиллов продаж Perplexity Computer с Product Manager Toolkit от Claude Code (RICE + Customer Interview Analyzer), UX Researcher Designer и Content Creator (Brand Voice Analyzer + Content Research Writer).*
