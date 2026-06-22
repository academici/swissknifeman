---
name: go-to-market
bucket: pm
version: 0.1.0
description: GTM-стратегия, ICP, messaging framework, каналы привлечения, launch plan
risk: draft
persona: pm
tags: [gtm, market, monetization]
requires: [competitive-analysis, monetization-design]
produces_for: [product-roadmap, pitch-deck]
outputs: ["docs/01_Business/06_Go_To_Market.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Go-To-Market (GTM)

Применять когда: задача на GTM-стратегию, выход на рынок, каналы привлечения, launch plan, ICP, messaging.

---

## Принцип

GTM = кому, через что, с каким сообщением, в каком порядке.
Без чёткого ICP (Ideal Customer Profile) GTM — это стрельба из дробовика.

---

## Шаг 1. ICP (Ideal Customer Profile)

Не "все пользователи" — а максимально конкретный первый сегмент.

```markdown
## ICP v1

**Тип:** [B2B / B2C / B2B2C]
**Сегмент:** [Малый бизнес / Фрилансеры / Студенты / ...]
**Размер компании:** [1-10 / 10-50 / 50-200 сотрудников] (для B2B)
**Гео:** [Страна / Регион]
**Проблема:** [Конкретная боль одной строкой]
**Триггер покупки:** [Что заставляет искать решение прямо сейчас]
**Альтернатива:** [Что используют сейчас вместо нашего продукта]
**Причина переключиться:** [Почему выберут нас, а не останутся на текущем]
```

---

## Шаг 2. Messaging Framework

| Элемент | Содержание |
|:---|:---|
| **Value proposition** | [Что делает продукт + для кого + результат] одна строка |
| **Tagline** | < 10 слов, запоминаемо |
| **Elevator pitch** | 2-3 предложения для инвестора |
| **Боли (Pain)** | Топ-3 боли, которые решаем |
| **Выгоды (Gain)** | Топ-3 конкретных результата |
| **Proof points** | Конкретные цифры или кейсы (или [placeholder]) |

---

## Шаг 3. Каналы привлечения

Оценить по матрице:

| Канал | Стоимость | Скорость | Масштаб | Приоритет |
|:---|:---|:---|:---|:---|
| Organic SEO | Низкая | Медленно | Высокий | 🟡 Средний |
| Paid ads (Meta/Google) | Высокая | Быстро | Высокий | 🔴 Только после PMF |
| Content / Community | Низкая | Медленно | Средний | 🟢 Старт |
| Partnerships | Средняя | Средне | Средний | 🟢 Если есть нетворк |
| Product-led growth | Низкая | Средне | Высокий | 🟢 При наличии freemium |
| Direct sales / outreach | Средняя | Быстро | Низкий | 🟢 На старте для B2B |

---

## Шаг 4. Launch Plan

Фазы:

```
Phase 0: Pre-launch (до релиза)
- Waitlist / landing page
- Seeding сообщества (Reddit, Telegram, ProductHunt)
- 10-20 beta-пользователей из ICP

Phase 1: Soft launch (неделя 1-4)
- Закрытый бета-доступ
- Сбор feedback
- Итерация продукта

Phase 2: Public launch
- ProductHunt / Hacker News / AppSumo (если подходит)
- PR / Media outreach
- Первые платящие

Phase 3: Growth
- Включение платных каналов только после: CAC < LTV и Retention ≥ 40% (Day 30)
```

---

## Шаг 5. GTM как функция (Launch/Scale)

Launch-plan выше — это запуск. На Launch/Scale-стадии задача другая: **построить repeatable growth engine**, а не разовый launch. Organic growth (founder-led selling, Product Hunt, личные связи) имеет потолок, и большинство фаундеров упираются в него до того, как впервые построили настоящую GTM-функцию.

**Repeatable & channel-driven (Launch-exit):** рост предсказуем через конкретные каналы с понятной экономикой — **CAC, LTV, payback** (числа, которые знаешь и можешь защитить), а не «повезло с постом». Сверять с `unit-economics`.

**Audience-segmented voice (Scale):** на Scale нужно достучаться не только до новых юзеров, но и до **инвесторов** и **enterprise-байеров**. У каждой аудитории свой словарь и свои критерии оценки:
| Аудитория | Что хочет слышать |
|---|---|
| Пользователи | боль → результат, time-to-value |
| Enterprise-байеры | reliability, security/compliance, SLA, support, integration depth |
| Инвесторы/аналитики | moat narrative, growth-механика, TAM, unit economics |

Создать **brand voice & story** + product-marketing инфраструктуру (interactive demo, integration docs, API-references, sandbox), чтобы GTM-motion работал асинхронно. Moat narrative для инвесторов/enterprise берётся из `defensibility`.

> GTM-функция не обязана быть большой, чтобы быть эффективной — та же AI-инфраструктура, что построила продукт, bootstrap'ит и вывод на рынок.

---

## Формат в документе

Размещать в `docs/01_Business/06_Go_To_Market.md`

---

## Что агент добавляет сам

- Специфику каналов для данной вертикали (SaaS vs Consumer vs Marketplace)
- Red flags: "Если нет retention — реклама только ускорит слив бюджета"
- Синергии с другими проектами vault если есть пересечение аудитории
- Конкретные площадки для launch (не абстрактно "социальные сети")

---

## Жёсткие запреты

НЕЛЬЗЯ:
- ICP "все, кому нужен [продукт]" — слишком широко
- Запускать платные каналы до проверки retention
- GTM без конкретной метрики успеха (что значит "успешный launch")

---

## Связанные скиллы

- `founder/competitive-analysis` — вход для GTM: рынок, конкуренты, JTBD, незанятая ниша (требуется ДО GTM).
- `pm/monetization-design` — выбранная модель монетизации задаёт каналы и messaging (требуется ДО GTM).
- `pm/unit-economics` — источник гейтов запуска платных каналов (CAC < LTV, payback); сверять с метриками отсюда.
- `pm/product-roadmap` — потребитель: ICP и фазы launch ложатся в фазирование продукта.
- `founder/startup-lifecycle` — рамка: launch-plan = вход в Launch, repeatable channel-driven growth = Launch-exit.
- `founder/defensibility` — поставщик moat narrative для investor/enterprise voice на Scale.
- `founder/pitch-deck` — потребитель: GTM-секция деки берётся отсюда.
