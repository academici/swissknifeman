---
name: marketing-super-skill
bucket: marketing
version: 1.0.0
description: Comprehensive end-to-end marketing skill merging Perplexity Computer's 6 built-in marketing skills with Claude Code's best community marketing skills. Covers campaign planning, brand voice, competitive analysis, SEO, content creation, performance analytics, copywriting frameworks, and marketing ops. Use when planning campaigns, analyzing competitors, creating content, building brand guidelines, tracking marketing metrics, or optimizing conversion funnels.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

# Маркетинговый супер-скилл: объединение Claude Code + Computer

> **Назначение**: исчерпывающий маркетинговый справочник, объединяющий лучшие фреймворки, шаблоны и рабочие процессы из маркетинговых скиллов Claude Code и встроенных маркетинговых скиллов Perplexity Computer в единый унифицированный плейбук.
>
> **Последнее обновление**: 3 марта 2026

## Содержание

1. [Анализ пробелов (Gap Analysis)](#gap-analysis)
2. [Объединённый скилл: создание контента и SEO](#merged-skill-content-creation--seo)
3. [Объединённый скилл: планирование кампаний и генерация спроса](#merged-skill-campaign-planning--demand-gen)
4. [Объединённый скилл: аналитика и эффективность](#merged-skill-analytics--performance)
5. [Объединённый скилл: конкурентная разведка и PMM](#merged-skill-competitive-intelligence--pmm)
6. [Объединённый скилл: оптимизация в магазинах приложений (ASO)](#merged-skill-app-store-optimization-aso)
7. [Объединённый скилл: prompt-инжиниринг для маркетинга](#merged-skill-prompt-engineering-for-marketing)
8. [Уникальные возможности Computer, которых нет в Claude Code](#unique-computer-capabilities-not-in-claude-code)

---

## Анализ пробелов (Gap Analysis)

### Матрица сравнения возможностей

| Возможность | Claude Code | Computer | Примечания |
|---|:---:|:---:|---|
| **Создание контента** | | | |
| Шаблоны постов в блог (How-to, Listicle, Case Study, Thought Leadership) | ✅ | ✅ (обобщённо) | У Claude Code 4 детальных шаблона; у Computer единая обобщённая структура |
| Шаблоны видео-сценариев | ✅ | ❌ | Уникально для Claude Code — сценарий образовательного видео с таймкодами по секциям |
| Матрица переупаковки контента (content repurposing) | ✅ | ❌ | Уникально для Claude Code — превращает один пост в блоге в 10+ производных активов |
| Формулы написания подписей (AIDA, PAS, Before-After-Bridge) | ✅ | ❌ | Уникально для Claude Code |
| Формулы заголовков | ✅ (в SEO) | ✅ (7 формул) | У Computer больше самостоятельных формул |
| Шаблон SEO-брифа | ✅ | ❌ | Уникально для Claude Code |
| Шаблон контент-календаря | ✅ | ✅ | Есть у обоих; у Claude Code детальнее |
| **Планирование кампаний** | | | |
| Шаблон кампанийного брифа | ✅ | ✅ | Есть у обоих; разные структуры |
| Фреймворк распределения бюджета | ✅ | ✅ | Есть у обоих |
| Матрица канальной стратегии | ✅ | ✅ | Есть у обоих |
| Чек-лист запуска | ✅ | ❌ | Уникально для Claude Code |
| Журнал экспериментов/тестов | ✅ | ❌ | Уникально для Claude Code |
| Плейбук генерации спроса | ✅ | ❌ | Уникально для Claude Code |
| **Аналитика и эффективность** | | | |
| Шаблон KPI-дашборда | ✅ | ✅ | Есть у обоих |
| Моделирование атрибуции | ✅ | ✅ | У Computer больше деталей по моделям |
| Когортный анализ | ✅ | ❌ | Уникально для Claude Code |
| UTM-таксономия | ✅ | ❌ | Уникально для Claude Code |
| Marketing mix modeling | ❌ | ✅ | Уникально для Computer |
| Тестирование инкрементальности | ❌ | ✅ | Уникально для Computer |
| **Конкурентная разведка** | | | |
| Шаблон конкурентной battlecard | ✅ | ✅ | Похожая структура |
| Анализ выигрышей/проигрышей (Win/loss) | ✅ | ❌ | Уникально для Claude Code |
| Отслеживание доли голоса (Share of voice) | ✅ | ❌ | Уникально для Claude Code |
| Матрица сравнения функций | ✅ | ✅ | Есть у обоих |
| Карта позиционирования | ❌ | ✅ | Уникально для Computer |
| **Оптимизация в магазинах приложений** | | | |
| Полный ASO-фреймворк | ❌ | ✅ | Уникально для Computer — полный ASO-плейбук |
| Исследование ключевых слов для ASO | ❌ | ✅ | Уникально для Computer |
| A/B-тестирование для магазина приложений | ❌ | ✅ | Уникально для Computer |
| **Голос бренда** | | | |
| Аудит голоса бренда | ✅ | ✅ | Есть у обоих |
| Шаблон style guide | ✅ | ✅ | Есть у обоих |
| Спектр тональности (tone spectrum) | ✅ | ❌ | Уникально для Claude Code |
| Управление терминологией (terminology governance) | ✅ | ❌ | Уникально для Claude Code |
| **PR и коммуникации** | | | |
| Шаблон пресс-релиза | ✅ | ❌ | Уникально для Claude Code |
| Шаблон медиа-питча | ✅ | ❌ | Уникально для Claude Code |
| Плейбук кризисных коммуникаций | ✅ | ❌ | Уникально для Claude Code |
| **Prompt-инжиниринг** | | | |
| Библиотека промтов для маркетинга | ❌ | ✅ | Уникально для Computer — полный фреймворк prompt-инжиниринга |
| Role prompting | ❌ | ✅ | Уникально для Computer |
| Chain-of-thought промты | ❌ | ✅ | Уникально для Computer |

### Сводка пробелов

**Есть у Claude Code, но отсутствует у Computer:**
- Шаблон видео-сценария
- Матрица переупаковки контента
- Формулы написания подписей
- Шаблон SEO-брифа
- Чек-лист запуска
- Журнал экспериментов/тестов
- Плейбук генерации спроса
- Фреймворк когортного анализа
- UTM-таксономия
- Шаблон анализа выигрышей/проигрышей
- Отслеживание доли голоса
- Шаблоны пресс-релиза + медиа-питча
- Плейбук кризисных коммуникаций
- Спектр тональности + управление терминологией

**Есть у Computer, но отсутствует у Claude Code:**
- Marketing mix modeling
- Тестирование инкрементальности
- Полный ASO-фреймворк
- Карта позиционирования
- Библиотека prompt-инжиниринга для маркетинга

---

## Объединённый скилл: создание контента и SEO

### Философия
Хороший контент одновременно служит трём хозяевам: **читателю** (ценность, ясность, вовлечённость), **алгоритму** (находимость, структура, сигналы) и **бренду** (голос, позиционирование, доверие). Каждый материал должен быть оптимизирован под всех троих.

---

### Шаблоны постов в блог

#### Шаблон 1: How-To / обучающий пост

```
Title: How to [Achieve Specific Outcome] in [Timeframe/Steps]

Meta Description (150-160 chars): Learn how to [outcome] with this step-by-step guide. [Key benefit 1] and [key benefit 2]. [CTA].

INTRO (150-200 words)
- Open with the problem/pain point
- Acknowledge why it's hard
- Promise: "In this guide, you'll learn..."
- Quick credential/trust signal

WHAT YOU'LL NEED (optional)
- Prerequisites list
- Tools/resources needed

STEP 1: [Action Verb + Outcome]
[200-300 words per step]
- What to do
- Why it matters
- Common mistake to avoid
- Screenshot/visual cue

[Repeat for Steps 2-N]

PRO TIPS SECTION
- 3-5 advanced tips
- Link to related content

CONCLUSION
- Recap the steps
- Reinforce the outcome they'll achieve
- CTA: [Next step, related guide, or product]

FAQ SECTION (for SEO)
Q: [Common question]
A: [Concise answer — 50-100 words]
[3-5 FAQs]
```

#### Шаблон 2: пост-листикл (Listicle)

```
Title: [Number] [Adjective] [Things] That [Benefit/Outcome]
Example: "17 Proven Email Subject Lines That Boost Open Rates"

INTRO (100-150 words)
- State the problem the list solves
- Why this list is different/better
- Quick navigation note if list is long

EACH LIST ITEM:
## [Number]. [Item Name]: [Optional Benefit Tagline]
[100-200 words]
- What it is
- Why it's on the list
- How to use it
- Example or data point

BONUS SECTION (optional)
- "Honorable mentions" for longer lists
- "What didn't make the cut and why"

CONCLUSION
- Which items to start with
- How to prioritize
- CTA
```

#### Шаблон 3: пост-кейс (Case Study)

```
Title: How [Company/Person] [Achieved Specific Result] in [Timeframe]

EXECUTIVE SUMMARY (100 words)
- Client/subject
- Challenge
- Solution
- Result (lead with the number)

THE CHALLENGE
- Background on the company/situation
- Specific pain points
- What they had tried before
- Stakes: what happened if they didn't solve it

THE SOLUTION
- What was implemented
- Why this approach
- Timeline of implementation
- Key decisions made

THE RESULTS
- Primary metric with % change
- Secondary metrics
- Qualitative feedback/quote
- Before/after comparison table

KEY TAKEAWAYS
- 3-5 lessons applicable to reader
- What made this work
- How reader can apply it

NEXT STEPS / CTA
```

#### Шаблон 4: лидерский / мнениевый пост (Thought Leadership / Opinion)

```
Title: [Contrarian Take] / [Prediction] / [Framework Name]
Examples: 
- "Why [Common Practice] Is Actually Hurting Your [Metric]"
- "The [New Framework] That Will Replace [Old Approach] by [Year]"

HOOK (50-100 words)
- Contrarian statement or bold prediction
- Who this challenges
- Why you're qualified to say it

THE CONVENTIONAL WISDOM
- Steel-man the position you're challenging
- Acknowledge what's right about it

WHY IT'S WRONG (OR INCOMPLETE)
- Your core argument
- Evidence/data
- Examples

THE BETTER FRAMEWORK
- Your alternative
- How it works
- Why it's superior

REBUTTALS
- Anticipate objections
- Address them honestly

CONCLUSION
- Restate the bold claim
- Call to action: challenge them to try your approach
```

---

### Шаблон видео-сценария

```
VIDEO: [Title]
Target length: [X minutes]
Platform: [YouTube / LinkedIn / TikTok / Webinar]
Goal: [Awareness / Education / Conversion]

[0:00-0:30] HOOK
- Open with problem, shocking stat, or bold claim
- "In this video, you'll learn..."
- Do NOT start with "Hey guys" or company intro

[0:30-1:00] CREDIBILITY + CONTEXT
- Why you / why now
- Brief framework preview

[1:00-X:XX] MAIN CONTENT
Section 1: [Topic] (~X minutes)
- Key point 1
- Key point 2
- Example or demo

Section 2: [Topic] (~X minutes)
[repeat structure]

[X:XX - X:XX] RECAP
- 3-bullet summary
- "The one thing to remember is..."

[Final 30 sec] CTA
- Specific next action
- Subscribe / like if applicable
- Link in description

B-ROLL NOTES: [List visual cues for editor]
LOWER THIRDS: [Text overlays to add]
MUSIC MOOD: [Upbeat / Serious / Inspirational]
```

---

### Матрица переупаковки контента (Content Repurposing)

Превратите **один длинный пост в блоге** в 10+ активов:

| Исходный актив | Производный актив | Платформа | Примечания |
|---|---|---|---|
| Пост в блоге (2 000+ слов) | Тред в Twitter/X | Twitter/X | Выньте 5-7 ключевых инсайтов; каждый = один твит |
| Пост в блоге | Карусель в LinkedIn | LinkedIn | 8-10 слайдов; визуальная сводка |
| Пост в блоге | Сценарий короткого видео | TikTok/Reels | 60-90 сек; выберите самый неожиданный инсайт |
| Пост в блоге | Email-рассылка | Email | Вступление + 3 ключевых пункта + CTA на полный пост |
| Пост в блоге | Инфографика | Pinterest/Blog | Визуализируйте фреймворк или процесс |
| Пост в блоге | Тезисы для подкаста | Podcast | Используйте заголовки H2 как темы сегментов |
| Пост в блоге | SlideShare/презентация | SlideShare | Преобразуйте заголовки в слайды |
| Пост в блоге | Графика с цитатами | Instagram | Вытащите 3-5 цитируемых строк |
| Пост в блоге | Обновление FAQ-страницы | Website | Извлеките секции «вопрос-ответ» |
| Пост в блоге | Лид-магнит/чек-лист | Landing page | Сожмите практические шаги в PDF |
| Пост в блоге | Фрагмент кейса | Sales deck | Если содержит данные о результатах |
| Пост в блоге | Варианты рекламного текста | Paid social | Используйте комбинации «заголовок + ключевая цифра» |

---

### Формулы написания подписей (Caption Writing)

#### AIDA (Attention → Interest → Desire → Action / Внимание → Интерес → Желание → Действие)
```
[ATTENTION] Shocking stat, bold claim, or question
[INTEREST] Why this matters to them specifically
[DESIRE] Paint the picture of the outcome
[ACTION] Clear, single CTA

Example:
"83% of B2B buyers make purchase decisions before talking to sales. 👀
That means your content is your first sales rep.
Imagine your blog doing the heavy lifting 24/7.
Download our content strategy template → [link]"
```

#### PAS (Problem → Agitate → Solve / Проблема → Усиление → Решение)
```
[PROBLEM] Name the pain
[AGITATE] Make it feel worse / more urgent
[SOLVE] Position your solution

Example:
"Posting every day but still getting zero traction?
It's not the frequency — it's the lack of a hook strategy.
Here's the 5-hook formula top creators use: [thread]"
```

#### Before-After-Bridge (До-После-Мост)
```
[BEFORE] Current frustrating situation
[AFTER] Ideal end state
[BRIDGE] How to get there (your content/product)

Example:
"Before: Manually compiling weekly reports for 3 hours every Friday.
After: Auto-generated reports land in your inbox every Monday at 8am.
Bridge: Our new reporting integration — live today."
```

---

### Формулы заголовков (объединённо: Claude Code + Computer)

**Из библиотеки Computer:**
1. How to [Do X] Without [Pain/Cost]
2. [Number] Ways to [Achieve Outcome] in [Timeframe]
3. The [Adjective] Guide to [Topic]
4. Why [Common Belief] Is Wrong (And What to Do Instead)
5. [Number] [Things] Every [Audience] Should Know About [Topic]
6. What [Respected Authority] Can Teach Us About [Topic]
7. The [Surprising/Counterintuitive] Truth About [Topic]

**Из SEO-фреймворка Claude Code:**
8. [Year]'s Best [Topic]: A Complete Guide
9. [Topic] for Beginners: Everything You Need to Know
10. [Topic] vs. [Topic]: Which Is Right for You?
11. How I [Achieved Result] in [Timeframe] (With Proof)
12. Stop [Doing Wrong Thing] — Do This Instead
13. The Only [Topic] Guide You'll Ever Need
14. [Number] Mistakes [Audience] Make with [Topic] (And How to Fix Them)

---

### Шаблон SEO-брифа

```
CONTENT BRIEF

Target Keyword: [primary keyword]
Search Volume: [monthly]
Keyword Difficulty: [0-100]
Search Intent: [Informational / Navigational / Transactional / Commercial]
Target SERP Feature: [Featured snippet / People Also Ask / Image pack]

SECONDARY KEYWORDS:
- [kw 2]: [volume]
- [kw 3]: [volume]
- [kw 4]: [volume]

SEMANTIC TERMS TO INCLUDE: (LSI keywords)
[list 8-10]

COMPETITOR ANALYSIS:
| URL | DA | Word Count | Key Angle | Missing |
|---|---|---|---|---|
| [top result 1] | | | | |
| [top result 2] | | | | |
| [top result 3] | | | | |

CONTENT ANGLE: [What makes our piece 10x better?]
TARGET WORD COUNT: [X words]
CONTENT FORMAT: [Blog / Landing page / Pillar page / FAQ]

OUTLINE:
H1: [Title with primary keyword]
H2: [Section 1]
  H3: [Subsection]
H2: [Section 2]
[etc.]

INTERNAL LINKS TO INCLUDE:
- [URL + anchor text]

EXTERNAL AUTHORITY LINKS TO INCLUDE:
- [Source + why]

CTA GOAL: [What action should reader take?]
META TITLE (60 chars): 
META DESC (155 chars):
```

---

### Шаблон контент-календаря

```
MONTH: [Month Year]
Theme/Campaign: [Monthly focus]
Key Dates: [Holidays, product launches, events]

WEEKLY CADENCE:
Monday: [Content type + topic]
Tuesday: [Content type + topic]
Wednesday: [Content type + topic]
Thursday: [Content type + topic]
Friday: [Content type + topic]

CONTENT TRACKER:
| Date | Platform | Format | Topic/Title | Keyword | Status | Owner | Published URL |
|---|---|---|---|---|---|---|---|
| [date] | [platform] | [format] | [title] | [kw] | Draft/Review/Live | [name] | [url] |

MONTHLY METRICS TARGETS:
- Organic traffic: [X]
- New backlinks: [X]
- Email signups from content: [X]
- Social shares: [X]
```

---

## Объединённый скилл: планирование кампаний и генерация спроса

### Шаблон кампанийного брифа

```
CAMPAIGN BRIEF

Campaign Name: 
Fiscal Quarter: 
Campaign Owner: 
Approval Required From: 

─── STRATEGIC CONTEXT ───
Business Objective: [What company goal does this serve?]
Marketing Objective: [Awareness / Consideration / Conversion / Retention]
Target Audience:
  Primary: [Segment + persona]
  Secondary: [Segment + persona]
Geography: 
Language(s):

─── CAMPAIGN STRATEGY ───
Core Message: [1 sentence]
Value Proposition: [What's the offer/hook?]
Key Differentiator: [Why us vs. alternatives?]
Proof Points: [3 data points or testimonials]

Creative Concept:
[Describe the big idea in 2-3 sentences]

Tone & Voice: [Refer to brand guidelines section]

─── CHANNELS & BUDGET ───
| Channel | Tactic | Budget | % of Total | Owner |
|---|---|---|---|---|
| Paid Search | [e.g., Google Ads branded] | $X | X% | [name] |
| Paid Social | [e.g., LinkedIn Lead Gen] | $X | X% | [name] |
| Email | [e.g., nurture sequence] | $X | X% | [name] |
| Content | [e.g., blog + SEO] | $X | X% | [name] |
| Events | [e.g., webinar] | $X | X% | [name] |
| **Total** | | **$X** | **100%** | |

─── TIMELINE ───
| Phase | Dates | Milestones |
|---|---|---|
| Planning | [dates] | Brief approved, creative brief sent |
| Production | [dates] | Copy, creative, landing page |
| QA | [dates] | All assets reviewed and approved |
| Launch | [date] | Go live |
| Optimization | [dates] | Weekly reviews |
| Reporting | [date] | Final report delivered |

─── SUCCESS METRICS ───
| Metric | Baseline | Target | Stretch |
|---|---|---|---|
| [Primary KPI] | [current] | [goal] | [aspirational] |
| [Secondary KPI 1] | | | |
| [Secondary KPI 2] | | | |

─── ASSETS NEEDED ───
[ ] Landing page
[ ] Ad creative (list specs)
[ ] Email copy (list # of sends)
[ ] Blog post(s)
[ ] Social posts
[ ] Sales enablement materials
[ ] Webinar/event assets

─── DEPENDENCIES & RISKS ───
Dependencies: [List what needs to happen first]
Risks: [What could go wrong + mitigation]
```

---

### Плейбук генерации спроса (Demand Gen)

#### Этап 1: осведомлённость (верх воронки, Top of Funnel)

**Цель:** оказаться перед нужными людьми, которые вас ещё не знают.

| Тактика | Описание | Канал | KPI |
|---|---|---|---|
| SEO-контент | Образовательные посты в блоге под небрендовые ключевые слова | Organic | Показы, клики |
| Лидерство мнений | Колонки, посты в LinkedIn, появления в подкастах | Social/PR | Охват, доля голоса |
| Проспектинг в paid social | Lookalike- и интерес-ориентированные аудитории | LinkedIn/Meta | CPM, CTR, охват |
| Display/programmatic | Без ретаргетинга; чистый проспектинг | Google Display | Показы, VCR |
| Ко-маркетинг | Партнёрские вебинары, совместный контент | Partner channels | Охват новой аудитории |
| Сообщество | Участие в Slack-группах, форумах, Reddit | Community | Упоминания, обратные ссылки |

#### Этап 2: рассмотрение (середина воронки, Middle of Funnel)

**Цель:** превратить осведомлённых потенциальных клиентов в вовлечённые лиды.

| Тактика | Описание | Канал | KPI |
|---|---|---|---|
| Лид-магниты | Электронные книги, шаблоны, калькуляторы, чек-листы | Content/Email | Загрузки, MQL |
| Вебинары | Живые демо, экспертные панели, how-to сессии | Zoom/LinkedIn | Регистрации, участники |
| Nurture-последовательности | Email-цепочки по интересу/поведению в контенте | Email | Open rate, CTR, доля MQL |
| Ретаргетинг | Показ объявлений с социальным доказательством посетителям сайта | Paid social | ROAS, CPC |
| Бесплатные инструменты | Инструменты аудита, оценщики, ROI-калькуляторы | Website | Использование инструмента, сбор email |
| Кейсы | Социальное доказательство для конкретных вертикалей/сценариев | Website/Sales | Время на странице, загрузки |

#### Этап 3: решение (низ воронки, Bottom of Funnel)

**Цель:** превратить вовлечённые лиды в пайплайн и клиентов.

| Тактика | Описание | Канал | KPI |
|---|---|---|---|
| Запросы демо | Оптимизация потока запроса демо | Website | Конверсия в демо |
| Бесплатный пробный период | Снизить трение для входа в продукт | Product | Старты триала, активация |
| Сравнительные страницы | SEO под «[brand] vs [competitor]» | SEO | Органический трафик, конверсия |
| Отзывы/рейтинги | Бейджи G2, Capterra, Trustpilot | Website | Объём отзывов, рейтинг |
| Аутрич SDR | Передача MQL → SQL + аутрич | Sales | Доля SQL, встречи |
| Конкурентное вытеснение | Таргетированные кампании на клиентов конкурентов | ABM | Повлиявший пайплайн |

#### Модель скоринга лидов

```
DEMOGRAPHIC SCORE (max 50 points)
+ 20: Target industry match
+ 15: Target company size match  
+ 10: Target job title/function match
+ 5: Target geography match

BEHAVIORAL SCORE (max 50 points)
+ 20: Pricing page view
+ 15: Demo request (even if abandoned)
+ 10: Case study download
+ 8: Webinar attendance
+ 5: Blog/content visit (per session)
+ 3: Email open (per email)
+ 2: Email click (per click)
- 10: Unsubscribed from email
- 20: Competitor domain email

MQL THRESHOLD: 60+ points
SAL THRESHOLD: SDR reviews and accepts MQL
SQL THRESHOLD: Discovery call completed, qualified by BANT
```

---

### Чек-лист запуска

**ДО ЗАПУСКА (T-4 недели)**
- [ ] Кампанийный бриф утверждён всеми стейкхолдерами
- [ ] Лендинг создан и прошёл QA
- [ ] Настроены UTM-параметры (см. секцию UTM-таксономии)
- [ ] Трекинг-пиксели/теги проверены в GTM
- [ ] Кампания в CRM создана и связана
- [ ] Email-последовательности загружены и протестированы
- [ ] Рекламные креативы разработаны и утверждены
- [ ] Юридическая/комплаенс-проверка завершена
- [ ] Бюджет утверждён и заказы (PO) оформлены

**ДО ЗАПУСКА (T-1 неделя)**
- [ ] Все рекламные аккаунты пополнены
- [ ] Варианты A/B-теста финализированы
- [ ] Команда SDR проинструктирована по кампании
- [ ] Материалы sales enablement распространены
- [ ] Подготовлен черновик внутреннего анонса
- [ ] Органические посты в соцсетях запланированы

**ДЕНЬ ЗАПУСКА**
- [ ] Кампании активированы (платные)
- [ ] Email-рассылка №1 отправлена
- [ ] Посты в соцсетях опубликованы
- [ ] Пост в блоге опубликован
- [ ] PR выпущен (если применимо)
- [ ] Анонс отправлен в командный Slack
- [ ] Запущен мониторинг в реальном времени (проверка каждые 2 часа)

**ПОСЛЕ ЗАПУСКА (неделя 1)**
- [ ] Проверка на день 3: темп, CTR, CPL относительно цели
- [ ] Обновлён список минус-слов (paid search)
- [ ] Слабые варианты объявлений приостановлены
- [ ] Проверена скорость follow-up у SDR
- [ ] Просмотрена тепловая карта лендинга

**ПОСЛЕ ЗАПУСКА (постоянно)**
- [ ] Еженедельный отчёт об эффективности отправлен
- [ ] Раз в две недели — обновление креативов при падении CTR
- [ ] Ежемесячное перераспределение бюджета по эффективности
- [ ] Итоговый отчёт по кампании при завершении

---

### Шаблон журнала экспериментов

```
EXPERIMENT LOG

Experiment ID: EXP-[YYYY-MM-DD]-[###]
Hypothesis: "By changing [X], we expect [Y] to improve by [Z]% because [reason]"
Type: A/B test / Multivariate / Sequential
Channel: 
Owner: 
Start Date: 
End Date: 
Sample Size Needed: [Use power calculator: n = ?]
Significance Level: 95%

CONTROL:
- Description: 
- Current baseline: [metric = X]

VARIANT(S):
- Variant A: [what changed]
- Variant B: [if multivariate]

RESULTS:
| Variant | Impressions | Clicks | Conv. | Conv. Rate | Stat Sig? |
|---|---|---|---|---|---|
| Control | | | | | — |
| Variant A | | | | | [Y/N] |

CONCLUSION:
[ ] Winner: [Control / Variant A / Variant B]
[ ] Inconclusive — extend test or increase sample
[ ] Loser — revert and document learnings

LEARNING:
[What did we learn that applies beyond this test?]

NEXT EXPERIMENT:
[What to test next based on these results]
```

---

### Фреймворк распределения бюджета

#### По этапам воронки (бенчмарк B2B SaaS)

| Этап | % бюджета | Обоснование |
|---|---|---|
| Осведомлённость (ToFu) | 25-35% | Строит пайплайн на 6-12 месяцев вперёд |
| Рассмотрение (MoFu) | 30-40% | Дозревание существующего спроса; зона наивысшего ROI |
| Решение (BoFu) | 25-35% | Закрытие выручки; наиболее измеримо |
| Бренд/Always-on | 5-10% | Накопительный эффект; трудно атрибутировать |

#### По каналам (B2B стадии роста)

| Канал | Типичный диапазон | Примечания |
|---|---|---|
| Paid Search | 20-30% | Захват существующего спроса; наивысший intent |
| Paid Social | 15-25% | LinkedIn для B2B; Meta для PLG |
| Content/SEO | 10-20% | Долгосрочный накопительный эффект; снижение CPA со временем |
| Email/Lifecycle | 5-10% | Канал с наивысшим ROI; низкая стоимость |
| Events/Webinars | 10-20% | Высококачественные лиды; ускорение пайплайна |
| ABM | 10-20% | Фокус на enterprise; сделки с высоким ACV |
| PR/Comms | 5-10% | Доверие к бренду; earned media |

---

## Объединённый скилл: аналитика и эффективность

### Шаблон KPI-дашборда

```
MARKETING PERFORMANCE DASHBOARD
Reporting Period: [Week/Month/Quarter] ending [date]
Prepared by: [Name]
Distribution: [List]

━━━ EXECUTIVE SUMMARY ━━━
One-sentence summary of performance: [Green/Yellow/Red + key driver]

━━━ PIPELINE & REVENUE ━━━
| Metric | This Period | Prior Period | YoY | Target | Status |
|---|---|---|---|---|---|
| Marketing-Sourced Pipeline | $X | $X | X% | $X | 🟢/🟡/🔴 |
| Marketing-Influenced Pipeline | $X | $X | X% | $X | |
| Marketing-Sourced Revenue | $X | $X | X% | $X | |
| Pipeline Coverage Ratio | Xx | Xx | | Xx | |

━━━ DEMAND GENERATION ━━━
| Metric | This Period | Prior Period | Target |
|---|---|---|---|
| Total MQLs | | | |
| MQL → SQL Rate | | | |
| Total SQLs | | | |
| SQL → Opp Rate | | | |
| Total Opportunities | | | |
| CPL (Cost per Lead) | | | |
| CPMQL (Cost per MQL) | | | |

━━━ CHANNEL PERFORMANCE ━━━
| Channel | Spend | Leads | CPL | MQLs | CPMQL | Pipeline | ROI |
|---|---|---|---|---|---|---|---|
| Paid Search | | | | | | | |
| Paid Social | | | | | | | |
| Email | | | | | | | |
| Organic/SEO | | | | | | | |
| Events | | | | | | | |
| Total | | | | | | | |

━━━ CONTENT PERFORMANCE ━━━
| Metric | This Period | Target |
|---|---|---|
| Organic Sessions | | |
| New Organic Keywords Ranking | | |
| Top 3 Posts by Traffic | [list] | |
| New Backlinks | | |

━━━ EMAIL ━━━
| Metric | This Period | Benchmark |
|---|---|---|
| List Size | | |
| Deliverability Rate | | >98% |
| Open Rate | | >25% |
| CTR | | >3% |
| Unsubscribe Rate | | <0.2% |

━━━ INSIGHTS & ACTIONS ━━━
🟢 What's working:
- [Insight 1 + data]

🔴 What needs attention:
- [Issue 1 + data + proposed action]

📋 Next period priorities:
1. [Action]
2. [Action]
```

---

### Гид по моделированию атрибуции

#### Сравнение моделей

| Модель | Как работает | Лучше всего для | Ограничение |
|---|---|---|---|
| **First Touch** | 100% кредита первому каналу | Анализ узнаваемости бренда | Игнорирует всё, что закрыло сделку |
| **Last Touch** | 100% кредита последнему каналу | Direct response / низ воронки | Игнорирует осведомлённость и дозревание |
| **Linear** | Равный кредит всем касаниям | Полноворонковый взгляд | Считает все касания равными |
| **Time Decay** | Больше кредита ближе к конверсии | Короткие циклы продаж | Недооценивает осведомлённость |
| **Position-Based (U-shaped)** | 40% первому, 40% последнему, 20% середине | Большинство B2B-сценариев | Произвольные веса |
| **W-Shaped** | 30% первому, 30% MQL, 30% opp, 10% остальным | Enterprise B2B | Сложна во внедрении |
| **Data-Driven** | ML распределяет кредит по реальным паттернам | Масштаб (нужно 1000+ конв.) | Чёрный ящик; нужно много данных |
| **Marketing Mix Modeling** | Статистическая модель по всем каналам | Полная воронка; офлайн + онлайн | Медленно; дорого; квартальная периодичность |

#### Рекомендуемая настройка

```
FOR WEEKLY REPORTING: Last-touch (simplest; sales team alignment)
FOR CAMPAIGN PLANNING: Position-based (U-shaped)
FOR BUDGET DECISIONS: Marketing Mix Modeling (quarterly)
FOR BOARD REPORTS: Multi-touch with custom weights

TOOL STACK:
- HubSpot / Salesforce: Last-touch and linear built-in
- Rockerbox / Northbeam / Triple Whale: Multi-touch + MMM
- Google Analytics 4: Data-driven (requires 1000+ conversions/month)
```

---

### UTM-таксономия

#### Стандартные UTM-параметры

```
FORMAT:
[website]?utm_source=[source]&utm_medium=[medium]&utm_campaign=[campaign]&utm_content=[content]&utm_term=[term]

NAMING CONVENTIONS (always lowercase, hyphens not underscores)

utm_source: Where the traffic comes from
  - google, linkedin, facebook, instagram, twitter-x, newsletter,
    partner-[name], direct, salesforce, hubspot

utm_medium: The marketing channel
  - cpc (paid search), paidsocial, email, organic, referral, 
    affiliate, display, video, sms, podcast, print

utm_campaign: Campaign name [quarter]-[campaign-name]
  Format: q1-2024-brand-awareness, q2-2024-product-launch-v2
  
utm_content: Ad variant or content piece
  - carousel-ad-a, text-ad-b, hero-image-1, cta-learnmore
  - blog-post-slug, email-header-cta

utm_term: Paid keyword (paid search only)
  - [keyword] — auto-populated with {keyword} ValueTrack
```

#### Правила управления UTM

1. **Никогда не используйте UTM на внутренних ссылках** — это ломает атрибуцию сессий
2. **Всегда в нижнем регистре** — UTM чувствительны к регистру в GA4
3. **Используйте URL builder** — предотвращает опечатки (от Google или свой собственный)
4. **Документируйте каждый UTM** в центральной таблице до запуска
5. **Тестируйте все UTM** до выхода кампании в продакшен
6. **Ежеквартальный аудит** — найдите осиротевшие UTM и битые ссылки

---

### Фреймворк когортного анализа

```
COHORT ANALYSIS: [Metric] by [Cohort Type]
Period: [Month/Quarter]
Cohort Definition: Users who [action] in [time period]

RETENTION TABLE (example: monthly email cohorts)
         Month 0  Month 1  Month 2  Month 3  Month 6  Month 12
Jan 2024:  100%     68%      54%      47%      38%      31%
Feb 2024:  100%     71%      57%      51%      41%      —
Mar 2024:  100%     69%      55%      —        —        —

KEY METRICS:
- Month 1 Retention: [X%] (target: >60%)
- 3-Month Retention: [X%] (target: >40%)
- 12-Month Retention: [X%] (target: >25%)

SEGMENT COMPARISONS:
| Cohort Segment | M1 Retention | M3 Retention | Observation |
|---|---|---|---|
| Organic search | | | |
| Paid social | | | |
| Email | | | |
| Direct | | | |

ACTIONS:
- Highest retention source: [X] → scale investment
- Lowest retention source: [X] → investigate + improve or cut
```

---

### Marketing Mix Modeling (MMM)

*Из аналитического скилла Computer — измерение enterprise-уровня*

#### Когда использовать MMM
- У вас есть 2+ года данных о еженедельных маркетинговых расходах
- Вы ведёте кампании в офлайн- и онлайн-каналах
- Нужно измерить каналы, которые нельзя отследить (ТВ, наружка/OOH, радио)
- Вы сталкиваетесь с потерей сигнала атрибуции (iOS 14.5+, отмена cookie)
- Вы хотите понять истинную инкрементальность, а не корреляцию

#### Фреймворк MMM

```
INPUTS REQUIRED:
- Weekly spend by channel (2+ years)
- Weekly revenue/conversions
- External factors: seasonality, holidays, competitor spend (if available)
- Price/promotion data

KEY OUTPUTS:
- ROI by channel
- Saturation curves (at what spend level does a channel plateau?)
- Optimal budget allocation
- Baseline vs. incremental revenue
- Halo effects (e.g., does TV lift search?)

FRAMEWORK STEPS:
1. Data Collection & Cleaning (2-3 weeks)
   - Standardize all spend data to weekly grain
   - Align revenue data to same grain
   - Identify anomalies (COVID, supply issues)

2. Exploratory Analysis (1 week)
   - Correlation matrix: spend vs. revenue by channel
   - Lag analysis: how many weeks delay per channel?
   - Seasonality decomposition

3. Model Build (2-4 weeks)
   - Multiplicative or additive model?
   - Adstock transformation for carry-over effects
   - Diminishing returns curves per channel

4. Validation (1-2 weeks)
   - Back-test: does model predict holdout periods?
   - MAPE target: < 10%

5. Scenario Planning
   - "What if" budget shifts
   - Saturation curve analysis
   - Optimal budget frontier

TOOLS:
- Open source: Meta Robyn (R), Google LightweightMMM (Python)
- Commercial: Analytic Partners, Nielsen, Neustar, Ekimetrics
```

---

### Тестирование инкрементальности

*Из аналитического скилла Computer*

#### Гео-ориентированный holdout-тест

```
OBJECTIVE: Measure true incremental lift from [channel/campaign]

SETUP:
1. Select test and control markets (matched on: size, demographics, baseline conversion rate)
2. Run campaign in TEST markets only
3. Dark (turn off) campaign in CONTROL markets
4. Duration: minimum 4 weeks; ideally 8 weeks

METRICS:
- Conversion rate: Test markets vs. Control markets
- Incremental lift % = (Test CvR - Control CvR) / Control CvR
- Incremental revenue = Total revenue × incremental lift %
- True ROAS = Incremental revenue / Media spend

COMMON PITFALLS:
- Markets that are too different baseline → use matching algorithm
- Too short → not enough time to see signal
- Spillover → test and control markets too geographically close
- Event contamination → news, weather, competitor promos during test
```

---

## Объединённый скилл: конкурентная разведка и PMM

### Шаблон конкурентной battlecard

```
BATTLECARD: [Competitor Name]
Last Updated: [Date]
Owner: [PMM Name]

─── QUICK SUMMARY ───
Positioning: [Their 1-sentence value prop]
Target Segment: [Who they go after]
Price Point: [Relative to us: premium/parity/discount]
Strengths: [Top 3]
Weaknesses: [Top 3]
Our Win Rate vs. Them: [X%]

─── THEIR MESSAGING ───
Tagline: 
Hero Message:
Key Claims:
1. 
2. 
3. 

─── FEATURE COMPARISON ───
| Feature | Us | [Competitor] | Notes |
|---|---|---|---|
| [Feature 1] | ✅ Best-in-class | ✅ Adequate | We win on [specific differentiator] |
| [Feature 2] | ✅ | ❌ | Major gap for them |
| [Feature 3] | ⚠️ Roadmap | ✅ Strong | Acknowledge; bridge to roadmap |
| [Feature 4] | ❌ | ✅ | Reframe: "[Feature 4] matters less than [our strength] because..." |

─── HOW TO WIN ───
Lead with: [Our strongest differentiator vs. this competitor]
Discovery question: "[Question that surfaces their weakness]"
Proof point: [Customer who switched from them + result]

OBJECTION HANDLING:
Objection: "[Competitor] has [feature we lack]"
Response: "[Acknowledge + reframe + redirect to our strength]"

Objection: "[Competitor] is cheaper"
Response: "[TCO argument + value proof point]"

─── TRAP-SETTING QUESTIONS ───
Questions to ask in discovery that favor us:
1. "How important is [our differentiator] to your team?"
2. "What's your current process for [thing we do better]?"
3. "Have you calculated the cost of [problem we solve better]?"

─── INTEL SOURCES ───
- G2/Capterra reviews: [link]
- LinkedIn: [link]
- Pricing page: [link]
- Job postings (signals): [observation]
- Recent news: [summary]
```

---

### Шаблон анализа выигрышей/проигрышей (Win/Loss)

```
WIN/LOSS ANALYSIS
Quarter: [Q]
Total Deals Analyzed: [N]
Overall Win Rate: [X%]
Data Source: [CRM export + customer interviews]

─── WIN REASONS ───
| Reason | Frequency | % of Wins | Rep Quote |
|---|---|---|---|
| Superior [feature] | X | X% | "Customers cited..." |
| Better support/onboarding | X | X% | |
| Price/value ratio | X | X% | |
| Brand/trust | X | X% | |
| Champion advocacy | X | X% | |

─── LOSS REASONS ───
| Reason | Frequency | % of Losses | Action |
|---|---|---|---|
| Lost to [Competitor A] | X | X% | Update battlecard; escalate feature gap |
| No decision / status quo | X | X% | Improve business case materials |
| Price too high | X | X% | Review packaging; improve ROI story |
| Missing [feature] | X | X% | Escalate to product |
| Poor champion | X | X% | Improve multi-threading playbook |

─── COMPETITIVE BREAKDOWN ───
| Competitor | Head-to-Head Deals | Our Win Rate | Trend |
|---|---|---|---|
| [Competitor A] | X | X% | ↑ / ↓ / → |
| [Competitor B] | X | X% | |

─── PRODUCT GAPS IDENTIFIED ───
| Gap | Loss Impact | Priority | Product Team Response |
|---|---|---|---|
| [Feature X] | X deals / $X ARR | P1 | On roadmap Q[X] |

─── MESSAGING GAPS ───
[What are buyers misunderstanding about us?]
[What competitor claims are most damaging?]

─── RECOMMENDED ACTIONS ───
1. PMM: Update [battlecard/deck/one-pager] by [date]
2. Sales: Retrain on [objection] by [date]
3. Product: Review [feature gap] for prioritization
4. Marketing: Create content addressing [misconception]
```

---

### Отслеживание доли голоса (Share of Voice)

```
SHARE OF VOICE REPORT
Period: [Month/Quarter]

─── SEARCH SHARE OF VOICE ───
[Use tools: SEMrush, Ahrefs, Moz]

| Competitor | Estimated Monthly Organic Traffic | SOV % | YoY Change |
|---|---|---|---|
| Us | X | X% | |
| [Competitor A] | X | X% | |
| [Competitor B] | X | X% | |
| Others | X | X% | |

Key keyword battles:
| Keyword | Our Rank | Comp A Rank | Comp B Rank |
|---|---|---|---|
| [head term] | | | |
| [secondary kw] | | | |

─── SOCIAL SHARE OF VOICE ───
[Use tools: Brandwatch, Mention, Sprout Social]

| Brand | Mentions (period) | SOV % | Sentiment |
|---|---|---|---|
| Us | X | X% | X% positive |
| [Competitor A] | X | X% | |

─── PR / EARNED MEDIA SOV ───
| Brand | Articles | SOV % | Top Publication |
|---|---|---|---|
| Us | X | X% | |
| [Competitor A] | X | X% | |

─── ACTIONS ───
- Keyword gaps to close: [list]
- Topics competitors dominate: [list + content plan]
- Brand sentiment issues: [list + response plan]
```

---

### Фреймворк карты позиционирования

*Из PMM-скилла Computer — визуальный стратегический инструмент*

```
POSITIONING MAP

Step 1: Choose your axes
- X-axis: [Dimension 1, e.g., "Ease of Use" → "Power/Complexity"]
- Y-axis: [Dimension 2, e.g., "Enterprise-focused" → "SMB-focused"]

Choose axes that:
a) Matter to your buyers (validated in research)
b) Differentiate players in your market
c) Favor your position

Step 2: Plot competitors
[Create 2x2 with competitors placed by perception]

Step 3: Identify white space
- Where are there no competitors?
- Is that white space desirable (demand) or empty for a reason (no market)?

Step 4: Validate with research
- Survey buyers: "Where would you place each vendor on these dimensions?"
- Win/loss data: What attributes did you win/lose on?

Step 5: Use in messaging
- Your position = the "owned" quadrant
- Your category name should imply your position
- Every piece of content should reinforce your axis values

COMMON AXIS PAIRS BY MARKET:
| Market | X-axis | Y-axis |
|---|---|---|
| CRM | Ease of use ← → Customization | SMB ← → Enterprise |
| Analytics | Self-serve ← → Full-service | Descriptive ← → Predictive |
| Security | Point solution ← → Platform | Reactive ← → Proactive |
| MarTech | Channel-specific ← → All-in-one | Campaign ← → Lifecycle |
```

---

## Объединённый скилл: оптимизация в магазинах приложений (ASO)

*Из уникального набора скиллов Computer — исчерпывающий фреймворк для роста мобильных приложений*

### Основы ASO

ASO — это процесс оптимизации мобильных приложений в App Store (iOS) и Google Play для максимизации органической видимости и конверсии. У него два компонента:

1. **Оптимизация ключевых слов (Keyword Optimization)** — чтобы вас находили (показы)
2. **Оптимизация коэффициента конверсии (Conversion Rate Optimization)** — чтобы устанавливали (CVR)

Их нужно оптимизировать совместно. Много показов при низком CVR = потраченная впустую видимость. Высокий CVR при малом числе показов = потолок роста.

---

### Процесс исследования ключевых слов

```
STEP 1: SEED LIST GENERATION
Sources:
- Your app's own description and category
- Top competitor apps (read their metadata)
- User reviews (exact language users use)
- App Store Search Ads suggested terms
- Apple Search Ads keyword tool
- Google Keyword Planner (proxy for intent)
- AppFollow, Sensor Tower, or AppTweak for volume data

STEP 2: KEYWORD EVALUATION MATRIX
| Keyword | Search Volume (1-10) | Difficulty (1-10) | Relevance (1-10) | Priority Score |
|---|---|---|---|---|
| [kw] | | | | (Vol × Rel) / Diff |

STEP 3: KEYWORD PLACEMENT HIERARCHY
Priority 1 — App Name/Title (highest weight)
Priority 2 — Subtitle (iOS) / Short Description (Android)
Priority 3 — Keyword Field (iOS only, 100 chars)
Priority 4 — Description (Android indexes this; iOS does not)

STEP 4: RULES
- Do NOT repeat keywords across fields (no bonus for repetition)
- Do NOT include your app name in the keyword field
- DO use singular OR plural (not both)
- DO include competitor brand names (if allowed by policy)
- DO localize — don't just translate; research local search terms
```

---

### Оптимизация листинга в магазине приложений

#### Формула заголовка (Title)

```
[Brand Name]: [Primary Keyword] + [Secondary Keyword]
Max: 30 characters (iOS), 50 characters (Android)

Examples:
"Duolingo: Language Lessons" — brand + primary kw
"Calm: Sleep & Meditation" — brand + two kws
"Robinhood: Investing for All" — brand + kw + value prop
```

#### Оптимизация скриншотов

```
SCREENSHOT STRATEGY:
Screenshot 1 (most important — shown in search results):
- Feature your #1 value prop
- Bold headline text (5-7 words max)
- Show product UI (real, not mockup)
- High contrast; readable at thumbnail size

Screenshots 2-3:
- Address top objections or secondary benefits
- Sequential story ("problem → solution" or "feature 1 → feature 2")

Screenshots 4-10:
- Social proof (ratings, awards, press)
- Key features
- Use case scenarios

DESIGN RULES:
- Consistent color scheme across all screenshots
- Overlay text on every screenshot (images alone don't convert)
- Portrait vs. landscape: test both for your category
- Localize screenshots for top markets (text + cultural imagery)
```

#### Превью-видео (Preview Video)

```
APP PREVIEW VIDEO:
Length: 15-30 seconds (sweet spot)
First 3 seconds: Most compelling moment (autoplay is muted)
Structure:
  0-3s: Hook (what does this app DO — show, don't tell)
  3-15s: Core value props (3 max)
  15-30s: CTA or brand moment

TECHNICAL SPECS:
- iOS: Up to 3 videos, portrait or landscape, H.264 or HEVC
- Android: YouTube URL embedded in Play Store listing
- Subtitles: Required (muted autoplay)
```

---

### Оптимизация коэффициента конверсии (CVR) для магазина приложений

```
CVR BENCHMARKS BY CATEGORY (median, iOS App Store):
- Games: 30-35%
- Utilities: 25-30%
- Health & Fitness: 20-25%
- Finance: 15-20%
- Productivity: 20-25%
- Social: 25-30%

FACTORS AFFECTING CVR:
1. Icon (A/B test via App Store Product Page Optimization)
2. Screenshots (biggest lever; test arrangement and creative)
3. Preview video (can ↑ CVR 25-30% if done well)
4. Ratings & reviews (below 4.2 stars = significant CVR drop)
5. App name subtitle (second line in search results)
6. Ratings count (500+ = trust threshold for most categories)

A/B TESTING:
- iOS: App Store Product Page Optimization (PPO) — up to 3 variants
- Android: Google Play Store Listing Experiments — up to 3 variants
- Test one variable at a time: icon OR screenshots OR video
- Minimum run time: 7 days; recommended: 4-6 weeks
- Significance threshold: 90%+ confidence

RATINGS & REVIEWS STRATEGY:
- Prompt for ratings at high-satisfaction moments only
  (post-achievement, post-save, post-positive action)
- Use SKAdNetwork + Smart App Banners for attribution
- Respond to all negative reviews within 48 hours
- Monitor: AppFollow, Appbot, or ReviewTrackers
```

---

### Метрики и отчётность ASO

```
ASO DASHBOARD — WEEKLY METRICS

━━━ VISIBILITY ━━━
| Metric | This Week | Prior Week | Target |
|---|---|---|---|
| Keyword Rankings (avg position, tracked set) | | | |
| # Keywords in Top 10 | | | |
| # Keywords in Top 50 | | | |
| Estimated Organic Impressions | | | |
| Category Ranking (top category) | | | |

━━━ CONVERSION ━━━
| Metric | This Week | Prior Week | Benchmark |
|---|---|---|---|
| App Store Impressions | | | |
| Product Page Views | | | |
| Tap-Through Rate (Impressions → Page Views) | | | |
| Conversion Rate (Page Views → Installs) | | | |
| Total Organic Installs | | | |

━━━ REPUTATION ━━━
| Metric | Current | Change | Target |
|---|---|---|---|
| Average Rating (current version) | | | >4.5 |
| Total Ratings (all versions) | | | |
| Review Response Rate | | | >90% |
| Sentiment Score | | | >80% positive |
```

---

## Объединённый скилл: prompt-инжиниринг для маркетинга

*Из уникальных возможностей Computer — полный фреймворк prompt-инжиниринга, адаптированный под маркетинговые сценарии*

### Базовые принципы промтинга

#### 1. Role Prompting (ролевой промтинг)

Назначьте конкретную экспертную идентичность, чтобы получить вывод экспертного качества.

```
FORMAT:
"You are a [specific expert role] with [X years] experience in [domain].
You specialize in [specific niche]. You have worked with [context]."

EXAMPLES:
"You are a senior B2B content strategist with 10 years of experience 
in SaaS marketing. You specialize in thought leadership content for 
CFOs and finance leaders at mid-market companies."

"You are an expert email copywriter who has written for Hubspot, 
Marketo, and Intercom. Your emails have been studied as best-in-class 
for their clarity, personalization, and conversion rates."

"You are a brand strategist who has led rebranding projects at 
Fortune 500 companies. You think in frameworks and always connect 
messaging back to positioning strategy."
```

#### 2. Context Injection (внедрение контекста)

Дайте модели всё необходимое до того, как просить вывод.

```
CONTEXT INJECTION TEMPLATE:

PRODUCT: [Name, category, primary function]
TARGET AUDIENCE: [Persona, job title, company size, pain points]
TONE & VOICE: [Adjectives, examples of on-brand writing]
BRAND RULES: [What to avoid, required disclaimers]
COMPETITIVE CONTEXT: [How we differ from alternatives]
GOAL: [What action should this content drive?]
FORMAT REQUIREMENTS: [Length, structure, platform]

EXAMPLE:
PRODUCT: Acme — an AI-powered expense management platform for SMBs
TARGET AUDIENCE: Finance managers at 50-500 person companies; frustrated 
  with manual expense reports; time-poor; skeptical of "AI" claims
TONE: Confident, direct, no fluff. Like a trusted finance colleague, 
  not a vendor pitch.
BRAND RULES: Never use the word "revolutionary". Always quantify claims.
COMPETITIVE CONTEXT: We're faster to implement than Concur (2 weeks vs 
  6 months) and cheaper than Expensify at scale.
GOAL: Email open → click to demo landing page
FORMAT: Cold email, 5-7 sentences, subject line + body + CTA
```

#### 3. Chain-of-Thought Prompting (цепочка рассуждений)

Для сложной работы над маркетинговой стратегией заставьте модель рассуждать пошагово.

```
FORMAT: Add "Think step by step" or structure the steps explicitly.

EXAMPLE — Campaign Strategy:
"Before writing the campaign brief, think through the following:
1. Who is the exact audience for this campaign? List 3 specific personas.
2. What is the ONE thing they need to believe to take action?
3. What objections do they have to that belief?
4. What proof points overcome each objection?
5. What channel reaches them with highest signal-to-noise?

Now, using your answers above, write the campaign brief."
```

#### 4. Few-Shot Examples (примеры в промте)

Покажите модели, как выглядит хороший результат, до того как просить вывод.

```
FORMAT:
"Here are 3 examples of [content type] that are on-brand for us:

EXAMPLE 1:
[Paste example]

EXAMPLE 2:
[Paste example]

EXAMPLE 3:
[Paste example]

Now write a [content type] for [new topic] in the same style."

WHEN TO USE:
- When you have existing on-brand content to reference
- When style/tone is hard to describe but easy to show
- When previous AI outputs were off-brand
- For social captions, email subject lines, ad headlines
```

#### 5. Output Format Control (контроль формата вывода)

Будьте явны насчёт структуры, длины и формата.

```
FORMAT CONTROL COMMANDS:
- "Write exactly [N] words."
- "Use bullet points only. No prose."
- "Respond in JSON format with keys: [key1], [key2], [key3]."
- "Write 5 variations. Label them Variant A through E."
- "Output a markdown table with columns: [col1], [col2], [col3]."
- "Write at a 6th-grade reading level."
- "Use only short sentences. Max 15 words per sentence."
- "Do not use the words: [list]. Find synonyms."
```

---

### Библиотека маркетинговых промтов

#### Промты для создания контента

```
BLOG POST OUTLINE:
"You are an expert SEO content strategist. Create a detailed outline 
for a blog post targeting the keyword '[keyword]'. The post should:
- Rank for [intent type] search intent
- Be comprehensive enough to earn featured snippets
- Include FAQ section targeting People Also Ask
- Be structured for [audience type]
Include: H1, H2s, H3s, word count per section, and internal link suggestions."

HEADLINE VARIATIONS:
"Generate 10 headline variations for a blog post about [topic].
Use these formulas: How-to, Listicle, Question, Contrarian, 
Data-led, and 'Ultimate Guide'. 
The target keyword is [keyword]. 
Each headline should be under 65 characters.
Mark your top 3 picks with a ★."

SOCIAL CAPTION:
"Write a LinkedIn post about [topic/announcement] for [company].
- Tone: [professional/conversational/provocative]
- Audience: [persona]
- Include: a hook, 3 key points, and a question to drive comments
- Length: 150-200 words
- Do not use emojis or hashtags"

EMAIL SUBJECT LINES:
"Generate 15 email subject line options for an email about [topic].
The email goes to [audience] in the [stage] of our funnel.
Include: curiosity gaps, benefit-led, number-led, question-based, 
and personalization token variants.
Mark the 5 you'd A/B test first."
```

#### Промты для стратегии кампаний

```
AUDIENCE RESEARCH:
"You are a market researcher specializing in B2B SaaS.
I need a deep-dive profile of [persona: e.g., VP of Marketing at a 
50-200 person SaaS company].

Provide:
1. Day-in-the-life narrative (what does their day look like?)
2. Top 5 professional frustrations
3. Top 3 career aspirations
4. Where they consume content (channels + publications)
5. How they make buying decisions (process + influencers)
6. Language they use to describe their problems (exact phrases)
7. What would make them immediately dismiss a vendor

Be specific. Use first-person language where it helps."

MESSAGING FRAMEWORK:
"Develop a messaging framework for [product/feature/campaign].
Structure:
1. Positioning statement (Geoffrey Moore format)
2. Elevator pitch (30 seconds)
3. Value propositions (3 tiers: business, functional, emotional)
4. Proof points for each value prop
5. Objection-response pairs (top 5)
6. Tagline options (5 variants)"

CAMPAIGN CONCEPT:
"We're launching a campaign for [product/offer] targeting [audience].
Budget: [range]. Timeline: [dates]. Goal: [objective + metric].

Propose 3 distinct campaign concepts. For each:
1. Campaign name and tagline
2. Big idea (the creative insight)
3. Hero channel and format
4. Supporting channels
5. Key messages for each audience segment
6. Why this concept will resonate with [audience]"
```

#### Промты для аналитики и отчётности

```
PERFORMANCE ANALYSIS:
"I'm sharing [time period] marketing performance data.
[Paste data or describe metrics]

Analyze:
1. What's performing above expectations and why?
2. What's underperforming and what are the likely causes?
3. What optimizations should we make in the next 30 days?
4. What does this data suggest about our strategy for next quarter?
5. What data are we missing that would sharpen this analysis?

Be specific. Use the numbers. Avoid generic advice."

BUDGET REALLOCATION:
"Based on this channel performance data: [paste data]

Recommend a budget reallocation for next month.
Assumptions: Total budget stays at $[X]. 
Objective: Maximize [MQLs / pipeline / revenue].

Provide:
1. Recommended allocation by channel (table with $, %, change from current)
2. Rationale for each increase and decrease
3. Expected impact on [primary KPI]
4. Risks of this reallocation and mitigations"
```

#### Промты для конкурентной разведки

```
COMPETITOR ANALYSIS:
"Analyze [competitor name] as if you were their CMO.
1. What is their current positioning and messaging strategy?
2. Who is their ideal customer profile (ICP)?
3. What content themes and formats do they prioritize?
4. What are their top 3 marketing strengths?
5. Where are their biggest marketing vulnerabilities?
6. What moves would you predict they'll make in the next 12 months?
7. How should we respond to their strategy?"

BATTLECARD DEVELOPMENT:
"Create a sales battlecard for [competitor] that our SDRs can use 
in a 2-minute conversation.

Include:
1. Their pitch in one sentence (steel-man it)
2. Our three-word response to their main claim
3. One discovery question that exposes their weakness
4. Our #1 proof point against them
5. The customer who switched from them (or hypothetical quote)
6. When we lose to them and why (be honest)"
```

---

## Уникальные возможности Computer, которых нет в Claude Code

### Что Computer умеет делать, на что традиционные маркетинговые скиллы не способны

| Возможность | Описание | Маркетинговый сценарий |
|---|---|---|
| **Живое веб-исследование** | Загрузка и анализ любой публичной веб-страницы в реальном времени | Конкурентная разведка, актуальные цены, свежие новости |
| **Генерация изображений** | Создание бренд-визуалов через ИИ | Макеты рекламных креативов, графика для соцсетей, заголовочные изображения блога |
| **Анализ данных** | Запуск Python/кода на загруженных файлах данных | Анализ эффективности кампаний, когортное моделирование |
| **Синтез из множества источников** | Объединение данных из веба, файлов и памяти | Отчёты о рыночных исследованиях, конкурентные ландшафты |
| **Интеграция с внешними инструментами** | Подключение к HubSpot, Salesforce, Google Analytics и т.д. | Живые данные кампаний, инсайты из CRM |
| **Создание длинных документов** | Генерация целых презентаций, отчётов, one-pager'ов | Кампанийные брифы, презентации для совета директоров, планы запуска |
| **Итеративная доработка** | Правка и улучшение контента в диалоге | Тестирование заголовков, итерации текста |
| **Симуляция персоны** | Отвечать как целевой клиент для проверки месседжинга | Тестирование сообщений, прогнозирование возражений |

---

### Рабочий процесс симуляции персоны

*Уникальная возможность Computer — протестируйте свой месседжинг до того, как тратить деньги*

```
WORKFLOW: Message Testing via Persona Simulation

STEP 1: Define the persona
"For the rest of this conversation, you are [Persona Name].
[Detailed description: role, company, pain points, background, 
attitudes toward vendors, what you've tried before]
Respond as this person would in real life — including skepticism, 
business jargon, and gut reactions."

STEP 2: Show them your message
"I'm going to show you a piece of marketing content. React as [Persona] 
would if they encountered this in the wild. Be honest and critical."
[Paste your ad, email, landing page, etc.]

STEP 3: Debrief
"Now step out of character. Based on your simulation:
1. What would likely resonate with this persona?
2. What would make them skeptical or disengage?
3. What questions would this messaging leave unanswered?
4. What one change would most improve this content for this persona?"

STEP 4: Iterate
Revise based on feedback, then re-run simulation.

USE CASES:
- Email subject line testing ("Which of these 5 would you open?")
- Landing page headline testing
- Cold outreach review
- Objection mapping
- Pricing page review
```

---

### Рабочий процесс конкурентной разведки в реальном времени

```
WORKFLOW: Weekly Competitive Pulse Check

PROMPT TEMPLATE:
"Research [competitor name] and summarize:
1. Any new product announcements or feature launches in the past 30 days
2. Changes to their pricing page (if accessible)
3. New content they've published (blog, case studies, guides)
4. Job postings that signal strategic direction
5. Social media campaigns currently running
6. Any press coverage or mentions in industry publications

Format as a competitive intel brief with an 'Implications for Us' section."

CADENCE RECOMMENDATION:
- Tier 1 competitors (head-to-head): Weekly
- Tier 2 competitors (adjacent): Monthly  
- Market signals (VC funding, M&A, category news): Weekly scan

TRIGGER ALERTS FOR:
- Pricing changes (bookmark their pricing page)
- New case studies (sign up for their blog)
- Job postings (set LinkedIn alert for their company + marketing roles)
- G2 reviews (monitor for patterns in recent reviews)
```

---

### Шаблоны PR и коммуникаций

*Из библиотеки Claude Code — отсутствуют во встроенных скиллах Computer*

#### Шаблон пресс-релиза

```
FOR IMMEDIATE RELEASE

[HEADLINE — Present tense, active voice, key news in <100 chars]
[SUBHEADLINE — Supporting detail or key stat]

[City, Date] — [Company Name], [brief descriptor], today announced 
[what was announced]. [Second sentence: why it matters + key benefit].

"[Quote from executive — reaction to the news, strategic significance.]"
said [Name], [Title], [Company].

[Paragraph 2: Context and details — what it is, how it works, 
when it's available, who it's for]

[Paragraph 3: Customer quote or data point validating the announcement]

"[Customer or partner quote here.]"
said [Name], [Title], [Company].

[Paragraph 4: Additional context, market opportunity, background]

[BOILERPLATE]
About [Company Name]
[2-3 sentences: what the company does, founding year, key traction metric, 
headquarters. Same text used in every press release.]

Media Contact:
[Name]
[Email]
[Phone]
[Website]
```

#### Шаблон медиа-питча

```
SUBJECT: [Newsy, specific subject line — not a PR subject line]
Examples:
- "Data: 73% of remote workers are burning out faster in 2024"
- "Exclusive: [Company] launching [thing] — first look?"
- "Source for your story on [topic they recently covered]"

BODY:
[Personalized hook — reference their specific recent article or beat]

[1-sentence news hook: what's the story?]

[2-3 sentences: why this matters NOW, data/proof, timeliness]

[The ask — be specific]
"Would you be interested in an exclusive briefing / data embargo / 
source interview for your coverage of [topic]?"

[What you can offer]
- Exclusive data from [X] survey of [N] respondents
- Executive interview: [Name, Title]
- Customer case study access
- Embargo until [date]

[Signature]
[Name] | [Title] | [Company]
[Phone] | [Email]

NOTES:
- Keep total email under 150 words
- Follow up once, 3-5 business days later
- Do NOT mass blast — personalize every pitch
- Target journalists who COVER your beat, not just any journalist
```

#### Плейбук кризисных коммуникаций

```
CRISIS RESPONSE FRAMEWORK

STEP 1: TRIAGE (First 30 minutes)
[ ] Confirm the facts — what happened, what's verified vs. rumored?
[ ] Assess severity: [P1: Existential / P2: Reputational / P3: Operational]
[ ] Assemble response team: CEO/exec, Legal, PR lead, CS lead
[ ] Hold on all scheduled social/email until reviewed
[ ] Set up monitoring: Google Alerts, social listening, news monitoring

STEP 2: INITIAL RESPONSE (Within 2 hours for P1/P2)
Key principle: Acknowledge before you have all the answers.

Initial statement template:
"We are aware of [situation]. We take [this matter / the safety of 
our customers / data privacy] extremely seriously. We are investigating 
and will provide an update by [specific time]. 
[If needed: immediate action we've taken]." 

Channels for initial statement:
- Website banner / status page
- Social media (Twitter/X first, then LinkedIn)
- Direct email to affected customers
- Proactive media outreach (get ahead of the story)

STEP 3: DETAILED RESPONSE (Within 24 hours)
Structure:
1. What happened (facts only — no speculation)
2. Who was affected and how
3. What we did immediately
4. What we are doing next
5. What we are doing to prevent recurrence
6. How affected parties can get help / be made whole

TONE GUIDELINES:
✅ Do: Own it, be specific, show empathy, commit to actions
❌ Don't: Minimize, deflect, use passive voice ("mistakes were made")
❌ Don't: Go silent, over-lawyer the statement, make it about the company

STEP 4: ONGOING COMMUNICATION
- Update cadence: Every 24 hours until resolved
- Designate single spokesperson
- Brief internal teams before external communications
- Document everything for post-mortem

STEP 5: POST-CRISIS
[ ] Post-mortem: What happened, why, what we learned
[ ] Process improvements implemented
[ ] Customer recovery program (if needed)
[ ] Media follow-up: share resolution story
[ ] Internal learnings shared across team
```

---

*Этот объединённый skill-документ — живой справочник, сочетающий лучшее из структурированных маркетинговых шаблонов Claude Code и встроенных маркетинговых скиллов Computer. Используйте как живой справочник — обновляйте по мере развития процессов вашей команды.*
