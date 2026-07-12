# P6.3 — Ревизия бакетов тяжёлых проектов (findings)

Дата: 2026-07-12. Owner в цикле недоступен (фоновый прогон, D17) — применена эвристика
из Code Guidance item'а: сопоставление заявленных бакетов со стеком/темой проекта
(`_comment_stack` в `.swissknifeman/config.json`, `composer.json`/`package.json`), высокая
уверенность → применено сразу; сомнение → не применялось, строка помечена «нужен Owner».

## 0. Главная находка (влияет на P6.4!)

`skiller budget --first-turn` / `maind doctor --context` меряют скиллы через
`resolve_active_set` → `resolve_selection(env, target, config)`, где `config` = **`.swissknife.json`**
(connect-канал). Если файла нет (большинство проекта флота) — код падает на **autodetect
профиля** (`profiles/<type>.json`) и полностью ИГНОРИРУЕТ:
- реальные `enabledPlugins` в `.claude/settings.local.json` (то, что Claude Code факти-
  чески грузит в сессии);
- вендорный `.swissknifeman/config.json` + физические копии в `.claude/skills/` (то, что
  реально читает Claude Code на vendor-проектах: agelto, diabox, azguard, botkit, cms,
  vintera, dterema, dterema-app).

Следствие: для **vendor-проектов** (в т.ч. agelto — флагманский «виновник» из Context
плана) ревизия бакетов через `skiller connect`/`.swissknife.json` теоретически не меняет
измеряемое число вообще — реальный vendor-набор просто не входит в формулу. Число agelto
32830 ток на 86% состоит из CLAUDE.md+rules (15114) и MCP tool-defs (10950); measured
skills — только 5571 ток по autodetect-профилю `laravel-project`, не по 19 бакетам
реального vendor-конфига. **P6.1 baseline и любое будущее P6.4 сравнение для vendor-
проектов измеряют не тот источник** — это предсуществующий разрыв budget.py/skillset.py
(budget.py спроектирован под старый `vendor.py`+`.swissknife.json`, а не под новый
`skillset.py`+`.swissknifeman/config.json`), не введённый этим item'ом и не в его Scope
(правка `budget.py` — код, не ревизия бакетов). **Рекомендация P6.4**: для vendor-
проектов (agelto и др.) использовать `analyst sessions` (реальные транскрипты) как
источник, не `doctor --context`, либо явно исключить их из числового вердикта приёмки
до починки измерения (roadmap-item).

## 1. Механизм применения

Для connect-канала (единственный, где отключение бакета фактически меняет измеряемое
число) отключение `enabledPlugins[bucket@swissknifeman] = false` **не подхватывается**
`_measure_skills`, пока у проекта нет `.swissknife.json` с явным `buckets` — сам
`skiller connect` никогда не переключает `true→false` (merge-only по конструкции,
печатает NOTE «отключите вручную»). Поэтому применение состояло из двух шагов на
затронутых проектах: (1) `enabledPlugins[...] = false` в `.claude/settings.local.json`
(реальный эффект в следующих сессиях), (2) явный `.swissknife.json` с урезанным
`buckets` (закрепляет выбор и делает его видимым `skiller budget --first-turn`/`doctor
--context`, защищает от отката при повторном `skiller connect`).

## 2. Таблица проект/предложено/решение/итог-ток

Легенда решений: **A** = применено (высокая уверенность, D17-эвристика) · **Owner** =
сомнительно, не применено · **—** = проверено, отклонений не найдено.

