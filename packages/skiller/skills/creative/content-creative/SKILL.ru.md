---
name: content-creative-super-skill
bucket: creative
version: 1.0.0
description: Comprehensive creative studio skill merging Perplexity Computer's video production, speech synthesis, image generation, and website building with Claude Code's canvas design, algorithmic art, brand guidelines, frontend design, artifacts builder, content frameworks, content calendar, and prompt engineering. Use when creating visual content, designing interfaces, building brands, generating videos/images/audio, writing content, planning content calendars, or doing any creative production work.
license: MIT
metadata:
  author: get-zeked
  version: '1.0'
adapters: [claude, cursor, fable]
sha256: ""
---

> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

# Супер-скилл «Контент и креатив»

Полное руководство по креативному производству, объединяющее лучшее из AI-нативных креативных инструментов Perplexity Computer с проверенными в бою фреймворками дизайна, контента и инженерии Claude Code. Используйте этот скилл всякий раз, когда на повестке любая креативная, брендовая, дизайнерская, контентная, аудио- или видео-задача.

---

## Оглавление

1. [Анализ пробелов: Perplexity Computer против Claude Code](#section-1-gap-analysis-table)
2. [Визуальный дизайн и canvas](#section-2-visual-design--canvas)
3. [Идентичность бренда и гайдлайны](#section-3-brand-identity--guidelines)
4. [Frontend-дизайн и веб-артефакты](#section-4-frontend-design--web-artifacts)
5. [Генеративное искусство и анимация](#section-5-generative-art--animation)
6. [Аудио и речь](#section-6-audio--speech)
7. [Создание контента и копирайтинг](#section-7-content-creation--copywriting)
8. [Контент-календарь и планирование](#section-8-content-calendar--planning)
9. [Промпт-инжиниринг для креативной работы](#section-9-prompt-engineering-for-creative-work)
10. [Уникальные возможности Perplexity Computer](#section-10-unique-perplexity-computer-capabilities)

---

## Раздел 1: Таблица анализа пробелов

Понимание того, что привносит каждая экосистема — и где объединённый супер-скилл добавляет новую мощь.

### Матрица сравнения возможностей

| Возможность | Perplexity Computer | Claude Code | Добавление объединённого супер-скилла |
|---|---|---|---|
| Генерация изображений ИИ | ✅ nano_banana_2, nano_banana_pro; фотореализм, иллюстрация, художественный стиль; img2img; 1:1, 16:9, 9:16, 4:3, 3:4 | ❌ Нет нативного инструмента генерации изображений | Шаблоны дизайн-промптов, оптимизированные под модели nano_banana; референс-воркфлоу img2img |
| Генерация видео ИИ | ✅ Sora 2, Sora 2 Pro, Veo 3.1, Veo 3.1 Fast; клипы 4–12 сек; альбомная/портретная ориентация | ❌ Нет нативной генерации видео | Фреймворк раскадровки; скрипты сцепления кадров; пайплайны сшивки клипов |
| Текст в речь (TTS) | ✅ Gemini 2.5 Pro TTS, ElevenLabs TTS v3; многоголосый JSON-диалог; 99 языков; диаризация | ❌ Нет нативного TTS | Гайд по кастингу голосов; воркфлоу производства подкастов; конвенции маркировки диаризации |
| Транскрипция аудио | ✅ 99 языков, диаризация спикеров, тайм-коды по словам/символам | ❌ | Чек-лист QA транскрипции; гайд по маркировке спикеров |
| Визуальный дизайн на основе вёрстки | ❌ Нет программного canvas | ✅ Скилл Canvas Design (PNG/PDF через Python/reportlab) | Воркфлоу дизайна «философия прежде всего»; паттерн многостраничной вёрстки в стиле подарочного альбома |
| Генеративное/алгоритмическое искусство | ❌ | ✅ Скилл Algorithmic Art (p5.js, сидированная случайность, системы частиц) | Исследователь вариаций сидированного арта; воркфлоу коллекций в стиле Art Blocks |
| Анимированные GIF | ❌ | ✅ Slack GIF Creator (PIL, easing, валидаторы) | Шпаргалка по Slack GIF; библиотека концептов анимации |
| Создание сайтов/веб-приложений | ✅ Скилл website-building (дизайн-система, Tailwind, анимация, стандарты качества) | ✅ Frontend Design + Web Artifacts Builder (React, TypeScript, shadcn/ui) | Единый чек-лист качества; дерево решений по выбору стека |
| Фреймворк голоса бренда | ✅ marketing-brand-voice (5 измерений, адаптация тона, аудит консистентности) | ✅ Brand Guidelines (цвета/шрифты Anthropic) + голос бренда alirezarezvani (архетипы Юнга) | Объединённая система идентичности бренда на 12 архетипов; матрица многоканальной консистентности |
| Контент-фреймворки | ❌ | ✅ Content Creator (шаблоны блогов, соцсетей, email); Content Frameworks (how-to, listicle, кейс, thought leadership) | Расширено видеосценариями, копирайтингом лендингов, фреймворками пресс-релизов |
| SEO-оптимизация | ❌ | ✅ Инструмент SEO Optimizer (плотность ключевых слов, структура заголовков, мета-теги) | SEO-воркфлоу, интегрированный с живым веб-исследованием Perplexity для подбора ключевых слов |
| Контент-календарь | ❌ | ✅ Шаблон месячного календаря + стратегия столпов | Расширено данными по тайминту платформ и матрицей репурпозинга |
| Промпт-инжиниринг | ❌ Промпты выводятся из параметров инструментов | ✅ Prompt Engineer Toolkit (zero-shot → мета-промптинг; A/B-тестирование; контроль версий) + Senior Prompt Engineer (RAG, оркестрация агентов) | Специфичные для креатива шаблоны промптов: генерация изображений, генерация видео, озвучка, бренд-копирайтинг |
| Живое веб-исследование | ✅ search_web, fetch_url, search_social | ❌ | Воркфлоу генерации идей контента: исследование трендов → бриф → контент → дистрибуция |
| Мониторинг соцсетей | ✅ search_social (операторы X/Twitter) | ❌ | Пайплайн «тренд → контент»; протокол аудита контента конкурентов |
| 400+ интеграций с приложениями | ✅ Коннекторы внешних инструментов (Gmail, Notion, Slack, CRM и т. д.) | ❌ | Автоматизация дистрибуции контента; воркфлоу кросс-платформенной публикации |
| Мониторинг по расписанию | ✅ Задачи по расписанию | ❌ | Каденция мониторинга производительности контента |

### Что умеет только Perplexity Computer (нативные дифференциаторы)

- Генерировать настоящие видеоклипы моделями Sora/Veo (не раскадровки — настоящие MP4)
- Генерировать настоящие изображения моделями nano_banana (не Python-рисунки — настоящие AI-изображения)
- Синтезировать речевое аудио (Gemini TTS, ElevenLabs)
- Транскрибировать аудио/видеофайлы с диаризацией спикеров
- Разворачивать живые сайты, доступные по публичному URL
- Искать в X/Twitter креативные тренды в реальном времени
- Подключаться к 400+ внешним сервисам для дистрибуции контента
- Планировать повторяющийся мониторинг и отчётность по контенту

### Что привносит только Claude Code (взаимодополняющие сильные стороны)

- Алгоритмическое/генеративное искусство через p5.js с сидированной случайностью
- Программный canvas-дизайн с выводом PNG/PDF музейного качества
- Производство анимированных GIF с PIL + функциями easing
- Сложные многокомпонентные веб-артефакты React/TypeScript/shadcn
- Инструментарий глубокого SEO-анализа
- Систематический промпт-инжиниринг с регрессионным тестированием и контролем версий
- Фреймворки оценки RAG и оркестрации агентов

### Объединённые добавления (новое в супер-скилле)

- Единый шаблон креативного брифа, применимый ко всем модальностям вывода
- Матрица кросс-платформенного репурпозинга контента (1 идея → 10 ассетов)
- Шпаргалка по размерам изображений и видео для конкретных платформ
- Фреймворки креативного направления (именование эстетических движений, словарь мудбордов)
- Пайплайн «бренд → производство»: идентичность бренда → контент-стратегия → производство → дистрибуция
- Гайд по кастингу голосов для многоголосых продакшнов

---

## Раздел 2: Визуальный дизайн и Canvas

**Объединённые источники:** Canvas Design (anthropics/skills) + инструмент generate_image (Perplexity Computer) + принципы дизайна

### 2.1 Выбор метода визуального производства

| Потребность | Инструмент | Вывод |
|---|---|---|
| Статичный дизайн музейного/постерного качества | Воркфлоу Canvas Design (Python/reportlab/matplotlib) | PNG или PDF |
| Фотореалистичное AI-изображение | generate_image (nano_banana_2) | PNG |
| AI-иллюстрация/художественный стиль | generate_image (nano_banana_pro для сложного) | PNG |
| Анимация на основе существующего изображения | generate_image с референсом image_path (img2img) | PNG |
| Многостраничный дизайн/подарочный альбом | Многостраничный воркфлоу Canvas Design | PDF |
| Генеративное искусство (интерактивное, анимированное) | Воркфлоу Algorithmic Art (p5.js) | HTML-артефакт |

### 2.2 Воркфлоу создания философии дизайна

Прежде чем создавать любой визуальный вывод, установите **Визуальную философию** — эстетическое движение, которое направляет все креативные решения.

#### Шаг 1: Назовите движение (1–2 слова)

Примеры: «Brutalist Joy» / «Chromatic Silence» / «Metabolist Dreams» / «Concrete Poetry» / «Analog Meditation»

#### Шаг 2: Напишите манифест философии (4–6 абзацев)

Затроньте каждое измерение по одному разу, без повторов:

- **Форма и пространство**: Как формы соотносятся с негативным пространством? Монументально или интимно?
- **Цвет и материал**: Какая палитра управляет? Какие текстуры или материальные качества?
- **Масштаб и ритм**: Каково соотношение большого к малому, быстрого к медленному?
- **Композиция и баланс**: Симметрия, асимметрия, диагональный поток, разрушение сетки?
- **Визуальная иерархия**: Куда взгляд идёт первым, вторым, последним?

**Критическое требование:** Многократно подчёркивайте мастерство — финальная работа должна выглядеть «скрупулёзно выполненной», «продуктом глубокой экспертизы», «кропотливого внимания», «исполнения мастер-уровня».

#### Шаг 3: Определите концептуальное зерно

Извлеките тонкую, нишевую отсылку, заложенную в запросе пользователя. Это душа, незаметно вплетённая в искусство — как джазовый музыкант цитирует другую песню. Только знающие уловят; все остальные переживают мастерскую композицию.

#### Шаг 4: Исполните на Canvas

Правила исполнения на canvas:
- 90% визуала, 10% необходимого текста (текст как визуальный акцент, не объяснение)
- Ничто не накладывается и не вылезает за границы canvas — всегда корректные поля
- Типографика дизайнерская: ищите уникальные шрифты в `./canvas-fonts`; сочетайте характерный дисплейный шрифт с утончённым текстовым
- Никогда не используйте дженерик-шрифты (Arial, Inter, Roboto, системные шрифты)
- Стремитесь к работе, которая выглядит так, будто над ней бесчисленные часы трудился кто-то из топа своей области
- Для проходов доработки: делайте существующие элементы более цельными, а не добавляйте новые

#### Шаг 5: Проход доработки

При доработке спросите: «Как сделать то, что уже здесь, ещё больше произведением искусства?» Избегайте добавления новых фигур или графики. Вместо этого: уплотняйте интервалы, улучшайте цветовую гармонию, усиливайте типографические решения, углубляйте композиционный баланс.

### 2.3 Генерация изображений ИИ (Perplexity Computer)

#### Модели
- **nano_banana_2** — По умолчанию. Фотореалистичные фото, чистые иллюстрации, декоративная графика. Быстрая.
- **nano_banana_pro** — Более высокое качество/детализация для сложной художественной работы.

#### Соотношения сторон
| Соотношение | Сценарий использования |
|---|---|
| 1:1 | Посты в соцсетях, аватары, превью |
| 16:9 | Заголовки блогов, превью YouTube, слайды презентаций |
| 9:16 | Instagram Stories, TikTok, вертикальные соцсети |
| 4:3 | Стандартная альбомная, баннеры сайтов |
| 3:4 | Стандартная портретная, Pinterest, редакционный формат |

#### Эффективная структура промпта для изображения

```
[Дескриптор стиля] [Субъект/сцена] [Заметки о композиции] [Цветовая палитра] [Освещение/настроение] [Заметки о техническом качестве]
```

**Пример — Фотореализм:**
```
Photorealistic professional product photo of a sleek black leather wallet on a marble surface, 
centered composition with shallow depth of field, warm amber and cream tones, soft natural 
window light from the left, studio-quality with subtle shadow, no text
```

**Пример — Иллюстрация:**
```
Flat vector illustration of a mountain landscape at dusk, geometric shapes, 
layered silhouettes in deep navy, burnt orange, and dusty rose, 
minimal and modern, suitable for app background, no text
```

**Пример — Художественный:**
```
Oil painting style portrait of a woman reading in a library, 
Renaissance lighting, rich chestnut and gold palette, 
painterly brushstrokes, museum-quality composition, moody and contemplative
```

#### Воркфлоу img2img (референсные изображения)

При анимации или трансформации существующего изображения:
1. Передайте до 10 референсных изображений через параметр `images`
2. Чётко опишите перенос стиля или правку
3. Укажите, что сохранить, а что изменить

```
Transform this product photo to match the visual style of the reference images: 
muted warm tones, slight grain texture, editorial magazine aesthetic. 
Preserve the product placement and composition.
```

### 2.4 Быстрая справка по принципам дизайна

#### Теория цвета
- **Аналоговые**: Соседние на цветовом круге — гармоничные, низкий контраст (напр., синий + сине-зелёный + бирюзовый)
- **Комплементарные**: Противоположные — высокий контраст, яркое напряжение (напр., оранжевый + синий)
- **Триадические**: Три равноотстоящих — сбалансированные, энергичные (напр., красный + жёлтый + синий)
- **Раздельно-комплементарные**: Один цвет + два соседних к его комплементу — мягче комплементарных
- **Монохроматические**: Один тон, варьируемая насыщенность/светлота — изысканные, цельные

#### Системы доминирующего цвета
- Задайте **доминирующий цвет** (60%), **вторичный цвет** (30%) и **акцент** (10%)
- Доминирующие цвета с резкими акцентами превосходят робкие, равномерно распределённые палитры
- Используйте CSS custom properties / дизайн-токены для консистентности между компонентами

#### Правила сочетания типографики
- Сочетайте характерный **дисплейный шрифт** (заголовки, крупный текст) с утончённым **текстовым шрифтом** (читаемым на малых размерах)
- Никогда не используйте: Inter, Roboto, Arial как основные дисплейные шрифты
- Примеры сильных сочетаний: Playfair Display + Source Serif Pro / Clash Grotesk + Instrument Serif / Bebas Neue + DM Sans
- Контраст начертаний: жирный дисплейный против regular текстового создаёт визуальную иерархию без цвета

#### Принципы композиции
- **Правило третей**: Размещайте ключевые элементы в пересечениях сетки
- **Визуальный вес**: Более крупные, тёмные и насыщенные элементы несут больше веса
- **Негативное пространство**: Намеренная пустота создаёт воздух и фокус
- **Выравнивание**: Каждый элемент должен выравниваться по сетке или другому элементу — никогда не плавать произвольно
- **Иерархия**: Один доминирующий элемент, один вторичный, всё остальное подчинено

### 2.5 Шаблон креативного брифа (визуальные проекты)

```markdown
## Visual Creative Brief

**Project name:** 
**Deliverable format:** [ ] PNG  [ ] PDF  [ ] HTML  [ ] Video  [ ] GIF
**Dimensions/aspect ratio:** 
**Brand context:** (existing brand OR new brand OR no brand constraints)

**Objective:** What does this piece need to accomplish?
**Target audience:** Who will see it and what should they feel?
**Key message:** The single most important thing to communicate

**Visual direction:**
- Aesthetic movement/philosophy name: 
- Mood reference (3 adjectives): 
- Color palette constraint (if any): 
- Typography constraint (if any): 
- Elements to include: 
- Elements to avoid: 

**Conceptual seed/reference:** (subtle, niche — not literal)

**Delivery deadline:** 
**Approval contacts:** 
```

---

## Раздел 3: Идентичность бренда и гайдлайны

**Объединённые источники:** Brand Guidelines (anthropics/skills) + Brand Voice Framework (alirezarezvani/claude-skills) + marketing-brand-voice (встроенный скилл Perplexity Computer)

### 3.1 Обзор архитектуры бренда

Полная идентичность бренда имеет пять слоёв:

1. **Фундамент**: Миссия, видение, ценности, цель
2. **Личность**: Архетип + атрибуты тона
3. **Система голоса**: Измерения голоса, принципы письма, языковые гайдлайны
4. **Визуальная идентичность**: Система цвета, типографика, иконография, стиль фотографии
5. **Применение**: Гайдлайны под конкретные каналы, аудиты консистентности

### 3.2 12 архетипов личности бренда по Юнгу

Выберите один **основной** и один **вторичный** архетип. Основной доминирует; вторичный добавляет нюанс.

| Архетип | Базовое желание | Тон бренда | Стиль контента | Примеры брендов |
|---|---|---|---|---|
| **The Innocent** (Невинный) | Безопасность, счастье | Оптимистичный, искренний, честный | Простой, благотворный, ностальгический | Dove, Coca-Cola |
| **The Everyman** (Свой парень) | Принадлежность, связь | Дружелюбный, скромный, без претензий | Близкий, инклюзивный, повседневный | IKEA, Target |
| **The Hero** (Герой) | Мастерство, отвага | Смелый, вдохновляющий, компетентный | С фокусом на достижения, дающий силу | Nike, FedEx |
| **The Outlaw** (Бунтарь) | Освобождение, революция | Дерзкий, разрушающий, провокационный | Нарушающий правила, антиистеблишмент | Harley-Davidson, Virgin |
| **The Explorer** (Искатель) | Свобода, открытие | Авантюрный, неугомонный, аутентичный | С фокусом на путешествие, экспансивный | REI, Jeep |
| **The Creator** (Творец) | Инновация, самовыражение | Образный, визионерский, оригинальный | С фокусом на ремесло, дотошный к деталям | Apple, Adobe |
| **The Ruler** (Правитель) | Контроль, порядок, качество | Властный, командующий, утончённый | Премиальный, эксклюзивный, престижный | Mercedes-Benz, Rolex |
| **The Magician** (Маг) | Трансформация, чудо | Мистический, визионерский, харизматичный | Нарративы трансформации, возможность | Disney, Dyson |
| **The Lover** (Любовник) | Близость, удовольствие | Страстный, чувственный, тёплый | Движимый желанием, эмоционально резонирующий | Chanel, Häagen-Dazs |
| **The Caregiver** (Заботливый) | Служение, забота | Сострадательный, терпеливый, поддерживающий | Помогающий, защищающий, общинный | Johnson & Johnson, UNICEF |
| **The Jester** (Шут) | Удовольствие, юмор | Игривый, юморной, непочтительный | Развлечение прежде всего, самоироничный | Old Spice, Dollar Shave Club |
| **The Sage** (Мудрец) | Знание, истина | Знающий, уверенный, аналитический | Основанный на данных, образовательный, авторитетный | Google, Harvard |

### 3.3 Фреймворк голоса бренда — 5 измерений

Для каждого измерения разместите бренд на спектре:

#### Измерение 1: Формальность
```
Formal ←————————————————→ Casual
  |         |          |         |
Legal   Professional  Conversational  Casual
```
- **Formal** (формальный): Коммуникации с инвесторами, юридические документы, кризисные ответы
- **Professional** (профессиональный): B2B-вайтпейперы, кейсы, пресс-релизы
- **Conversational** (разговорный): Посты в блог, соцсети, email-рассылки
- **Casual** (непринуждённый): Посты в сообществах, бэкстейдж-контент

#### Измерение 2: Выражение экспертизы
```
Expert ←————————————————→ Peer
  |         |          |         |
Authority  Guide   Knowledgeable  Peer
```

#### Измерение 3: Уровень энергии
```
High Energy ←————————————→ Calm
  |         |          |         |
Energetic  Motivating  Measured  Serene
```

#### Измерение 4: Эмоциональная теплота
```
Warm ←———————————————————→ Cool
  |         |          |         |
Nurturing  Friendly  Professional  Clinical
```

#### Измерение 5: Прямота
```
Direct ←—————————————————→ Suggestive
  |         |          |         |
Imperative  Clear  Inviting  Narrative
```

### 3.4 Выбор атрибутов тона

Выберите 3–5 основных атрибутов тона:

| Атрибут | Описание | Пример фразы |
|---|---|---|
| **Authoritative** (Авторитетный) | Позиционирование отраслевого эксперта | «Our research shows that 87% of businesses...» |
| **Friendly** (Дружелюбный) | Доступный и тёплый | «We get it — this can be overwhelming...» |
| **Innovative** (Инновационный) | Прогрессивный, визионерский | «The future of X is already here...» |
| **Trustworthy** (Заслуживающий доверия) | Надёжный, прозрачный | «Here's exactly what happened and why...» |
| **Inspiring** (Вдохновляющий) | Мотивирующий, воодушевляющий | «You have the power to transform...» |
| **Educational** (Образовательный) | Информативный, полезный | «Here's how to think about this step by step...» |
| **Witty** (Остроумный) | Умный, развлекательный (использовать умеренно) | «Plot twist: the data actually says...» |
| **Empathetic** (Эмпатичный) | Понимающий, признающий | «We know you've been frustrated by this...» |

### 3.5 Языковая система

#### Слова к использованию (по архетипу)
- **Глаголы действия**: Transform, accelerate, optimize, unlock, elevate, pioneer, craft, build, shape
- **Позитивные дескрипторы**: Seamless, powerful, intuitive, strategic, intentional, thoughtful
- **С фокусом на результат**: Results, growth, impact, clarity, momentum, trust, confidence

#### Слова, которых стоит избегать (универсальные)
- **Жаргон**: Synergy, leverage (как глагол), bandwidth (в значении доступность), circle back, move the needle
- **Заезженные заявления**: Innovative, disruptive, cutting-edge (если только не действительно применимо)
- **Слабые квалификаторы**: Very, really, just, maybe, hopefully, kind of, sort of
- **Негативное обрамление**: Can't, won't, impossible — заменяйте на challenge, opportunity, working on

### 3.6 Система цветов бренда Anthropic (референс)

Для выводов, которые должны нести идентичность бренда Anthropic:

| Роль цвета | Hex | Использование |
|---|---|---|
| Dark (основной текст, тёмные фоны) | `#141413` | Заголовки, основной текст, фон тёмной темы |
| Light (светлые фоны, текст на тёмном) | `#faf9f5` | Фоны страниц, текст на тёмном |
| Mid Gray (вторичные элементы) | `#b0aea5` | Подзаголовки, подписи, метаданные |
| Light Gray (сдержанные фоны) | `#e8e6dc` | Карточки, разделители, сдержанные секции |
| Orange (основной акцент) | `#d97757` | CTA, выделения, ссылки |
| Blue (вторичный акцент) | `#6a9bcc` | Вторичные действия, информационные состояния |
| Green (третичный акцент) | `#788c5d` | Состояния успеха, теги, поддерживающие акценты |

**Типографика:**
- Заголовки (24pt+): **Poppins** (фолбэк Arial)
- Основной текст: **Lora** (фолбэк Georgia)

### 3.7 Чек-лист аудита консистентности голоса бренда

Прогоняйте этот аудит перед публикацией любого контента:

**Согласованность голоса**
- [ ] Соответствует выбранному архетипу(ам) — ощущается ли это как бренд?
- [ ] Атрибуты тона присутствуют (3–5 выбранных вами)
- [ ] Уровень формальности уместен для канала
- [ ] Перспектива (мы/вы/третье лицо) консистентна с выбором бренда

**Качество языка**
- [ ] Нет жаргона или запрещённых слов
- [ ] Активный залог ≥80% предложений
- [ ] Выгоды подчёркнуты над функциями
- [ ] «You» встречается чаще, чем «we»

**Структура**
- [ ] Чёткое ценностное предложение в первом абзаце
- [ ] Уместный призыв к действию для материала
- [ ] Мобильно-дружественное форматирование (короткие абзацы, сканируемость)
- [ ] Оксфордские запятые используются консистентно

**Инклюзивность**
- [ ] Гендерно-нейтральный язык повсюду
- [ ] Нет идиом, которые не переводятся глобально
- [ ] Разнообразные перспективы представлены там, где уместно
- [ ] Доступное форматирование (правильная иерархия заголовков, alt-текст для изображений)

### 3.8 Адаптации голоса под конкретные каналы

| Канал | Формальность | Длина | Ключевой принцип |
|---|---|---|---|
| Главная страница сайта | Professional | Сканируемая, короткая | Заголовки от выгоды, 6–12 слов |
| Пост в блог | Conversational | 1 500–2 500 слов | Хук в первых 50 словах; ценность в каждой секции |
| LinkedIn | Professional–Conversational | 150–300 слов | Инсайт + история + вопрос |
| Twitter/X | Casual | 280 символов | Смелый зачин, останавливающий скролл |
| Instagram | Casual–Conversational | 100–200 слов + хэштеги | История прежде всего; хэштеги блоком ниже |
| Email-рассылка | Conversational | Сканируемая | Одно главное сообщение; зачин с личным наблюдением |
| Промо-email | Conversational | Короткий | Боль → выгода → CTA → срочность |
| Пресс-релиз | Formal | 400–600 слов | Перевёрнутая пирамида; ведомый данными |
| Кейс | Professional | 800–1 200 слов | Вызов → решение → измеримые результаты |

### 3.9 Шаблон креативного брифа идентичности бренда

```markdown
## Brand Identity Brief

**Brand name:** 
**Industry/sector:** 
**Founded/launch date:** 
**Tagline (current or proposed):** 

**Mission statement:** (why do we exist?)
**Vision statement:** (what future are we building?)
**Core values:** (3–5 principles that guide decisions)

**Primary archetype:** (from Jung's 12)
**Secondary archetype:** 
**Voice dimensions:**
- Formality: [1=Formal → 5=Casual]: 
- Energy: [1=High → 5=Calm]: 
- Warmth: [1=Warm → 5=Cool]: 

**3 tone attributes:** 
**3 words we always use:** 
**3 words we never use:** 

**Visual direction:**
- Color palette (3–5 hex codes): 
- Primary typeface: 
- Body typeface: 
- Visual style (photographic/illustrative/abstract/typographic): 

**Audience personas:** (describe 2–3 primary audiences)
**Competitors to differentiate from:** 
**Brand DNA statement:** (one sentence: "We are the only brand that ___")
```

---

## Раздел 4: Frontend-дизайн и веб-артефакты

**Объединённые источники:** Frontend Design (anthropics/skills) + Web Artifacts Builder (anthropics/skills) + website-building (встроенный скилл Perplexity Computer)

### 4.1 Дерево решений по выбору стека

```
What are you building?
│
├─ Simple single-page HTML experience (no framework needed)
│   → Plain HTML/CSS/JS artifact
│   → Focus on CSS animations, custom properties, vanilla JS
│
├─ Component-rich interactive app (state management, routing)
│   → React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui
│   → Use Web Artifacts Builder workflow
│
├─ Full website requiring live deployment and public URL
│   → website-building skill (HTML/CSS/JS + Tailwind)
│   → Deploy via Perplexity Computer sandbox
│
└─ Generative/algorithmic interactive art
    → p5.js single HTML artifact
    → See Section 5 (Generative Art)
```

### 4.2 Дизайн-мышление до кода

Прежде чем написать хоть строку кода, ответьте:

1. **Назначение**: Какую проблему решает этот интерфейс? Кто им пользуется?
2. **Тон**: Зафиксируйтесь на эстетической крайности — не сваливайтесь по умолчанию в «чисто и современно»
   - Brutally minimal / Maximalist chaos / Retro-futuristic / Organic/natural
   - Luxury/refined / Playful/toy-like / Editorial/magazine / Brutalist/raw
   - Art deco/geometric / Soft/pastel / Industrial/utilitarian / Cyberpunk
3. **Дифференциация**: Что одно человек запомнит?
4. **Типографический якорь**: Какая пара шрифтов определяет визуальную идентичность?

**Критическое правило:** И смелый максимализм, и утончённый минимализм оба преуспевают — проваливается робость. Исполняйте выбранную эстетику с полной отдачей и точностью.

### 4.3 Гайдлайны frontend-эстетики

#### Типографика
- Выбирайте шрифты, которые **красивы, уникальны и интересны**
- Никогда не сваливайтесь по умолчанию в: Inter, Roboto, Arial, system-ui как дисплейные шрифты
- Сильные дисплейные варианты: Clash Grotesk, Playfair Display, Bebas Neue, Canela, Fraunces, Syne, General Sans
- Сильные текстовые варианты: Source Serif Pro, DM Sans, Instrument Sans, Literata, Spectral
- Сочетайте характерный дисплейный шрифт с утончённым, читаемым текстовым

#### Цвет и тема
- Зафиксируйтесь на **цельной эстетике** — используйте CSS custom properties для консистентности
- Задайте доминирующий цвет (60%), вторичный (30%), акцент (10%)
- Доминирующий + резкий акцент превосходит робкие, равномерно распределённые палитры
- Никогда не сваливайтесь по умолчанию в фиолетовые градиенты на белом фоне

#### Движение и анимация
- Только CSS для HTML-проектов; библиотека Motion для React
- **Одна хорошо срежиссированная загрузка страницы** со ступенчатыми появлениями создаёт больше восторга, чем разрозненные микровзаимодействия
- Используйте `animation-delay` для ступенчатых последовательностей появления
- Запуск по скроллу и hover-состояния, которые искренне удивляют
- Избегайте: дёрганых переходов, беспричинного вращения, движения ради движения

#### Пространственная композиция
- Неожиданные раскладки: асимметрия, наложение, диагональный поток, элементы, разрушающие сетку
- Щедрое негативное пространство **или** контролируемая плотность — зафиксируйтесь на одном
- Никаких раскладок-колонок по центру по умолчанию, если только контент этого не требует

#### Фоны и визуальные детали
- Создавайте атмосферу через: градиентные сетки, шумовые текстуры, геометрические паттерны, слоистые прозрачности
- Драматичные тени, декоративные рамки, кастомные курсоры, зернистые оверлеи, когда уместно эстетике
- Никогда не сваливайтесь по умолчанию в `background: #ffffff` без намеренного обоснования

### 4.4 Воркфлоу Web Artifacts Builder (React + shadcn/ui)

Для сложных многокомпонентных артефактов:

```bash
# Step 1: Initialize project
bash scripts/init-artifact.sh <project-name>
cd <project-name>

# Stack auto-configured:
# React 18 + TypeScript + Vite + Tailwind CSS 3.4.1
# 40+ shadcn/ui components pre-installed
# All Radix UI dependencies included
# Path aliases (@/) configured
# Parcel bundler configured

# Step 2: Develop
# Edit src/ files, build components in src/components/

# Step 3: Bundle to single HTML
bash scripts/bundle-artifact.sh
# Creates bundle.html — self-contained, all JS/CSS inlined

# Step 4: Share artifact with user
```

**Референс компонентов shadcn/ui:** https://ui.shadcn.com/docs/components

### 4.5 Паттерны Tailwind CSS для креативных UI

```css
/* Mesh gradient background */
.bg-mesh {
  background: radial-gradient(at 40% 20%, hsla(28,100%,74%,1) 0px, transparent 50%),
              radial-gradient(at 80% 0%, hsla(189,100%,56%,1) 0px, transparent 50%),
              radial-gradient(at 0% 50%, hsla(355,100%,93%,1) 0px, transparent 50%);
}

/* Noise texture overlay */
.texture-noise::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,...");
  opacity: 0.04;
  mix-blend-mode: multiply;
}

/* Staggered reveal animation */
.stagger-reveal > * {
  opacity: 0;
  transform: translateY(20px);
  animation: reveal 0.6s ease forwards;
}
.stagger-reveal > *:nth-child(1) { animation-delay: 0ms; }
.stagger-reveal > *:nth-child(2) { animation-delay: 100ms; }
.stagger-reveal > *:nth-child(3) { animation-delay: 200ms; }
```

### 4.6 Чек-лист стандартов качества

Перед отгрузкой любой frontend-работы:

**Функциональность**
- [ ] Все интерактивные элементы работают корректно
- [ ] Нет ошибок в консоли
- [ ] Формы валидируются и обрабатывают ошибки изящно
- [ ] Ссылки и навигация работают

**Визуальное качество**
- [ ] Типографика характерна и читаема на всех размерах
- [ ] Контраст цветов соответствует WCAG AA (4.5:1 для основного текста, 3:1 для крупного)
- [ ] Нет дженерик-эстетики ИИ (фиолетовые градиенты, заезженные шрифты, предсказуемые раскладки)
- [ ] Зафиксированность на чётком эстетическом направлении — не попытка быть всем

**Адаптивный дизайн**
- [ ] Хорошо выглядит на 320px, 768px, 1280px, 1920px
- [ ] Touch-цели ≥44px на мобильных
- [ ] Изображения не вылезают за контейнеры
- [ ] Нет горизонтального скролла на мобильных

**Производительность**
- [ ] Нет блокирующих ресурсов в `<head>`
- [ ] У изображений есть `loading="lazy"` где уместно
- [ ] Анимации используют `transform` и `opacity` (GPU-композитинг)
- [ ] Нет лишних ре-рендеров (React)

**Доступность**
- [ ] Семантичный HTML (правильная иерархия заголовков, лендмарки)
- [ ] У всех изображений есть осмысленный `alt`-текст
- [ ] Клавиатурная навигация работает
- [ ] Индикаторы фокуса видны

### 4.7 Дизайн-система лендинга

Высококонвертящий лендинг следует этой иерархии секций:

```
1. Hero
   - Headline: 6–12 words, benefit-focused, above the fold
   - Subheadline: 1–2 sentences expanding the headline
   - Primary CTA: high contrast, action verb + outcome ("Start free trial")
   - Social proof: logos, user count, or rating
   - Hero visual: product screenshot, illustration, or video

2. Problem / Agitate
   - Describe the pain point the audience knows
   - Make them feel understood before offering the solution

3. Solution Introduction
   - What the product/service does in plain language
   - 3–4 key benefits (not features)

4. Feature Showcase
   - Visual demonstration
   - Feature-benefit pairs
   - Each feature answers: "So what? What can I do with this?"

5. Social Proof
   - Testimonials (with real names, photos, company)
   - Case study results
   - Logos of recognizable customers

6. Pricing / Comparison
   - 3 tiers is the standard (good–better–best)
   - Highlight the recommended tier
   - Annual vs. monthly toggle

7. FAQ
   - Address the top 5 objections
   - Keep answers short and direct

8. Final CTA
   - Repeat the primary CTA
   - Add urgency or risk reversal (free trial, money-back guarantee)
```

---

## Раздел 5: Генеративное искусство и анимация

**Объединённые источники:** Algorithmic Art (anthropics/skills) + Slack GIF Creator (anthropics/skills) + video-production (встроенный скилл Perplexity Computer)

### 5.1 Выбор метода анимации

| Потребность | Метод | Вывод |
|---|---|---|
| Генеративное/алгоритмическое интерактивное искусство | p5.js (воркфлоу Algorithmic Art) | HTML-артефакт (интерактивный) |
| Slack-эмодзи или реакция-GIF | PIL + GIFBuilder (воркфлоу Slack GIF) | .gif (128×128 или 480×480) |
| Короткий AI-видеоклип (4–12 сек) | Инструмент generate_video (Sora/Veo) | .mp4 |
| Более длинное AI-видео (>12 сек) | Сцепление кадров + сшивка клипов | Несколько .mp4 → сшитые |
| Анимация продукта/демо | CSS/JS-анимация (воркфлоу Frontend) | HTML |
| Моушн-графика для веба | CSS-анимация + SVG | HTML/CSS |

### 5.2 Воркфлоу алгоритмического искусства (p5.js)

#### Создание алгоритмической философии

Как и визуальный дизайн, начинайте с вычислительной философии — эстетического движения, выраженного через код.

**Назовите движение:** «Organic Turbulence» / «Quantum Harmonics» / «Recursive Whispers» / «Field Dynamics» / «Stochastic Crystallization»

**Измерения философии, которые нужно затронуть:**
- Вычислительные процессы и математические соотношения
- Шумовые функции и паттерны случайности
- Поведения частиц и динамика полей
- Временная эволюция и состояния системы
- Параметрическая вариация и эмерджентная сложность

**Обязательные технические требования:**

```javascript
// ALWAYS use seeded randomness (Art Blocks pattern)
let seed = 12345;
randomSeed(seed);
noiseSeed(seed);

// Parameter structure
let params = {
  seed: 12345,
  // Quantities: how many?
  // Scales: how big, how fast?
  // Probabilities: how likely?
  // Ratios: what proportions?
  // Angles: what direction?
  // Thresholds: when does behavior change?
};

// Standard canvas
function setup() {
  createCanvas(1200, 1200);
}

function draw() {
  // Your generative algorithm
}
```

#### Обязательные фичи для интерактивных вьюеров

1. **Управление параметрами**: Слайдеры для числовых параметров, color pickers, обновления в реальном времени, кнопка сброса
2. **Навигация по сидам**: Отображение текущего сида, кнопки Prev/Next, кнопка Random, поле ввода сида
3. **Единый артефакт**: Весь код p5.js инлайн — никаких внешних файлов, кроме CDN p5.js

#### Библиотека алгоритмических философий

**«Organic Turbulence»**
Поля потока, управляемые слоистым шумом Перлина. Тысячи частиц, следующих за векторными силами, следы накапливаются в органические карты плотности. Множество октав шума создают турбулентные и спокойные зоны. Цвет возникает из скорости и плотности.

**«Quantum Harmonics»**
Частицы, инициализированные на сетке, несущие фазовые значения, эволюционирующие через синусоиды. Конструктивная интерференция создаёт яркие узлы; деструктивная создаёт пустоты. Простое гармоническое движение порождает сложные эмерджентные мандалы.

**«Recursive Whispers»**
Ветвящиеся структуры, рекурсивно подразделяющиеся. Каждая ветвь ограничена золотыми сечениями, слегка рандомизирована. L-системы порождают древовидные формы, ощущающиеся одновременно математическими и органическими.

**«Field Dynamics»**
Векторные поля из математических функций. Частицы рождаются на краях, текут вдоль линий поля, умирают в равновесии. Визуализация показывает только призрачные следы невидимых сил.

**«Stochastic Crystallization»**
Упаковка кругов или тесселяция Вороного. Случайные точки эволюционируют через релаксацию до равновесия. Ячейки расталкиваются; цвет основан на размере, числе соседей, расстоянии от центра.

### 5.3 Воркфлоу Slack GIF Creator

#### Требования Slack

| Формат | Размеры | FPS | Цвета | Макс. длительность |
|---|---|---|---|---|
| Emoji GIF | 128×128 (рекомендуется) | 10–15 | 48 | 3 секунды |
| Message GIF | 480×480 | 10–30 | 48–128 | Любая |

#### Основной воркфлоу

```python
from core.gif_builder import GIFBuilder
from PIL import Image, ImageDraw

# 1. Create builder
builder = GIFBuilder(width=128, height=128, fps=10)

# 2. Generate frames
for i in range(12):
    frame = Image.new('RGB', (128, 128), (240, 248, 255))
    draw = ImageDraw.Draw(frame)
    # Draw using PIL primitives (ellipse, polygon, line, rectangle)
    builder.add_frame(frame)

# 3. Save with optimization
builder.save('output.gif', num_colors=48, optimize_for_emoji=True)
```

#### Библиотека концептов анимации

| Концепт | Техника | Лучше всего для |
|---|---|---|
| **Shake/Vibrate** (Тряска/вибрация) | Смещение `math.sin()`, применённое к x и/или y | Тревога, оповещение, акцент |
| **Pulse/Heartbeat** (Пульс/сердцебиение) | Масштабирование `math.sin(t * freq * 2π)` между 0.8–1.2 | Уведомления, лайки |
| **Bounce** (Отскок) | `interpolate()` с `easing='bounce_out'` | Празднования, успех |
| **Spin/Rotate** (Вращение) | `image.rotate(angle)` — линейное или синусоидальное покачивание | Загрузка, обработка |
| **Fade In/Out** (Затухание) | RGBA alpha 0→1 или 1→0 | Переходы, появления |
| **Slide** (Сдвиг) | Старт за кадром, остановка с `easing='ease_out'` | Появляющиеся сообщения |
| **Zoom** (Зум) | Масштаб 0.1→2.0 или 2.0→1.0, обрезка по центру | Удар, фокус |
| **Explode** (Взрыв) | Частицы со случайными углами/скоростями, затухание | Празднования |

#### Доступные функции easing

```python
from core.easing import interpolate

t = i / (num_frames - 1)  # Progress 0.0 → 1.0
y = interpolate(start=0, end=400, t=t, easing='ease_out')

# Available: linear, ease_in, ease_out, ease_in_out,
#            bounce_out, elastic_out, back_out
```

#### Правила качества графики
- Всегда используйте `width=2` или выше для обводок — тонкие линии выглядят дилетантски
- Добавляйте визуальную глубину градиентами, слоистыми фигурами, бликами
- Используйте яркие, комплементарные цвета с контрастом
- Для сложных фигур: комбинируйте полигоны + эллипсы; тщательно рассчитывайте точки для симметрии

### 5.4 Генерация видео ИИ (Perplexity Computer)

#### Выбор модели

| Модель | Лучше всего для | Длина клипа | Стоимость |
|---|---|---|---|
| **sora_2** | По умолчанию. Высококачественные кинематографичные кадры | 4, 8, 12 сек | Стандартная |
| **sora_2_pro** | Максимальное качество, сложные сцены | 4, 8, 12 сек | Премиум |
| **veo_3_1** | Быстрая, фотореалистичная, разнообразные стили | 4, 6, 8 сек | Стандартная |
| **veo_3_1_fast** | Быстрые итерации, прототипирование | 4, 6, 8 сек | Ниже |

#### Соотношения сторон
- **16:9** — Альбомная/широкоэкранная (YouTube, презентации, ТВ)
- **9:16** — Портретная/вертикальная (TikTok, Instagram Stories, Reels)

#### Эффективная структура промпта для видео

```
[Camera movement] [Scene description] [Subject action] [Visual style] [Lighting/mood] [Audio cues if any]
```

**Пример — Кинематографичный продукт:**
```
Slow push-in shot of a glass perfume bottle on a dark marble surface, 
amber liquid catching the light as a single drop of water falls onto the marble beside it, 
hyper-realistic CGI product commercial style, dramatic chiaroscuro lighting, 
cinematic color grade, no text
```

**Пример — Лайфстайл:**
```
Handheld follow shot of a woman walking through a sun-drenched farmers market, 
dappled golden hour light, shallow depth of field, 
contemporary lifestyle brand aesthetic, warm analog film look, natural ambient sound
```

**Пример — Абстракция/художественный:**
```
Fluid simulation of metallic liquid mercury morphing into geometric shapes, 
macro lens, mirror-like surface reflections catching colored light, 
seamless loop, minimal electronic ambient soundtrack
```

#### Воркфлоу многоклипового видеопроизводства

Для видео длиннее 12 секунд:

```
Step 1: Storyboarding
  - Define key scenes and transitions
  - Estimate clip count (1 clip per scene/shot)
  - Write a prompt for each clip

Step 2: Frame Anchoring (for continuity)
  - Generate clip 1 (opening shot)
  - Screenshot the final frame of clip 1
  - Use that screenshot as image_path for clip 2
    → This creates visual continuity between clips

Step 3: Generate All Clips
  - Generate each clip with model, duration, and prompt
  - Download all .mp4 files to workspace

Step 4: Stitch Clips
  ffmpeg -i clip1.mp4 -i clip2.mp4 -i clip3.mp4 \
    -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]" \
    -map "[outv]" output_final.mp4

Step 5: Add Audio (if needed)
  ffmpeg -i output_final.mp4 -i voiceover.mp3 \
    -c:v copy -c:a aac -shortest final_with_audio.mp4
```

### 5.5 Шаблон раскадровки видео

```markdown
## Video Storyboard: [Project Name]

**Total duration target:** 
**Aspect ratio:** [ ] 16:9  [ ] 9:16
**Style reference:** 
**Music/audio brief:** 

---

### Clip 1 (Opening)
**Duration:** 
**Camera:** 
**Scene:** 
**Action:** 
**Model:** 
**Prompt:**
```
[Full video prompt here]
```
**Notes:**

### Clip 2
**Duration:** 
**Camera:** 
**Scene:** 
**Action:** 
**Transition from Clip 1:** (describe how they connect)
**Model:** 
**Prompt:**
```
[Full video prompt here]
```

[Continue for all clips...]

---

### Audio Track
**Voiceover:** [ ] Yes  [ ] No
**Script:** 
**Voice:** 
**Background music:** 
**SFX:** 
```

---

## Раздел 6: Аудио и речь

**Объединённый источник:** скилл speech (встроенный скилл Perplexity Computer) — текст-в-речь и транскрипция

### 6.1 Система «текст в речь»

#### Выбор модели

| Модель | Лучше всего для |
|---|---|
| **gemini_2_5_pro_tts** | По умолчанию. Высокое качество, естественная просодия, все стандартные сценарии |
| **elevenlabs_tts_v3** | Требуется 3+ различных спикера, либо пользователь явно запрашивает ElevenLabs |

**Правило:** Используйте Gemini (по умолчанию), если только: (a) пользователь явно не запрашивает ElevenLabs, либо (b) диалог не требует 3+ различных спикеров.

#### Производство с одним спикером

Создайте файл `.txt`, затем вызовите `text_to_speech` с желаемым голосом.

**Доступные голоса Gemini (выборка):**

| Голос | Характер |
|---|---|
| `kore` | По умолчанию. Нейтральный, профессиональный |
| `charon` | Глубокий, авторитетный |
| `fenrir` | Динамичный, энергичный |
| `aoede` | Тёплый, разговорный |
| `puck` | Яркий, бодрый |

#### Производство многоголосого диалога

Создайте файл `.json` с назначениями спикеров:

```json
[
  {"speaker": "aoede", "text": "Welcome to the show. I'm your host, and today we're diving into brand strategy."},
  {"speaker": "charon", "text": "Thanks for having me. Brand strategy is something most founders get completely wrong."},
  {"speaker": "aoede", "text": "What's the biggest mistake you see?"},
  {"speaker": "charon", "text": "They confuse logo design with brand identity. The logo is maybe five percent of the picture."}
]
```

Затем вызовите `text_to_speech` с путём к файлу `.json`. Голоса автоматически назначаются на каждого спикера.

#### Поддержка 99 языков

TTS поддерживает 99 языков. Укажите язык в содержимом текста — отдельный параметр не нужен. Модель определяет и сопоставляет язык с подходящей фонологией.

Распространённые ISO-коды для справки:
- English: `en` | Spanish: `es` | French: `fr` | German: `de` | Portuguese: `pt`
- Japanese: `ja` | Korean: `ko` | Chinese: `zh` | Arabic: `ar` | Hindi: `hi`
- Italian: `it` | Dutch: `nl` | Russian: `ru` | Turkish: `tr` | Polish: `pl`

### 6.2 Система транскрипции аудио

#### Опции конфигурации

| Параметр | Опции | Заметки |
|---|---|---|
| `diarize` | true / false | Включить идентификацию спикеров |
| `num_speakers` | 1–32 | Подсказка для точности диаризации (оставьте null для автоопределения) |
| `timestamps` | `none` / `word` / `character` | `none` → простой .txt; остальные → .json с таймингом |
| `language_code` | ISO 639-1 | Автоопределение, если не указан |

#### Поддерживаемые форматы
`.mp3`, `.wav`, `.mp4`, `.webm`, `.m4a`, `.ogg`, `.flac`

#### Конвенция маркировки диаризации спикеров

При диаризации многоголосого контента маркируйте консистентно:

```
SPEAKER_00: [first speaker heard]
SPEAKER_01: [second speaker heard]
SPEAKER_02: [third speaker heard]
```

Для именованных интервью/подкастов переименуйте спикеров после транскрипции:

```python
transcript = transcript.replace("SPEAKER_00:", "HOST:")
transcript = transcript.replace("SPEAKER_01:", "GUEST:")
```

### 6.3 Воркфлоу производства подкаста / озвучки

```
Step 1: Script Preparation
  - Write script as multi-speaker JSON (for 2 speakers) or .txt (single voice)
  - Mark pronunciation notes in brackets: [EMPH: strategy] [PAUSE: 1s]
  - Review for natural speech patterns — written language ≠ spoken language

Step 2: Voice Selection
  - Match voice character to brand archetype (see Section 3.2)
  - Test with a 50-word sample before committing to full script
  - For multi-speaker: assign voices by character (e.g., aoede=host, charon=expert guest)

Step 3: Generation
  - Generate audio with text_to_speech tool
  - Review output MP3

Step 4: Post-Processing (if needed)
  - Trim silence: ffmpeg -i input.mp3 -af silenceremove=1:0:-50dB output.mp3
  - Normalize levels: ffmpeg -i input.mp3 -filter:a loudnorm output_normalized.mp3
  - Add background music: ffmpeg -i voice.mp3 -i music.mp3 -filter_complex "[1:a]volume=0.1[bg];[0:a][bg]amix=inputs=2:duration=first" final.mp3

Step 5: Final Export
  - Deliver as MP3 for most platforms
  - WAV for professional audio editing
  - Specific podcast platforms may require specific bitrates (Spotify: 128kbps minimum)
```

### 6.4 Чек-лист QA транскрипции

После транскрипции аудио проверьте:

- [ ] Метки спикеров назначены корректно (выборочно проверьте 3+ переходов)
- [ ] Тайм-коды совпадают с аудио (проверьте пословные тайм-коды на минутах 0, 5, середине, конце)
- [ ] Технические термины и имена собственные написаны верно — автотранскрипция часто ошибается на названиях брендов, продуктов, аббревиатурах
- [ ] Слова-паразиты обработаны консистентно (`um`, `uh` — решите, оставить или убрать)
- [ ] Границы предложений осмысленны (автотранскрипция редко включает пунктуацию)
- [ ] Проверка уверенности на неоднозначных сегментах — переслушайте любые отмеченные участки

---

## Раздел 7: Создание контента и копирайтинг

**Объединённые источники:** Content Creator (alirezarezvani) + Content Frameworks & Templates (alirezarezvani) + marketing-content-creation (Perplexity Computer) + Brand Voice Framework

### 7.1 Мастер-воркфлоу создания контента

```
1. Audience & Intent
   → Who is this for? What do they need to feel, know, or do after reading?

2. Keyword & Topic Research (for SEO content)
   → Primary keyword: 500–5,000 searches/month (sweet spot)
   → 3–5 secondary keywords
   → 10–15 LSI (latent semantic indexing) keywords
   → Use Perplexity search_web for live keyword intelligence

3. Content Type Selection
   → Match format to intent: How-to (informational) / Listicle (inspiration) / 
     Case study (consideration) / Thought leadership (awareness) / 
     Landing page (conversion) / Press release (PR)

4. Outline using Template
   → Pull appropriate template from Section 7.3 below

5. Draft (no editing)
   → Write first draft without self-censoring
   → Target word count by type:
     Blog: 1,500–2,500 | Social: see platform guides | Email: scannable
     Landing page: value-driven, not word-count-driven

6. SEO Optimization Pass
   → Keyword in title, first paragraph, 2–3 H2 headings
   → Keyword density: 1–3%
   → Heading structure: one H1, logical H2/H3 hierarchy
   → Meta description: 150–160 characters

7. Brand Voice Edit
   → Run Brand Voice Consistency Audit (Section 3.7)
   → Ensure active voice ≥80%
   → Check for banned words

8. Platform Optimization
   → Apply platform-specific formatting (Section 7.6)
   → Adjust length, hashtags, visual requirements

9. CTA + Distribution
   → Every piece has one clear CTA
   → Schedule per content calendar (Section 8)
```

### 7.2 Формулы хуков и заголовков

#### Фреймворк AIDA
- **Attention** (Внимание): Захватите удивительным фактом, смелым заявлением или провокационным вопросом
- **Interest** (Интерес): Объясните, почему это важно именно им
- **Desire** (Желание): Нарисуйте картину их улучшенного состояния
- **Action** (Действие): Скажите ровно, что делать дальше

#### Фреймворк PAS
- **Problem** (Проблема): Прямо назовите болевую точку
- **Agitate** (Усиление): Заставьте почувствовать вес проблемы
- **Solution** (Решение): Представьте ответ

#### Формулы заголовков

| Формула | Шаблон | Пример |
|---|---|---|
| How-to | How to [Achieve X] Without [Pain Point] | How to Double Email Opens Without A/B Testing |
| Number List | [N] [Adjective] Ways to [Achieve Goal] | 7 Counterintuitive Ways to Beat Creative Block |
| Question | [Challenging Question Your Audience Has]? | Are You Making These 5 Brand Mistakes? |
| Contrarian | Why [Common Belief] Is [Wrong/Backwards/Costing You] | Why "Best Practices" Are Killing Your Brand |
| Specificity | How [Specific Person] Achieved [Specific Result] in [Timeframe] | How a 3-Person Team Grew to 50K Subscribers in 90 Days |
| Secret/Insider | The [Counterintuitive] Truth About [Topic] | The Uncomfortable Truth About Content Calendars |
| Fear of Missing | [N] Things You're Missing If You're Not [Doing X] | 6 Revenue Streams You're Ignoring in Your Content |

#### Формулы хуков для соцсетей

```
Type 1: Contrarian
"Unpopular opinion: [industry belief] is completely wrong."

Type 2: Specificity
"[Specific result] in [timeframe] with [unusual method]."

Type 3: Story opener
"Two years ago, [dramatic situation]. Today, [transformation]."

Type 4: Question
"What if [assumed truth] was actually [reframed truth]?"

Type 5: List promise
"[N] things I wish someone told me before [doing X]:"

Type 6: Direct address
"If you're a [specific audience] and you're not doing [X], read this."
```

### 7.3 Библиотека шаблонов постов в блог

#### Шаблон How-To гайда

```markdown
# How to [Achieve Desired Outcome] in [Timeframe]

## Introduction
[Hook: surprising fact, challenging question, or bold statement — 1–2 sentences]
[Problem statement: what pain this solves]
[Promise: what reader will learn and why it matters now]

## Prerequisites/What You'll Need
- [Tool/Resource 1]
- [Tool/Resource 2]
- [Estimated time to complete]

## Step 1: [Action Verb + Object]
[Clear instruction]
[Why this step matters]
[Common mistake to avoid]
[Visual aid or example if helpful]

## Step 2: [Action Verb + Object]
[Repeat structure above]

[Continue for all steps...]

## Troubleshooting Common Issues
### [Issue 1 Label]
**Symptom:** [What they'll observe]
**Cause:** [Why it happens]
**Fix:** [Exact solution]

## Results You Can Expect
- [Immediate outcome 1]
- [Long-term benefit]
- [Success metric to track]

## Next Steps
- [Advanced technique or related guide]
- [Relevant tool or resource]
- [CTA for product/service — soft sell]

## Conclusion
[Recap: 2–3 key points from the guide]
[Reinforce the value of what they've learned]
[Encouragement + final CTA]
```

#### Шаблон Listicle (список)

```markdown
# [Number] [Adjective] [Things/Ways/Tips] to [Achieve Goal] [in Year/Context]

## Introduction
[Context: trend or insight driving the topic]
[Promise: what they gain from reading]
[Credibility signal: why you can speak to this]

## 1. [First Item — Lead with Most Important or Most Surprising]
**Why it matters:** [Brief explanation — 1–2 sentences]
**How to implement:** [2–3 specific, actionable steps]
**Pro tip:** [Expert insight that elevates the advice]
**Example:** [Real-world application]

[Continue for all N items...]

## Bringing It All Together
[How these items work synergistically]
[Priority order for implementation]
[Expected timeline for results]

## Your Action Plan
1. Start with [easiest/most impactful item]
2. Next, tackle [second priority]
3. Measure [specific metric] after [timeframe]

## Conclusion & CTA
[2–3 sentence summary]
[CTA — specific action to take next]
```

#### Шаблон кейса (Case Study)

```markdown
# How [Company/Person] Achieved [Specific Result] Using [Your Solution/Method]

## Executive Summary
[Company overview — 1 sentence]
[Challenge faced — 1 sentence]
[Solution implemented — 1 sentence]
**Key results:** [Metric 1] | [Metric 2] | [Metric 3]

## The Challenge
[Industry context — why this challenge is common]
[Specific pain points — 2–3 concrete problems]
[Stakes — what was at risk if they didn't solve it]

## The Solution
[How they found/chose the solution]
[Implementation approach — phases if applicable]
[Timeline from start to results]

## The Results
### Quantitative Outcomes
- [Metric 1]: [Before] → [After] ([% change])
- [Metric 2]: $[Amount] saved/gained
- [Metric 3]: [Time reduction/increase]

### Qualitative Benefits
[Quote from key stakeholder]
[Team or customer experience improvement]

## Key Takeaways
1. [Lesson that applies broadly]
2. [Best practice discovered]
3. [Unexpected finding]

## Ready to Get These Results?
[CTA — book a demo, start a trial, contact us]
```

#### Шаблон Thought Leadership (экспертное лидерство)

```markdown
# [Provocative Statement About the Future of Your Industry]

## The Current State
[Where the industry is right now — establish common ground]

## The Seismic Shift
[The emerging trend, technology, or behavior changing everything]
[Data point or example that makes it concrete]

## Why [Conventional Approach] Will Fall Short
[Specific critique of the status quo]
[What companies doing X are missing]

## A New Framework for [Challenge]
[Your proposed model — give it a name if possible]
[How it works — 3–5 principles]
[What changes when you apply it]

## What This Means for [Your Audience's Role]
[Specific implications for their day-to-day]
[Skills to develop / things to stop doing]
[Timeline — when does this shift become irreversible?]

## The Path Forward
[Your prediction for the next 12–24 months]
[The companies/people who will win and why]
[What action to take now, before it's obvious]

## Join the Conversation
[Engage readers: What do you think? Comment/share]
[CTA: read more, subscribe, follow]
```

### 7.4 Библиотека шаблонов для соцсетей

#### Фреймворк поста LinkedIn

```
[🎯 OR bold statement — Pattern interrupt line that stops the scroll]

[Context paragraph: the situation, challenge, or observation — 3–5 sentences]

[Key insight or lesson you're sharing:]

• [Specific, actionable point 1]
• [Measurable outcome or evidence]
• [Unexpected finding or contrarian take]

[Brief story or example that makes the point real — 2–3 sentences]

[Takeaway: the single most important thing to remember]

[Engagement question: genuinely curious, not rhetorical?]

#[Industry] #[Topic] #[Audience]
```

**Оптимизация LinkedIn:**
- Оптимальная длина: 150–300 слов
- Постите изображения или карусели для 3× показов
- Лучшее время: Вт–Чт, 8–10:00 и 12–14:00 в часовом поясе аудитории
- Заканчивайте вопросом, чтобы стимулировать комментарии

#### Шаблон треда Twitter/X

```
1/ [Bold opening statement that stops the scroll — make a claim worth reading 10 tweets for]

2/ [Context: why this matters right now — data point or trend]

3/ [The problem most people face — specific, not vague]

4/ [Conventional solution — acknowledge what people try]

5/ [Why the conventional solution falls short — the gap]

6/ [Better approach — introduce it]

7/ [Step/element 1 of better approach]

8/ [Step/element 2]

9/ [Step/element 3]

10/ [Step/element 4 — if needed]

11/ [Real-world example or proof]

12/ Recap in 3 points:
→ [Point 1]
→ [Point 2]
→ [Point 3]

13/ [CTA: If this was useful, [follow/retweet/share]. Here's where to learn more: [link]]

14/ P.S. [Bonus insight or resource that rewards people who read to the end]
```

**Оптимизация Twitter/X:**
- Треды до 15 твитов работают лучше более длинных
- Первый твит должен работать автономно (он показывается без контекста)
- Изображения повышают вовлечённость на 150%
- Лучшее время: будни 9:00–15:00; избегайте вечеров пятницы

#### Шаблон подписи Instagram

```
[Attention-grabbing first line — appears in preview before "more"]

[Story or relatable scenario — 2–3 sentences that create emotional connection]

Here's what I learned:

[The key insight — make it specific and actionable]

[N] things that changed everything:
1️⃣ [First point — concrete, not vague]
2️⃣ [Second point — surprising or counterintuitive]  
3️⃣ [Third point — actionable]

[Engagement prompt: "Drop a ❤️ if you've been here!" or a direct question]

—
[Hashtags in a block below the dash — 10–30, mix of popular and niche]
#[hashtag1] #[hashtag2] #[hashtag3]
```

**Оптимизация Instagram:**
- Первая строка решает всё — должна зацепить до «more»
- Карусели получают 3× охват одиночных изображений
- Видео Reels: 7–15 секунд для максимального охвата
- Лучшее время: будни 11:00–13:00; пик Ср 11:00
- 20–30 хэштегов: микс широких (1M+), средних (100K–1M), нишевых (<100K)

#### Шаблон поста Facebook

```
[Question or bold statement — community-oriented]

[Narrative or context — 2–4 paragraphs, more conversational than LinkedIn]

[Value delivery: tips, insights, or resource]

[Community CTA: "Have you experienced this? Tell us in the comments" OR "Tag someone who needs to see this"]

[Link if applicable — Facebook reduces reach for link posts; consider posting link in comments]
```

#### Шаблон сценария видео TikTok / Short-Form

```
[0–3 sec: HOOK — Visual + text overlay that answers "Why should I watch this?"]
  Script: "[Bold claim or surprising statement]"
  
[3–10 sec: CONTEXT — Establish who this is for]
  Script: "If you're a [audience] who [challenge], this is for you."

[10–45 sec: VALUE DELIVERY]
  "[Step 1 / Point 1]"
  "[Step 2 / Point 2]"  
  "[Step 3 / Point 3]"
  [Keep each step to 1–2 sentences max]

[45–60 sec: CTA]
  Script: "Follow for more [topic] tips. Save this for when you need it."
  
[Caption: First line = hook. Hashtags: 3–5 niche + 2 broad]
```

### 7.5 Шаблоны email-маркетинга

#### Шаблон рассылки (Newsletter)

```
Subject: [Benefit or insight] — [curiosity/specificity element]
Preview text: [Complements subject, doesn't repeat it — adds urgency or context]

Hi [Name / Hey there],

[Personal observation or timely hook — 1–2 sentences that feel human, not broadcast]

---

## [Main Content Section Title]

[2–3 key points in scannable format]
• **[Point 1]:** [Benefit-focused explanation]
• **[Point 2]:** [Specific example or stat]
• **[Point 3]:** [Actionable tip they can use today]

---

## Resource of the Week
**[Title]** — [One sentence on why it's worth their time]
→ [Link]

---

## Quick Win You Can Implement Today
[Specific, actionable — 2–3 steps, under 100 words]

---

[Sign-off with personality]

P.S. [Bonus: additional value, soft CTA, or teaser for next issue]
```

#### Шаблон промо-email

```
Subject: [Specific, concrete benefit] by [deadline/timeframe]
Preview text: [Scarcity or exclusivity signal]

Hi [Name],

[Open by acknowledging their pain point or aspiration — 2–3 sentences]

[Transition: "That's why we built/created/launched X"]

Here's what you get:
✓ [Benefit 1 — outcome, not feature]
✓ [Benefit 2 — outcome, not feature]
✓ [Benefit 3 — outcome, not feature]

[Social proof: testimonial with name + company, or specific result data]

[Primary CTA button: "Get Started Free" / "Claim Your Spot" / "Start Today"]

[Urgency element: deadline, limited availability, or bonus that expires]

P.S. [Reinforce urgency OR add bonus not mentioned above — P.S. gets read almost as often as the subject line]
```

### 7.6 Справка по размерам изображений и видео для платформ

| Платформа | Тип изображения | Размеры | Заметки |
|---|---|---|---|
| Instagram | Лента, квадрат | 1080×1080 | Соотношение 1:1 |
| Instagram | Лента, альбомная | 1080×566 | Соотношение 1.91:1 |
| Instagram | Лента, портретная | 1080×1350 | Соотношение 4:5 (рекомендуется) |
| Instagram | Story/Reel | 1080×1920 | Соотношение 9:16 |
| Twitter/X | Изображение в твите | 1200×675 | Соотношение 16:9 |
| Twitter/X | Баннер профиля | 1500×500 | Соотношение 3:1 |
| LinkedIn | Изображение для шеринга | 1200×627 | Соотношение 1.91:1 |
| LinkedIn | Баннер | 1584×396 | Соотношение 4:1 |
| Facebook | Пост в ленте | 1200×630 | Соотношение 1.91:1 |
| Facebook | Stories | 1080×1920 | Соотношение 9:16 |
| YouTube | Превью | 1280×720 | Соотношение 16:9 |
| YouTube | Баннер | 2560×1440 | Оформление канала |
| TikTok | Видео | 1080×1920 | Соотношение 9:16 |
| Pinterest | Пин | 1000×1500 | Соотношение 2:3 |
| Blog/Web | Hero-изображение | 1600×900 | Соотношение 16:9 |
| Open Graph | Превью для соцсетей | 1200×630 | Стандарт OG |

### 7.7 SEO-фреймворк контента

#### Иерархия таргетинга ключевых слов

```
Primary keyword (1): 
  → Include in: title, first paragraph, 1–2 H2 headings, meta description, URL slug
  → Density: 1–2%

Secondary keywords (3–5):
  → Include in: H2/H3 headings, body paragraphs
  → Density: 0.5–1%

LSI keywords (10–15):
  → Include naturally throughout content
  → Don't force — use semantic variations
```

#### Чек-лист On-Page SEO

- [ ] Title: Основное ключевое слово ближе к началу, до 60 символов, кликабельный
- [ ] URL slug: Короткий, на основе ключевого слова, дефисы, не подчёркивания
- [ ] Meta description: Основное ключевое слово, 150–160 символов, включает CTA
- [ ] H1: Только один, совпадает или близко отражает title
- [ ] H2–H6: Логичная иерархия, вторичные ключевые слова естественно вплетены
- [ ] Первые 100 слов: Основное ключевое слово появляется в первом абзаце
- [ ] Alt-текст изображений: Описательный, включает ключевое слово где естественно
- [ ] Внутренние ссылки: 2–4 ссылки на релевантные страницы того же домена
- [ ] Внешние ссылки: 1–2 ссылки на авторитетные источники
- [ ] Уровень читабельности: Flesch-Kincaid Grade 7–9 для большинства B2C; выше для B2B/технического

### 7.8 Шаблон пресс-релиза

```
FOR IMMEDIATE RELEASE
[OR: EMBARGOED UNTIL: DATE/TIME]

[COMPANY NAME] [ANNOUNCES/LAUNCHES/PARTNERS/ACHIEVES] [SPECIFIC THING]
[Subtitle: Supporting detail or secondary benefit]

[CITY, STATE] — [Month Day, Year] — [Company name], [brief company description], today announced [specific news]. [One sentence expanding on the news and its significance].

"[Quote from senior executive — forward-looking, human, and substantive]," said [Full Name], [Title], [Company]. "[Second sentence of quote that adds emotional or strategic color]."

[Paragraph 2: Expanded context — why this matters, what problem it solves, market context]

[Paragraph 3: Product/program/partnership details — specifics, features, availability, pricing if relevant]

[Optional Paragraph 4: Supporting quote from partner, customer, or investor]

[Paragraph 5: Availability and next steps — when, where, how to access, pricing]

###

About [Company Name]
[2–3 sentence boilerplate: what the company does, founded when, key customers/metrics]

Media Contact:
[Name]
[Title]
[Email]
[Phone]
[Website]
```

---

## Раздел 8: Контент-календарь и планирование

**Объединённый источник:** Content Calendar Template (alirezarezvani) + Content Planning Frameworks

### 8.1 Стратегия столпов контента (правило 40/25/25/10)

```
Pillar 1: Educational (40%)
  Formats: How-to guides, tutorials, explainers, tips & tricks, data analysis
  Goal: Establish authority; drive SEO traffic; build trust

Pillar 2: Inspirational (25%)
  Formats: Success stories, case studies, transformations, vision pieces, behind the brand
  Goal: Build aspiration; create emotional connection; show what's possible

Pillar 3: Conversational (25%)
  Formats: Behind-the-scenes, team spotlights, Q&As, polls, questions, hot takes
  Goal: Build community; increase engagement; humanize the brand

Pillar 4: Promotional (10%)
  Formats: Product announcements, offers, event invites, features highlights, CTAs
  Goal: Convert interest to action; drive revenue; announce news
```

**Почему это соотношение работает:** Аудитория подписывается на бренды ради ценности, не ради рекламы. Соотношение 40/25/25/10 гарантирует, что на аккаунт сначала стоит подписаться — а затем промо-контент попадает в восприимчивую аудиторию.

### 8.2 Фреймворк месячного планирования

#### Настройка месяца (сделайте это первым)

```markdown
## [Month] [Year] Content Plan

### Monthly Goals
- Traffic target: 
- Lead generation target: 
- Engagement target: 
- Subscribers/followers target: 
- Key campaign/theme: 

### Key Dates This Month
- Product launch: 
- Industry event: 
- Holiday/awareness day: 
- Content deadline: 

### Monthly Theme
[One unifying topic or narrative thread that ties the month together]

### Primary Content Asset
[The one big piece — long-form blog, video, webinar, guide — that other content repurposes from]
```

#### Шаблон недельного распределения

```
Week 1: Foundation
  Monday — Blog post (primary keyword: [X])
  Tuesday — LinkedIn insight post
  Wednesday — Email newsletter
  Thursday — Twitter/X thread
  Friday — Instagram carousel

Week 2: Inspiration
  Monday — Case study or success story
  Tuesday — LinkedIn thought leadership
  Wednesday — Product highlight or promo
  Thursday — Community question or poll
  Friday — Behind-the-scenes content

Week 3: Education
  Monday — Tutorial or how-to (video or blog)
  Wednesday — Infographic or data visual
  Friday — Q&A or myth-busting post

Week 4: Conversion
  Monday — In-depth guide or whitepaper tease
  Wednesday — Testimonial or case study
  Friday — Newsletter recap + CTA
```

### 8.3 Полный шаблон месячного контент-календаря

```markdown
# Content Calendar — [Month Year]

## Monthly Goals
- **Traffic Goal**: 
- **Lead Generation Goal**: 
- **Engagement Goal**: 
- **Key Campaign**: 

---

## Week 1: [Date Range]

### Monday [Date]
**Platform**: Blog  
**Topic**:   
**Primary Keyword**:   
**Secondary Keywords**:   
**Target Length**:   
**Status**: [ ] Planned [ ] Written [ ] Reviewed [ ] Published  
**Owner**:   
**Notes**:   

**Platform**: LinkedIn  
**Type**: Article Share / Original Post  
**Caption snippet**:   
**Hashtags**:   
**Optimal Post Time**: 9:00 AM  

### Tuesday [Date]
**Platform**: Instagram  
**Type**: [ ] Single image  [ ] Carousel  [ ] Reel  
**Topic**:   
**Visual brief**:   
**Caption**:   
**Hashtags**:   
**Optimal Post Time**: 11:00 AM  
**Visuals status**: [ ] Briefed [ ] Created [ ] Approved  

### Wednesday [Date]
**Platform**: Email Newsletter  
**Subject line (A)**:   
**Subject line (B)**:   
**Preview text**:   
**Audience segment**:   
**Primary CTA**:   
**Status**: [ ] Drafted [ ] Designed [ ] Tested [ ] Scheduled  

### Thursday [Date]
**Platform**: Twitter/X  
**Type**: [ ] Single tweet [ ] Thread  
**Topic**:   
**Thread length (if thread)**:   
**Media**: [ ] Images [ ] GIFs [ ] Video [ ] None  
**Optimal Post Time**: 12:00 PM  

### Friday [Date]
**Platform**: Multi-channel
**Campaign**:   
**Assets needed**:
- [ ] Blog post
- [ ] Social graphics
- [ ] Email
- [ ] Video  

---

## Week 2: [Date Range]
[Repeat structure]

## Week 3: [Date Range]
[Repeat structure]

## Week 4: [Date Range]
[Repeat structure]

---

## Content Bank (Ideas for Future)
1. 
2. 
3. 
4. 
5. 

---

## Performance Review (End of Month)

### Top Performing Content
1. **Title/Topic**:  
   **Platform**:  
   **Key metric**:  
   **Why it worked**:  

2. **Title/Topic**:  
   **Platform**:  
   **Key metric**:  
   **Why it worked**:  

### Underperforming Content
1. **Title/Topic**:  
   **Why it underperformed**:  
   **Adjustment for next month**:  

### Lessons Learned
- 
- 
- 

### Adjustments for Next Month
- 
- 
- 

## Resource Links
- Brand Guidelines: [Link]
- Asset Library: [Link]
- Analytics Dashboard: [Link]
- Team Calendar: [Link]
```

### 8.4 Справка по времени публикации для конкретных платформ

| Платформа | Лучшие дни | Лучшее время | Заметки |
|---|---|---|---|
| LinkedIn | Вт–Чт | 8–10:00, 12–14:00 | Избегайте выходных; правило рабочих часов |
| Instagram | Пн, Ср, Пт | 11:00–13:00 | Пик Ср 11:00; 19:00–21:00 для лайфстайла |
| Twitter/X | Будни | 9:00–15:00 | Обеденный час (12:00–13:00) — пик для B2C |
| Facebook | Ср–Пт | 13:00–16:00 | Органический охват низкий; бустите важные посты |
| TikTok | Любой | 19:00–21:00 по местному времени | Вечерняя аудитория самая большая |
| YouTube | Пт–Вс | 14:00–16:00 | Подписчиков уведомляют; пики в воскресенье днём |
| Email | Вт–Чт | 10:00–14:00 | Вторник 10:00 исторически высший open rate |
| Pinterest | Сб–Вс | 20:00–23:00 | Поведение просмотра вдохновения по выходным |

*Всё время указано в местном часовом поясе аудитории, не отправителя.*

### 8.5 Матрица репурпозинга контента

Один элемент основного контента → множество ассетов:

| Основной ассет | Репурпозится в |
|---|---|
| Длинный пост в блог (2 000+ слов) | 5 постов LinkedIn (по одному на секцию), 1 тред Twitter, 1 email-рассылка, 3 карусели Instagram, 1 сценарий видео YouTube |
| Эпизод подкаста (30–60 мин) | Аудиограм-клипы (3×), цитата-графика (5×), пост-транскрипт в блог, тред Twitter (топ-инсайты), статья LinkedIn |
| Кейс | Пост LinkedIn, карусель Instagram, слайд для sales-дека, фича в блог, сценарий видео-отзыва |
| Отчёт с данными/исследованием | Инфографика, 10 соцпостов по точкам данных, пресс-релиз, план вебинара, email-серия прогрева |
| Вебинар/видео | Пост-резюме в блог, клипы-хайлайты (3–5×), транскрипт, серия email-фоллоуапов, слайд-дек |
| Туториал/how-to | Короткое видео (TikTok/Reel), тред Twitter (шаги), пин Pinterest, email-микрокурс |

### 8.6 Воркфлоу генерации идей контента (усиленный Perplexity)

Используйте возможности живого исследования Perplexity Computer для ведомой трендами генерации идей:

```
Step 1: Trend Discovery
  → search_web for "[industry] trends [current month/year]"
  → search_social for "#[industry] OR [topic]" (recent posts only)
  → Look for: high engagement posts, recurring questions, emerging terminology

Step 2: Competitive Content Audit
  → fetch_url on 3–5 competitor blog/social pages
  → Identify: their top-performing content types, topics they haven't covered, angles they miss

Step 3: Keyword Opportunity Research
  → search_web for "[topic] frequently asked questions"
  → search_web for "how to [topic] site:reddit.com OR site:quora.com"
  → Extract: recurring pain points = content opportunities

Step 4: Brief Creation
  → For each content idea, complete the Content Brief Template (Section 8.7)

Step 5: Batch Scheduling
  → Fill the monthly calendar template
  → Assign to content pillars (40/25/25/10)
  → Assign to platforms with platform-specific notes
```

### 8.7 Шаблон контент-брифа

```markdown
## Content Brief

**Title (working):** 
**Content type:** [ ] Blog [ ] Social [ ] Email [ ] Video [ ] Podcast [ ] Infographic
**Platform(s):** 
**Pillar:** [ ] Educational (40%) [ ] Inspirational (25%) [ ] Conversational (25%) [ ] Promotional (10%)
**Publish date:** 
**Author/Owner:** 

**Objective:**
What should the audience feel, know, or do after consuming this piece?

**Target audience:**
Which persona is this primarily for? What stage of awareness are they at?

**Primary keyword (if SEO):**
**Secondary keywords:**

**Hook/angle:**
What is the surprising, specific, or counterintuitive angle that makes this piece worth reading?

**Key points to cover:**
1. 
2. 
3. 

**Key points to avoid:**
(What competing content covers that we want to differentiate from)

**Call to action:**
What is the single action the reader should take?

**Visual requirements:**
- Feature image: [ ] AI generated [ ] Stock [ ] Custom design
- In-article visuals: 
- Social cut-down assets needed: 

**Sources/references to include:**

**Internal links (2–4):**

**Word count target:**
**Deadline:**
```

---

## Раздел 9: Промпт-инжиниринг для креативной работы

**Объединённые источники:** Prompt Engineer Toolkit (alirezarezvani/marketing-skill) + Senior Prompt Engineer (alirezarezvani/engineering-team)

### 9.1 Гид по выбору техники

| Ситуация | Техника | Почему |
|---|---|---|
| Чёткая, простая, хорошо определённая задача | **Zero-shot** | Быстрее всего; работает хорошо, когда формат однозначен |
| Сложная задача, требующая консистентного формата | **Few-shot** | Примеры закрепляют стиль вывода модели |
| Многошаговое рассуждение, логика, диагностика | **Chain-of-Thought (CoT)** | Явные пошаговые рассуждения снижают ошибки |
| Открытая задача с множеством путей | **Tree-of-Thought (ToT)** | Принуждает к исследованию до фиксации |
| Интеграция с API, downstream-обработка | **Structured Output (JSON)** | Гарантирует парсимые ответы |
| Постоянная персона, правила, ограничения | **System Prompt Design** | Отделяет статичные инструкции от динамического ввода |
| Улучшение самих промптов | **Meta-Prompting** | Превращает модель в оптимизатор промптов |

### 9.2 Специфичные для креатива шаблоны промптов

#### Промпты генерации изображений

**Фотореалистичный продукт:**
```
Professional product photography of [product description], [surface/setting], 
[composition: centered/rule-of-thirds/dramatic angle], 
[color palette: warm/cool/neutral/specific tones], 
[lighting: soft natural/dramatic studio/backlit/golden hour], 
no text, no watermarks, high resolution
```

**Портрет/лайфстайл:**
```
[Style: photorealistic/editorial/cinematic] portrait/photo of [subject description], 
[environment and context], [pose or activity], 
[lighting quality and direction], [color mood: warm/cool/desaturated], 
[aspect ratio use case — e.g., "suitable for Instagram portrait format"]
```

**Иллюстрация:**
```
[Art style: flat vector/line art/watercolor/gouache/digital painting/risograph] 
illustration of [subject], [composition notes], 
[color palette: limit to 3–5 colors, e.g., "dusty rose, sage green, off-white, and charcoal"], 
[mood: playful/minimal/bold/organic], [intended use: app icon/blog header/print]
```

**Абстракция/художественный:**
```
[Medium: oil painting/acrylic/pastel/mixed media/CGI] 
[style reference: impressionist/bauhaus/surrealist/contemporary], 
[subject or concept expressed abstractly], 
[palette], [compositional quality: layered/sparse/chaotic/geometric], 
[lighting and texture notes], no text
```

**Бренд-ассет:**
```
Brand illustration for [company type/industry], 
[visual metaphor for the brand value: e.g., "growth represented as a seedling becoming a tree"], 
[brand colors: hex codes], [style: clean geometric/organic/bold typographic], 
suitable for [use: website hero/social media/print], no text overlay
```

#### Промпты генерации видео

**Витрина продукта:**
```
[Camera: slow push-in/dolly/orbit/static] of [product], 
[setting and surface], [key visual action or detail], 
[visual style: cinematic CGI/lifestyle/documentary/abstract], 
[lighting: dramatic/natural/artificial], 
[color grade: warm/cold/neutral/film emulation], 
no text, seamless loop if possible
```

**История/нарратив:**
```
[Shot type: wide establishing/medium/close-up/POV] showing [character/subject] 
[action and emotion] in [setting], [time of day and lighting], 
[visual aesthetic: handheld documentary/smooth gimbal/fixed frame], 
[color palette and mood], [optional: ambient sound description]
```

**Абстракция/моушн-графика:**
```
Abstract [material/concept: liquid metal/fluid simulation/particle field/geometry] 
[motion description: morphing/flowing/exploding/crystallizing], 
[color palette], [lighting: dramatic/soft/neon/natural], 
[loop quality: seamless loop], [style: CGI/hand-drawn/kinetic typography]
```

#### Промпты для голоса и аудио

**Бриф сценария диктора/озвучки:**
```
Write a [duration: 30-second/60-second/2-minute] voiceover script for [brand/product].
Tone: [tone attributes from brand voice framework]
Audience: [persona]
Key message: [single most important point]
CTA: [specific action]
Avoid: [anything to omit: technical jargon, competitor comparisons, etc.]
Voice style: [warm and conversational / authoritative and confident / playful and energetic]
```

**Бриф диалога подкаста:**
```
Write a [duration] podcast segment between HOST and GUEST discussing [topic].
HOST voice: [characteristics — curious, challenging, accessible]
GUEST voice: [characteristics — expert, specific, story-driven]
The conversation should cover:
1. [Opening question/topic]
2. [Main insight or debate point]
3. [Practical takeaway for the listener]
Avoid: [lecture format, excessive agreement, abstract answers without examples]
End with a [teaser for next episode / book recommendation / listener question prompt]
```

#### Промпты бренд-копирайтинга

**Заголовок главной страницы:**
```
Write 5 homepage headline options for [company name], a [type of business] 
that helps [target audience] achieve [outcome] without [pain point/obstacle].
Brand archetype: [archetype from Section 3.2]
Tone: [tone attributes]
Format: Each option should be under 10 words, benefit-led, and memorable.
Include one question-format option and one contrarian option.
```

**Пост в соцсети:**
```
Write a [platform: LinkedIn/Twitter/Instagram] post for [brand name] about [topic].
Brand voice: [archetype + 3 tone attributes]
Angle: [specific hook type from Section 7.2: contrarian/story/list/question]
Length: [platform-appropriate: e.g., "LinkedIn: 150–200 words"]
CTA: [desired action]
Do not: [anything to avoid]
```

**Тема email:**
```
Write 10 email subject line options for [campaign/email purpose].
Audience: [persona and their current state of awareness]
Email goal: [open rate optimization / click optimization]
Include:
- 3 curiosity-gap options
- 3 specificity/number options
- 2 urgency/scarcity options
- 2 personalization options
Keep each under 50 characters for mobile optimization.
```

### 9.3 Методология оптимизации промптов

#### Фреймворк A/B-скоринга (5 измерений)

Оцените каждую версию промпта по шкале 1–5 по:

| Измерение | Что оценивать |
|---|---|
| **Coherence** (Связность) | Вывод логичен, хорошо структурирован, внутренне консистентен |
| **Accuracy** (Точность) | Фактически верен / уместен задаче / без галлюцинаций |
| **Format compliance** (Соответствие формату) | Точно соответствует запрошенному формату |
| **Conciseness** (Лаконичность) | Нет воды, нет избыточности, эффективная подача |
| **Usefulness** (Полезность) | Человек стал бы действовать на основе этого вывода или использовать его |

**Порог:** Стремитесь к ≥4.0 по всем измерениям, прежде чем считать промпт готовым к продакшну.

#### Паттерны сокращения токенов

```python
# BEFORE: Verbose (312 tokens)
"""
You are a highly experienced and skilled assistant who specializes in sentiment analysis.
Your job is to carefully read the text that the user provides to you and then thoughtfully
determine whether the overall sentiment expressed in that text is positive, negative, or neutral.
Please make sure to only respond with one of these three labels and nothing else.
"""

# AFTER: Lean (28 tokens — same quality)
"""Classify sentiment as POSITIVE, NEGATIVE, or NEUTRAL. Reply with label only."""

# Savings at scale: 284 tokens × rate = significant cost reduction at volume
```

**Принципы сокращения токенов:**
1. Убирайте описания роли, не добавляющие ограничений («You are a highly experienced...»)
2. Заменяйте многословные инструкции прямыми командами
3. Переносите примеры в few-shot формат вместо их описания
4. Устраняйте избыточные перефразирования («Your job is to... please make sure to...»)

#### Контроль версий промптов

```markdown
# CHANGELOG.md

## [v1.3.0] — [Date]
### Changed
- Added explicit JSON schema to extraction prompt (fixes null-field regression)
- Reduced system prompt from 450 to 280 tokens (18% cost reduction)
### Fixed
- Sentiment prompt now handles mixed-language input correctly
### Regression: PASS (14/14 cases)

## [v1.2.0] — [Date]
...
```

**Структура файлов:**
```
prompts/
├── CHANGELOG.md
├── production/       ← What's running in prod
├── staging/          ← Candidates under testing
├── archive/          ← Old versions (never delete)
├── tests/
│   ├── regression.json
│   └── edge_cases.json
└── results/
    └── ab_test_[date].json
```

### 9.4 Распространённые ловушки промпт-инжиниринга

| Ловушка | Описание | Исправление |
|---|---|---|
| **Хрупкость промпта** | Работает на тест-кейсах; ломается на крайних случаях | Всегда тестируйте с пустым вводом, очень длинным вводом, юникодом, инъекцией кода |
| **Конфликты инструкций** | «Be concise» + «be thorough» в одном промпте | Разрешите противоречия; приоритизируйте одно ограничение |
| **Неявные допущения о формате** | Модель угадывает формат | Всегда указывайте формат явно |
| **Пропуск регрессионных тестов** | Каждая правка промпта рискует сломать прежние кейсы | Постройте регрессионный набор до любых изменений |
| **Оптимизация не той метрики** | Низкая стоимость токенов важна меньше высокой точности для высоких ставок | Сопоставляйте цель оптимизации со ставками задачи |
| **Раздувание системного промпта** | Промпты на 2 000 токенов, которые могли бы быть на 200 | Тестируйте более лёгкие версии — качество часто держится |
| **Промпты под конкретную модель** | Промпт, настроенный под GPT-4, деградирует на Claude и наоборот | Тестируйте кросс-модельно перед деплоем |

### 9.5 Библиотека креативных шаблонов промптов (10 шаблонов)

```
1. VISUAL BRIEF → AI IMAGE PROMPT
Convert this creative brief to an optimized image prompt:
Brief: {{brief}}
Style: {{style_reference}}
Restrictions: {{what_to_avoid}}
Output a single, detailed prompt optimized for photorealistic AI image generation.

2. SCRIPT → VOICEOVER DIRECTION
Convert this script to voice direction for TTS:
Script: {{script}}
Target emotion: {{emotion}}
Pace: {{pace: slow/medium/fast}}
Emphasis points: {{where_to_stress}}
Output: Annotated script with [PAUSE] markers and [EMPH:word] emphasis tags.

3. BRIEF → VIDEO STORYBOARD
Create a 5-shot video storyboard from this brief:
Brief: {{brief}}
Duration: {{total_seconds}}
Style: {{visual_reference}}
For each shot: describe the camera angle, action, lighting, and a ready-to-use video generation prompt.

4. TOPIC → HEADLINE OPTIONS
Generate 10 headline variations for: {{topic}}
Audience: {{audience}}
Tone: {{tone_attributes}}
Include: question format, contrarian format, number list format, how-to format, and specificity format.

5. CONTENT → REPURPOSING PLAN
This is a {{content_type}} about {{topic}}:
{{content}}
Generate a repurposing plan producing 8 derivative assets for different platforms.
For each asset: platform, format, key angle, draft content.

6. BRAND → VOICE SAMPLE
Apply this brand voice to the following draft:
Brand: {{archetype}} archetype, {{tone_attributes}} tone, {{formality}} formality level
Draft: {{draft}}
Rewrite it to fully embody the brand voice. Preserve all factual content.

7. DATA → VISUAL CONTENT BRIEF
Convert this data into a visual content plan:
Data: {{data_points}}
Target platform: {{platform}}
Create: (a) key insight headline, (b) infographic outline, (c) 3 social post angles using the data.

8. PERSONA → CONTENT IDEAS
For the following audience persona:
{{persona_description}}
Generate 15 content ideas across:
- 5 educational topics they'd search for
- 5 aspirational topics they'd engage with
- 5 conversational topics they'd respond to

9. COMPETITOR ANALYSIS → CONTENT GAPS
Here are topics covered by our top 3 competitors:
{{competitor_content_list}}
Here are topics we've covered:
{{our_content_list}}
Identify: (a) topics they cover we don't, (b) angles they miss, (c) 10 content opportunities to differentiate.

10. PERFORMANCE DATA → CONTENT STRATEGY
Here is our content performance data for the last 90 days:
{{performance_data}}
Analyze: (a) patterns in top performers, (b) common traits of underperformers,
(c) 5 strategic recommendations for next quarter's content mix.
```

---

## Раздел 10: Уникальные возможности Perplexity Computer

Эти возможности нативны для Perplexity Computer и не могут быть воспроизведены одним лишь промпт-инжинирингом или исполнением кода.

### 10.1 Генерация видео ИИ

**Что делает:** Генерирует настоящие MP4-видеоклипы моделями Sora 2, Sora 2 Pro, Veo 3.1 и Veo 3.1 Fast.

**Когда использовать:**
- Бренд-видео, витрины продуктов, контент для соцсетей
- Визуальные демонстрации, когда скриншотов/изображений недостаточно
- Абстрактная моушн-графика для презентаций или сайтов
- Более длинные нарративы, собранные из нескольких клипов

**Параметры:**
- `model`: sora_2 (по умолчанию), sora_2_pro, veo_3_1, veo_3_1_fast
- `duration_seconds`: 4, 8, 12 (Sora); 4, 6, 8 (Veo)
- `aspect_ratio`: 16:9 или 9:16
- `image_path`: Опциональный стартовый кадр для img2video

**Референс воркфлоу:** Раздел 5.4 (Генерация видео ИИ)

### 10.2 Генерация изображений ИИ

**Что делает:** Генерирует настоящие PNG-изображения моделями nano_banana_2 и nano_banana_pro.

**Когда использовать:**
- Заголовки блогов и featured-изображения
- Визуалы для соцсетей
- Бренд-иллюстрации и графика
- Мокапы продуктов и лайфстайл-имиджи
- Версии существующих изображений с переносом стиля (img2img)

**Параметры:**
- `model`: nano_banana_2 (по умолчанию), nano_banana_pro
- `aspect_ratio`: 1:1, 16:9, 9:16, 4:3, 3:4
- `images`: До 10 референсных изображений для img2img
- `prompt`: Детальное описание (см. Раздел 2.3)

**Не для:** Диаграмм, графиков, таймлайнов, инфографики с конкретными данными — модель нагаллюцинирует неверные значения.

### 10.3 Текст-в-речь и производство голоса

**Что делает:** Преобразует текст в естественно звучащее речевое аудио моделями Gemini 2.5 Pro TTS и ElevenLabs TTS v3.

**Когда использовать:**
- Озвучка для видеоконтента
- Производство подкастов
- Аудио-версии письменного контента
- Демо продуктов с дикторским текстом
- Производство многоголосого диалога

**Ключевой дифференциатор:** Многоголосый JSON-формат позволяет полноценное производство подкаста/диалога с 2+ различными голосами без какого-либо записывающего оборудования.

**Референс воркфлоу:** Раздел 6 (Аудио и речь)

### 10.4 Транскрипция аудио

**Что делает:** Транскрибирует аудио- и видеофайлы с диаризацией спикеров, пословными тайм-кодами и поддержкой 99 языков.

**Когда использовать:**
- Транскрипция интервью, подкастов и встреч
- Создание искомого текста из аудиоконтента
- Репурпозинг видеоконтента в письменные ассеты
- Генерация субтитров

**Ключевой дифференциатор:** Диаризация спикеров до 32 спикеров делает её жизнеспособной для больших встреч и панельных дискуссий.

### 10.5 Развёртывание живых сайтов

**Что делает:** Строит и разворачивает сайты, веб-приложения и веб-игры, доступные по публичному URL.

**Когда использовать:**
- Лендинги кампаний
- Интерактивные инструменты или калькуляторы
- Портфолио или витринные сайты
- Страницы событий
- Прототипы продуктов

**Ключевой дифференциатор:** В отличие от локальных HTML-артефактов, сайты, развёрнутые Perplexity Computer, публично доступны по реальному URL — ими можно делиться с кем угодно, не требуя от получателя запускать код.

**Референс воркфлоу:** Раздел 4 (Frontend-дизайн и веб-артефакты)

### 10.6 Исследование трендов в соцсетях

**Что делает:** Ищет в X/Twitter в реальном времени с продвинутыми операторами для обнаружения трендов, мониторинга конкурентов и исследования аудитории.

**Когда использовать:**
- Генерация идей контента: обнаружить, какие темы набирают обороты
- Мониторинг конкурентов: отслеживать, что постят конкуренты и как реагирует аудитория
- Слушание бренда: находить упоминания, реакции и настроение
- Пайплайн «тренд → контент»: выявить трендовую тему → создать релевантный контент → опубликовать до пика тренда

**Доступные операторы:**
```
#hashtag      — posts containing hashtag
@username     — posts mentioning user
from:user     — posts from specific user
to:user       — replies to specific user
is:retweet    — include retweets
-is:retweet   — exclude retweets
is:reply      — include replies
is:quote      — include quote tweets
```

**Воркфлоу генерации идей контента:**
```
1. search_social for "#[industry] -is:retweet" (recent, original posts)
2. Identify posts with high engagement or recurring themes
3. Note language patterns audiences use (use their words, not yours)
4. Find topics competitors haven't addressed yet
5. Create content that enters the existing conversation
```

### 10.7 400+ интеграций с приложениями

**Что делает:** Подключается к внешним сервисам для дистрибуции контента, обновления CRM, сбора аналитики и автоматизации воркфлоу.

**Релевантные интеграции для работы с контентом:**
- **Email-платформы** (Gmail, Outlook): Распространять рассылки, отслеживать открытия
- **Соцпланировщики** (Buffer, Hootsuite): Планировать посты по платформам
- **CMS-платформы** (WordPress, Webflow, Notion): Публиковать контент напрямую
- **Аналитика** (Google Analytics, Mixpanel): Вытягивать данные о производительности
- **Дизайн-инструменты** (Canva, Figma — через API): Получать или обновлять ассеты
- **CRM-системы** (Salesforce, HubSpot): Сегментировать контент по стадии клиента

**Воркфлоу автоматизации дистрибуции контента:**
```
1. Write content → 2. Generate visuals → 3. Post to primary platform
→ 4. Schedule repurposed versions for other platforms
→ 5. Add to email newsletter queue
→ 6. Update CRM with content touchpoint
→ 7. Schedule performance review at D+7 and D+30
```

### 10.8 Мониторинг контента по расписанию

**Что делает:** Запускает задачи по расписанию — ежедневно, еженедельно или с кастомными интервалами.

**Применения для контента:**
- Еженедельные отчёты о производительности: вытянуть данные аналитики → суммировать в email
- Мониторинг трендов: ежедневный соцпоиск упоминаний бренда или контента конкурентов
- Алерты о пробелах в контенте: еженедельная проверка, опубликовали ли конкуренты на приоритетные темы
- Напоминания календаря: помечать предстоящие даты публикации, требующие создания ассетов
- Отслеживание SEO-позиций: периодический мониторинг позиций ключевых слов

### 10.9 Стек креативного производства Perplexity Computer

Полный воркфлоу креативного производства, уникальный для Perplexity Computer:

```
RESEARCH
  ↓ search_web (trend research, keyword discovery)
  ↓ search_social (social listening, competitor content audit)
  ↓ fetch_url (read competitor pages, gather references)

PLANNING
  ↓ Create content brief (Section 8.7)
  ↓ Fill content calendar (Section 8.3)
  ↓ Build storyboard for video/audio (Section 5.5)

CREATION
  ↓ Write copy (Section 7 frameworks)
  ↓ generate_image (Section 2.3) — blog headers, social visuals
  ↓ generate_video (Section 5.4) — video content
  ↓ text_to_speech (Section 6.1) — voiceovers, podcasts
  ↓ Build web experience (Section 4) — landing pages, microsites

DISTRIBUTION
  ↓ call_external_tool (social schedulers, email platforms, CMS)
  ↓ Deploy live website via sandbox

MONITORING
  ↓ Scheduled performance tracking
  ↓ search_social for brand/content mentions
  ↓ Performance review → next cycle input
```

---

## Быстрая справка: деревья решений

### «Какой креативный инструмент мне нужен?»

```
Making a static image?
  → Already have a reference to transform? → generate_image with images=[ref] (img2img)
  → Need photorealistic AI image? → generate_image (nano_banana_2)
  → Need programmatic design (poster, PDF)? → Canvas Design workflow (Python)
  → Need generative/algorithmic art? → Algorithmic Art workflow (p5.js)

Making a video?
  → Short clip (4–12 sec)? → generate_video (sora_2)
  → Long-form video? → Multiple clips → stitch with ffmpeg
  → Animated GIF for Slack? → Slack GIF Creator (PIL)
  → CSS animation for web? → Frontend Design workflow

Making audio?
  → Voiceover (single voice)? → text_to_speech (.txt file)
  → Podcast/dialogue (2 voices)? → text_to_speech (.json file, 2 speakers)
  → Complex production (3+ voices)? → text_to_speech (ElevenLabs) or .json with 3+ speakers
  → Transcribing audio? → transcribe_audio

Making web content?
  → Simple HTML experience? → Plain HTML/CSS/JS
  → Component-rich app? → React + shadcn/ui (Web Artifacts Builder)
  → Live public website? → website-building skill + sandbox deployment

Writing copy?
  → Blog post? → Section 7.3 templates
  → Social media? → Section 7.4 templates
  → Email? → Section 7.5 templates
  → Brand voice? → Section 3 (Voice framework)
  → SEO content? → Section 7.7 (SEO framework)
```

### «Что мне нужно построить первым?»

```
New brand from scratch?
  → Section 3.9 (Brand Identity Brief) → Section 3.2 (Archetype) → Section 3.3–3.5 (Voice)

Content strategy?
  → Section 8.1 (Pillar strategy) → Section 8.2 (Monthly framework) → Section 8.3 (Calendar)

Single piece of content?
  → Section 7.1 (Master workflow) → Section 7.3–7.5 (Templates)

Creative production?
  → Section 2.5 (Creative brief) → Choose modality → Execute
```

---

## Приложение: справка по зависимостям

### Python-библиотеки (Canvas Design, генеративное искусство, создание GIF)

```bash
# Canvas/PDF design
pip install reportlab matplotlib pillow

# Algorithmic art (runs in HTML via p5.js CDN — no Python install needed)

# GIF creation
pip install pillow imageio numpy

# Audio post-processing
# Use ffmpeg (pre-installed in Perplexity Computer workspace)
```

### Зависимости JavaScript / CDN

```html
<!-- p5.js for generative art -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.0/p5.min.js"></script>

<!-- React for web artifacts -->
<!-- Handled automatically by Web Artifacts Builder scripts -->

<!-- Motion for React animations -->
<!-- npm install framer-motion -->
```

### Шрифты

**Программный дизайн (Canvas Design):**
- Шрифты хранятся в каталоге `./canvas-fonts` внутри скилла
- Скачивайте с Google Fonts или системные шрифты для программного использования

**Веб (Frontend Design):**
- Импортируйте через CDN Google Fonts в `<head>`
- Предпочтительны для онлайн-использования: Google Fonts, Adobe Fonts, Font Share

**TTS:**
- Нет зависимостей от шрифтов — голос определяется выбором модели и параметра голоса

---

*Content & Creative Super-Skill v1.0 — Merged from 14 source skills across anthropics/skills, alirezarezvani/claude-skills, and Perplexity Computer built-in capabilities.*