| Проект | Канал | Предложено к отключению | Решение | Ток до → после (skiller budget --first-turn) | Вердикт до→после |
|:--|:--|:--|:--|--:|:--|
| agelto | vendor | — (все vendor-бакеты соответствуют стеку Filament+Inertia/Vue+Wayfinder) | — | 32830 → 32830 (не измеряется на vendor, см. §0) | WARN→WARN |
| diabox | vendor | — (blender/blender-modeling соответствуют CAD-теме) | — | 12180 → 12180 | WARN→WARN |
| flexcrm | connect | — (azguard-бакет проверен: реально потребляет `axioma-studio/azguard-*` пакеты; general/oss-dev-легаси нет) | — | 29539 → 29539 | WARN→WARN |
| azguard | connect | `oss-dev` (легаси CORE_BUCKETS, дублирует плагин `core`) | A | 14083 → 13504 | WARN→WARN |
| botkit | connect | `oss-dev` (легаси) | A | 12985 → 12406 | WARN→WARN |
| vaulter | connect | `general`, `oss-dev` (легаси) | A | 16346 → 16865 (см. §3: реальный набор включал `architect`, ранее не учитывался autodetect — рост честный) | WARN→WARN |
| swissknifeman | connect | `general`, `oss-dev` (легаси) | A (только enabledPlugins; `.swissknife.json` с пустым `buckets` откатывает на autodetect-fallback = general+oss-dev — не писал, см. §3) | 10590 → 10590 (де-факто не измеряется, реальный эффект в сессии есть) | WARN→WARN |
| corex | connect | `general`, `oss-dev` (легаси) | A | 19771 → 19192 | WARN→WARN |
| memster | connect | `general`, `oss-dev` (легаси) | A | 21867 → 22409 (см. §3: реальный набор включал `frontend`/`frontend-tailwind`/`laravel-filament` — Filament-подтверждено composer.json, рост честный) | WARN→WARN |
| cms | vendor+connect(дрейф) | `oss-dev` (легаси, connect-канал) | A | 24037 → 22966 | WARN→WARN |
| edufy | connect | `general`, `oss-dev` (легаси) | A (профиль laravel-project и так их не включал — число не изменилось, эффект только в реальной сессии) | 21532 → 21532 | WARN→WARN |
| vintera | vendor | — (легаси-бакетов в enabledPlugins нет) | — | 20521 → 20521 | WARN→WARN |
| dterema | vendor | — (легаси-бакетов в enabledPlugins нет) | — | 15371 → 15371 | WARN→WARN |
| dterema-app | vendor+connect(дрейф) | `general`, `oss-dev` (легаси) + `roles` (персоны tech-lead/CTO/founder — нерелевантны Nuxt-пакету) | A | 31348 → 31348 (autodetect-профиль `node-frontend` уже совпал с реальным набором минус легаси — число не изменилось, эффект в реальной сессии) | WARN→WARN |
| sibintek-insiders | connect | `general`, `oss-dev` (легаси); ОБНАРУЖЕНО (не в Scope — недо-поставка, не излишек): реально используются Filament+Inertia+Vue3+azguard-filament (composer.json), но `laravel-filament`/`frontend-vue`/`azguard` НЕ подключены — **Owner**: расширить набор (вне Scope P6.3, только заметка) | A (легаси) | 21906 → 21906 (профиль совпал, реальный эффект в сессии) | WARN→WARN |
| chatom | connect | `oss-dev` (легаси; general уже был false) | A | 23428 → 24309 (см. §3: реальный набор включал `architect`/`laravel-auth`/`laravel-data-layer` сверх профиля php-package — рост честный) | WARN→WARN |
| perplexity-web-mcp | connect | `oss-dev` (легаси) | A | 11981 → 11402 | WARN→WARN |
| loqum | connect | `general`, `oss-dev` (легаси) + `php`, `php-packages`, `frontend-vue`, `frontend-backend` (дрейф: нет PHP и Vue в реальном стеке — TS/Vite демо-клиент без фреймворка, `.swissknife.json` был неактуален) | A | 15774 → 14177 | WARN→WARN |
| brain | connect | `general` (легаси; код-ориентированный бакет — git-commit-rules/naming-conventions/project-map нерелевантны Obsidian-вольту) | A | 17620 → 17972 (см. §3: реальный набор — полный ролевой стек pm/research/founder/roles/axioma/creative/finance/legal/marketing/operator/sales, ранее не учитывался autodetect — рост честный) | WARN→WARN |

## 3. Почему для части проектов число выросло (не регресс)

`_measure_skills` без `.swissknife.json` считает autodetect-профиль (фиксированный список
по типу проекта), который для многих проектов **меньше**, чем реально включённые
`enabledPlugins` (дрейф: кто-то когда-то добавил бакеты сверх профиля флагами). Написав
явный `.swissknife.json` = «реальный набор минус легаси», я одновременно (а) убрал
легаси-бакеты и (б) заставил измерение честно учесть ранее скрытый дрейф. Для vaulter/
memster/chatom/brain это скрытое «сверх профиля» оказалось больше, чем экономия от
легаси-бакетов → итоговое число выросло. Это не регресс от P6.3, а вскрытие
недо-измерения, существовавшего и на момент baseline (P6.1) для этих же проектов.

## 4. Итог по критерию Validation item'а

«вердикт улучшился» (`skiller budget --first-turn`) — **не достигнуто как смена тира**
ни для одного проекта: у всех вердикт остался WARN (доминируют CLAUDE.md/rules и MCP
tool-defs источники, не skills — skills давали 15–20% от total и до, и после). Сырое
число снизилось у 6 проектов (azguard, botkit, corex, cms, perplexity-web-mcp, loqum),
не изменилось у 5 (swissknifeman, edufy, dterema-app, sibintek-insiders — измерение не
чувствительно к сделанному изменению) и честно выросло у 4 (vaulter, memster, chatom,
brain — вскрытый дрейф). Реальный эффект в будущих Claude Code-сессиях (загрузка
`enabledPlugins`) достигнут у ВСЕХ 14 связанных проектов независимо от того, что
показывает `doctor --context`.

## 5. Сомнительные случаи — нужен Owner (не применено)

- **sibintek-insiders**: недо-поставка `laravel-filament`/`frontend-vue`/`azguard`
  относительно реального стека (Filament+Inertia/Vue3+azguard-filament подтверждены
  composer.json/package.json) — вне Scope P6.3 (только удаление, не добавление).
- **agelto**: vendor-бакет `general` (входит в `_comment_exclude`-логику предыдущего
  мейнтейнера частично) — ценность неочевидна, не трогал (vendor-измерение всё равно не
  отражает эффект, см. §0).
- **memster**: базовый бакет `frontend` (не `frontend-tailwind`) при Filament-only
  (без Vue/Inertia) — не однозначно лишний (может содержать framework-агностичные
  скиллы), оставлен.
- **vintera**: legacy-имена бакетов `frontend/*` в `.swissknifeman/config.json`
  (известно с P6.2, вне Scope P6.3).
