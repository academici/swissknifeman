# Changelog

## [Unreleased]

### Added (детерминированная привязка скиллов к агентам)

- **Поле `skills:` во frontmatter агентов бакетов** (`skills/<bucket>/agents/*.md`) —
  нативный preload Claude Code (v2.0.43+): полный контент перечисленных скиллов
  инжектится в субагента на старте, без надежды на model-invocation. Привязаны
  `php/laravel-implementer`, `laravel-reviewer`, `laravel-test-writer`. Закрывает
  корень сбоя «агент проигнорировал скилл» (6/7 пропустили `repositories`).
- **Валидация (`scripts/validate.sh`, 10c):** каждый `skills:`-элемент агента обязан
  резолвиться в реальный скилл реестра (`bucket:name`); ненеймспейснутый — warning.
- **`php/laravel-implementer`:** прозовый «ПЕРВЫЙ ШАГ — load via Skill» заменён на
  декларативное поле `skills:`; жёсткие правила оставлены L4-страховкой.

### Added (гейт принуждения + Observer — план agent-skill-binding, Stage B–D)

- **`harness` review-gate** — детерминированный гейт архитектуры на `SubagentStop`
  (`off|warn|strict`, дефолт `warn`): прогоняет настроенную проектом проверку
  (`check_command`), `warn` → подсказка в `additionalContext`, `strict` → блок
  субагента. Без проверки — no-op. L5-рубеж под `skills:`-preload. (Stage B)
- **`system/session-observer`** (skiller, ЭКСПЕРИМЕНТАЛЬНО, per-project toggle
  `.claude/observer.env.ini`) — пост-фактум разбор сессии по JSONL-логам с
  3-осевой аналитикой слабых мест: **агенты** (skill-skip/drift/циклы), **скиллы**
  (gap/thin/dead/correction-after-load), **настройки** (хуки/права). Находки →
  learnings через memory-хук, промоция человеком; замкнутый цикл самопочинки.
  Сниппет `analyze-session.md` (jq/grep-рецепты). Read-only по коду, не live. (Stage C–D)

### Changed (валидация: строгий frontmatter + битые ссылки)

- **`validate.sh` ужесточён** (секция 1a) — раньше проверялось только *наличие*
  обязательных полей; теперь:
  - `risk` ∈ {read, draft, write, external}; `adapters` ⊆ {claude, cursor, fable};
  - `version` — semver (`\d+.\d+.\d+`); frontmatter `bucket` == каталог бакета (для локальных);
  - объявленные в frontmatter `snippets:` обязаны существовать на диске;
  - **внутрискилловые ссылки** `snippets/…` / `references/…` в теле SKILL.md обязаны
    резолвиться (битая ссылка → error).
- Намеренно НЕ проверяем: равенство frontmatter `snippets:` ↔ `index.json` (принятая
  конвенция — index.json самодостаточен, frontmatter-список опционален; 34 скилла),
  и общие `../`/`.agents`-ссылки (раскладка проекта-потребителя у upstream/imported —
  ложные срабатывания). Все новые проверки дают 0 нарушений на текущем реестре.

### Changed (core: дедупликация + защищённый subprocess)

- **`parse_flags`/`parse_args` сведены в `core/cli.py`** — раньше `parse_flags`
  дублировался в skiller и harness байт-в-байт, `parse_args` (надмножество с
  позиционными) жил в maind. Теперь один источник истины, пакеты реэкспортируют из
  своих `common.py` (импорты `from .common import parse_flags|parse_args` не тронуты).
- **`core.cli.run_cmd`** — защищённый запуск подпроцесса (argv-список, без shell):
  `FileNotFoundError`/`TimeoutExpired`/ненулевой код → чистый `die` вместо
  трейсбэка. Применён к `registry`/`hub` (вызовы `generate-*.sh` с `check=True`
  больше не падают трейсбэком).
- **`core.io.safe_load_json`** — единый graceful-ридер JSON (битый/отсутствующий →
  default, опц. `on_error`). Для БД с бэкапом битого файла остаётся доменный
  `maind.common.load_json_db`.
- **Сплит `maind/common.py`**: HTTP-клиент (`http_get_json`/`http_post_json`/`ping`)
  → `maind/http.py`, управляемый markdown-блок (`managed_block`/`upsert_block`/
  `content_hash`) → `maind/blocks.py`. Реэкспорт из `common.py` — импорты
  `from .common import ...` не тронуты (non-breaking).
- Аудит subprocess-вызовов: остальные уже защищены (`shutil.which`-гварды,
  `try/except OSError`, health-poll демона памяти с детектом раннего выхода) —
  не трогали (рекомендация аудита про `shlex.quote` оказалась ложной: argv-списки
  не инъектируемы шеллом).
- **Тесты:** core 12→28 (parse_flags/parse_args/run_cmd/safe_load_json), harness
  14→28 (новое покрытие `doctor`/`settings`/`cli`-диспетчер).

### Added (скиллы дисциплины именования)

- **`general/naming-conventions`** (бакет `general` — CORE-connect, авто-раздаётся в каждый
  проект) — язык-агностичные правила: имя раскрывает намерение, борьба с шумовыми словами
  (`Manager`/`Helper`/`data`/`process`) и комбинаторным взрывом методов (`findByX…OrFail`/
  `…OrNull`). Сниппет `naming-gallery.md` (плохо → хорошо).
- **`php/naming-conventions`** (бакет `php`) — Laravel-конкретика: именование Action/Repository/
  DTO/VO/Enum/Event/Job, таблиц/колонок, разбор анти-паттерна `findByCodeOrFail`-взрыва
  (→ route binding / model scopes по намерению / критерий / один канонический `findByIdOrFail`).
  Сниппеты `naming-antipatterns.php`, `repository-method-naming.php`. Перекрёстные ссылки в
  `repositories`, `code-style-spatie`, `named-arguments`; уточнён чеклист `repositories`
  (единственный канонический lookup, не плодить метод-на-поле).
- Имя `naming-conventions` намеренно живёт в двух бакетах (`general` + `php`): legal под
  plugin-namespaces (connect), в vendor-режиме flat-имена разводятся префиксом бакета.

### Changed

- **Бакет `blender` разрезан на два плагина:** `blender` (универсальный bpy+MCP —
  `version-gotchas`, `mcp-blender`) и `blender-modeling` (параметрический CAD под
  FDM/SLA — `parametric-config`, `threading`, `model-rules`, `config-conventions`,
  `scene-conventions`, `build-loop`). Раньше один бакет смешивал универсальный
  Blender, методологию CAD и приватный workflow проекта DiaBox; диабокс-специфика
  (слой C) вырезана из плагина. Имена деталей в скиллах обезличены
  (`lens/glass/rocket → part/insert/model`). `blender-modeling` зависит от `blender`
  (`mcp-blender` от B не зависит); потребителям модельных скиллов подключать оба плагина.

### Added (agent-framework — каркас агент-практик + continuous-audit)

- **Документация каркаса агентов** (`docs/skiller/agent-framework/`): обзор,
  `framework-overview` (текущее состояние — вход аудита), `decisions-ledger`
  (принято/отклонено + проверенные факты Claude Code), `roles`,
  `skills-index-and-hub`, `post-integration-checklist`. Стойка: **данные + скилл,
  не движок-генератор**.
- **Переиспользуемый аудит-промт** `docs/skiller/workflows/framework-audit.md` —
  периодическая ревизия каркаса через Perplexity (вход: overview + ledger; выход:
  строгие дельта-таблицы); самоякорящаяся петля, не перепредлагает готовое.
- **Архив аудитов** `docs/skiller/audits/` (raw verbatim + триаж двух прогонов
  2026-06-23: universal-framework, agent-teams+ponytail) + ledger
  `references/framework-audits.md`. Sidebar обновлён (standalone + агрегат).

### Changed (hub — видимость агентов и скиллов, Фаза 1)

- **`generate-hub.sh`**: в хаб добавлен срез **«Агенты проекта»** (таблица из
  `.claude/agents/*.md`: роль → назначение → преднагруженные `skills:`) — роли и их
  скиллы теперь видны оркестратору. Каждое имя в `skills:` сверяется с реестром;
  неизвестное помечается `⚠` (preload молча no-op) + WARNING в stderr. Добавлен
  **freshness-штамп** `<!-- swissknifeman:registry sha=… skills=N -->` для сверки
  дрейфа «реестр изменился — хаб не перегенерён» (doctor — Фаза 5). Парс блок-списка
  `skills:` — инлайн в скрипте; общий хелпер в common.py придёт с валидатором (Фаза 3).

### Added (agent-packs — версионируемая pack-система, Фаза 2)

- **Скилл `system/agent-packs`** — playbook установки и версионного апгрейда паков в
  проект-потребитель: детект стека → интервью → рендер+копия → lock; upgrade по
  CHANGELOG-дельте с 3-way reasoning через sha256 в lock (без diff-движка). Стойка:
  агент-driven, не движок-генератор.
- **Пак `backend-laravel` v0.1.0** (`harness/configs/claude-code/agent-packs/`):
  агенты slice-builder/test-writer/reviewer + workflow dev-loop + review-gate хук +
  settings-фрагмент + guideline; обобщены плейсхолдерами (`{{PACK_PREFIX}}`,
  `{{PHP_RUNNER}}`, `{{TEST_RUNNER_CMD}}`, `{{TEST_DB}}`, `{{CHECK_CMD}}`,
  `{{PROJECT_DIR}}`). `pack.json` (manifest) + per-pack `CHANGELOG.md` + README паков.
- **Lock-схема** `.claude/agent-pack.lock.json` (версия + ответы интервью + per-file
  `base_sha256` отрендеренного) — основа upgrade без diff-движка.

### Added (Фаза 3 — роли, path-scoped rules, ponytail-дисциплина)

- **Роль `spec-writer`** (опц.) в паке `backend-laravel` — пишет `docs/specs/<feature>.md`
  (tech-spec) на крупные фичи, НЕ глобальный гейт. Path-scoped `rules/{api-controllers,
  migrations,tests}.md` — нативная авто-загрузка `.claude/rules/` по путям; тонкие
  триггеры, ссылаются на скиллы (без дублирования текста).
- **ponytail-дисциплина впитана в `quality/code-simplifier`** (0.2.0→0.3.0): лесенка
  YAGNI до кода (7 ступеней) + delete-list формат (теги `delete:`/`stdlib:`/`native:`/
  `yagni:`/`shrink:`). Внешний плагин ponytail НЕ подключаем (конфликт с boost).
  Reviewer-роль пака ссылается на over-engineering-проход.
- **`.swissknife.json` схема** (`CONFIG_KEYS`): `shape`/`stacks`/`skills_map` — данные
  профиля для универсальности back/front/fullstack (не движок).
- Сверка имён `skills:` у агентов уже покрыта hub-проверкой (Фаза 1) — отдельная
  команда `validate-agents` не понадобилась.

### Added (Фаза 5 — doctor freshness-дрейф)

- **`skiller doctor`** сверяет штамп `swissknifeman:registry sha=…` в хабе каждого
  зарегистрированного проекта с текущим sha реестра → флагит устаревшие хабы («реестр
  изменился — хаб не перегенерён»). Проекты без штампа (старый хаб) пропускаются.
  Замыкает continuous-audit петлю на детект дрейфа.

### Added (Фаза 6 — Agent Teams, опц.)

- **Пресет `settings.agent-teams.json`** (harness) — opt-in включение экспериментальных
  Agent Teams: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` + `teammateMode` (merge-only,
  сосуществует с auto-approve/review-gate). Предпосылка: Claude Code ≥2.1.178; конфиг
  форвард-совместим.
- **Doc `agent-framework/agent-teams`** — когда брать Teams vs субагенты, spawn-шаблоны
  (full-stack фича, параллельный дебаг), module-boundaries (зоны путей под роли, БЕЗ
  file-lock), опц. quality-gate хуки `TeammateIdle`/`TaskCompleted` (переиспользуют
  review-gate). Роли каркаса годятся как teammates. Sidebar обновлён.

## [0.4.0] - 2026-06-22

> **Зонтичная единая версия монорепо.** Накопленное с `v0.3.0`: выделение пакета
> `harness` (окружение Claude Code), корневой управляющий слой `swissknifeman`,
> доки по пакетам + зонтичный агрегат, гранулярная оркестрация окружения и
> standalone-сборка доков пакетов. Тег `vX.Y.Z` — единый маркер всего репозитория;
> версии плагинов Claude Code резолвятся в git SHA и от тега не зависят, per-package
> `plugin.json` (harness 0.1.0 · maind 0.2.1 · skm 0.3.0) — информативны.

### Added (Фаза 3 — гранулярная оркестрация окружения)

- **Capability `env:mcp` / `env:hooks`** в `maind/orchestrate.py` рядом с `env:apply` —
  точечная раскатка MCP-серверов / хуков через пакет `harness` (`maind run <project>
  env:mcp|env:hooks`, router `swissknifeman env mcp|hooks` — полный passthrough в
  harness). Раньше окружение настраивалось только цельным шагом (`skiller integrate`
  или `env:apply` для permissions); теперь «зонтик = единое управление» покрывает и
  MCP/хуки гранулярно. Whitelist `CAPABILITIES` расширен, тесты orchestrate дополнены
  (sibling=harness, подкоманда, `{path}`-подстановка).

### Changed (Фаза 3 — standalone-сборка доков пакетов)

- **Доки skiller/harness собираются и standalone, и в агрегате** (как уже умеет
  maind). У каждого пакета — своя `docs/.vitepress/config.mts` (base `/skiller/`,
  `/harness/`); зонтичный `scripts/docs-sync.sh` по-прежнему отбрасывает per-package
  `.vitepress` и собирает единый сайт. Внутренние ссылки доков переведены на
  **относительные** (`./`, `../`, без `/skiller/`·`/harness/`-префикса) — один
  источник валиден в обеих сборках; кросс-пакетные ссылки skiller→harness/`/routing`
  резолвятся только в агрегате и в standalone помечены `ignoreDeadLinks`. `harness`
  получил `package.json` (docs-скрипты), skiller — `docs:standalone:*`. Проверено:
  агрегат + оба standalone-сайта собираются без dead links.

### Changed (docs: maind влит в единый сайт)

- **maind-доки вошли в зонтичный VitePress** — `scripts/docs-sync.sh` теперь
  агрегирует и `packages/maind/docs`; в меню «Память и граф» ведёт внутрь сайта
  (`/maind/…`), не наружу. Внутренние ссылки maind-доков переведены с абсолютных
  (база `/maind/`) на **относительные** — пакет собирается и standalone (свой
  `.vitepress`), и в агрегате (общая база `/swissknifeman/`). Единый сайт зелёный
  (`vitepress build`, без dead links); standalone-сборка maind тоже зелёная.

### Added (корневой управляющий слой `swissknifeman`)

- **`bin/swissknifeman`** — тонкий router + setup-фасад над тремя пакетами (зонтик =
  единое управление, пакеты = возможности): `swissknifeman skills|env|maind …` →
  skiller/harness/maind; `swissknifeman setup <project>` → `maind onboard` (полный
  онбординг: скиллы+окружение+память+граф); `swissknifeman doctor` → fan-out трёх.
  Логику не реализует — делегирует; цепочка онбординга одна (`maind/onboard.py`).
- **Back-compat алиаса**: исторические `swissknifeman <cmd>` (connect/vendor/integrate/
  update/sync/lock/status/list/registry/topology/validate/version) router проксирует в
  `skiller` — онбордженные проекты и привычка не ломаются.
- **Владение алиасом перешло зонтику**: `swissknifeman`→`bin/swissknifeman` ставит
  зонтичный `install.sh` ПОСЛЕ пакетов; из `packages/skiller/install.sh` установка
  алиаса убрана (иначе re-run skiller install затирал бы router). Standalone-skiller
  без зонтика — только `skiller` (алиаса нет).
- **maind**: capability `env:apply` (sibling `harness`) — прямое применение окружения
  (`maind run <p> env:apply`, router `swissknifeman env`); `onboard --skip-skills` теперь
  всё равно настраивает окружение через harness (раньше оно шло только внутри
  `skiller integrate`).

### Added (пакет `harness` — настройка окружения Claude Code)

- **Новый пакет `packages/harness`** (CLI `harness`): настройка харнеса Claude Code —
  пресеты permissions, режимы auto-approve/bypass, MCP-серверы, хуки (memory/notify/log).
  Выделен из `skiller`, потому что к управлению скиллами не относится. `git mv`
  `configs/claude-code/` и `scripts/apply-permissions.sh` из skiller → harness (история
  сохранена). Команды: `harness permissions|mcp|hooks|doctor`. Пакет stateless
  (пишет в `.claude/` целей и `~/.claude/hooks/`); зонтичный `install.sh` ставит
  `skiller · harness · maind`.
- **skiller делегирует окружение в harness через subprocess** (как maind → skiller):
  `apply_permissions` и env-блоки `integrate` (permissions/MCP/auto-approve/memory)
  зовут `harness …`; резолв лаунчера — `SKM_HARNESS_BIN` →
  `<монорепо>/packages/harness/bin/harness`. Сигнатура `apply_permissions` не менялась —
  `connect`/`vendor` не трогались; harness не установлен → graceful skip (как раньше при
  отсутствии скрипта). Политика выбора MCP (`_default_mcp`/dev-гейт) осталась в integrate.
- **marketplace: поле провенанса `package`** у каждой записи плагина (`skiller`/`harness`/
  `maind`) — `skiller registry` проставляет автоматически; harness подхватывается как
  соседний пакет (плагин `harness@swissknifeman`, только команды `/harness:*`). Имена
  плагинов и имя marketplace НЕ менялись (back-compat: `<plugin>@swissknifeman`).
- **PR-шаблон** переписан под монорепо (затронутые пакеты skiller/harness/maind/core,
  per-package validate, regenerate-marketplace, docs). Память хуков делит state со skiller
  (`~/.swissknifeman/`) — пути в установленных хуках не менялись.

### Changed (модель имён и топология MCP)

- **Пакет `packages/swissknifeman` → `packages/skiller`** (CLI `skiller`). Репо/зонтик остаётся
  `swissknifeman` (= контейнер-«швейцарский нож»); имя пакета теперь явно про управление СКИЛЛАМИ
  и не путается с репозиторием. `git mv` каталога + `lib/swissknifeman`→`lib/skiller` (импорты
  пакета относительные — менялись только absolute-импорты в `tests/`) + `bin/swissknifeman`→
  `bin/skiller` (`python3 -m skiller`). `install.sh` ставит `skiller` **и back-compat алиас
  `swissknifeman`** в PATH — доки/привычка/онбордженные проекты не ломаются. **НЕ менялись**
  (бренд зонтика): имя marketplace `swissknifeman`, state-каталог `~/.swissknifeman/`,
  `.swissknifeman-manifest.json`, `.swissknife.json`, репо-URL; `skm`-плагин и `/skm:*`.
  `orchestrate.py` (maind): путь sibling-лаунчера → `packages/skiller/bin/skiller`.
- **Плагин `maind` → только команды (`/maind:*`), без MCP-сервера.** Снято поле `mcpServers`
  из `plugin.json`, удалён `packages/maind/.mcp.json` (сервер `maind-hub --scope global`). Раньше
  user-global плагин тащил `maind-hub` в КАЖДУЮ сессию поверх per-project сервера `maind` — две
  одинаковые `maind`-строки в `/mcp` с разными scope (промах «пишем в global вместо project»).
  Теперь MCP-инструменты хаба даёт только per-project сервер `maind` из `.mcp.json` проекта;
  граф/`projects_*`/`links` scope-независимы, ecosystem-факт пишется явным `scope:"global"`.
- **maind MCP: дефолт-scope из cwd, а не глухой `global`.** При запуске без `--scope`/`MAIND_SCOPE`
  сервер определяет `project:<id>` по текущему каталогу (резолвер общий с `health --cwd`), падая
  в `global` только вне известного проекта — argless-сервер пишет в бакет своего проекта.
- **Дедуп включения плагина в `~/.claude/settings.json`** (user-config): снят дубль
  `maind@academici` (+ stale marketplace `academici`, указывавший на pre-monorepo standalone-клон);
  оставлен единый `maind@swissknifeman`.
- **Решение: maind остаётся единым** (память+граф связаны namespace-моделью; memory `agentmemory`
  и graphify уже отдельные MCP-серверы — дробить нечего). Зафиксировано в CLAUDE.md.

### Added

- **Аудит практик round-2 + 4 дельты реестра скиллов.** Продолжение
  `docs/research/practices-audit-2026-06.md` — новый док `practices-audit-2026-06-r2.md`
  (карта покрыто/частично/гэп/отклонено + бэклог, Dart отложен как 1 проект). Заавторены:
  - **NEW `php/enum-state-machine`** — граф переходов доменного статуса единым источником
    (`transitionDefinitions()` на enum) + рантайм-реестр (`allowedFrom`/`canTransition`) +
    исполнение перехода в Action под `DB::transaction()` с событием `ShouldDispatchAfterCommit`.
    Гэп: `enum-attributes` исключает state-machine, `ticket-workflow` проектно-специфичен.
  - **EXTEND `devops/ci-cd` 0.3.0 → 0.4.0** — coverage-gate отдельным CI-job (GitHub Actions
    + GitLab `.php-base`/`php-coverage`); парсер/конфиг переиспользованы из `php/laravel-testing`,
    не дублируются. Сниппет `github-actions-coverage-gate.yml`.
  - **EXTEND `quality/test-strategy` 0.1.0 → 0.2.0** — композиция именованных тест-сюитов
    (Arch/Unit/Feature/Context) + архитектурные тесты Pest Arch. Сниппеты `pest-arch-test.php`,
    `phpunit-testsuites.xml`.
  - **EXTEND `php/spatie-settings` 0.1.0 → 0.2.0** — паттерн «рантайм-инфраконфиг (websocket/
    Reverb) из админки → во фронт публичным DTO», граница секретов.

### Changed

- **Конфиг узла: `.maind.json` → `config.json` в корне монорепо (общий).** Конфиг переехал
  из пакета в корень монорепо и переименован (шаблон — `config.example.json`). Резолвер
  `Env.default_config` ищет `config.json` вверх по дереву (до каталога с `packages/`), с
  обратной совместимостью на legacy `.maind.json`. Добавлена лёгкая обёртка `Config`
  (подкласс dict: `Config.load(env)`/`.save(env)`/`.projects`/`.project(id)` — единая точка
  логики конфига; старый доступ `cfg["projects"]` сохранён). `config.json` — gitignored,
  `0600`. Резолв brain в оркестрации сделан консистентным с синком (через
  `integrations.brain.path` → vault → дефолт `~/Vaults/Brain`, нормализация к каталогу) —
  `maind run brain:*` работает без записи проекта brain. Документация и сообщения обновлены.

- **Плагин maind 0.2.0 → 0.2.1.** Bump версии, чтобы Claude Code перекэшировал плагин со
  свежим кодом (исправленный `.mcp.json` → `maind` из PATH, `from core`); кэш по прежней
  версии не перестраивался. `package.json` синхронизирован.

### Removed

- **Убрана консоль-обёртка `bin/academici`.** Зонтичный роутер `academici maind/skm <cmd>`
  удалён — остаются два независимых CLI в PATH (`swissknifeman`, `maind`). Зонтичный
  `install.sh` теперь только делегирует установку пакетным `install.sh`; CLAUDE.md/README
  описывают два CLI без обёртки. (Имя экосистемы «academici» как бренд сохранено.)

### Changed

- **Общий core: `academici_core` → пакет `core`.** Убрано слово `academici` из путей/имён.
  Каталог `core/` сам стал python-пакетом (`core/__init__.py`, `core/env.py`, …); импорт
  `from core import ...`. PYTHONPATH теперь указывает на корень монорепо (где лежит `core/`),
  а не на сам `core/` — обновлены лаунчеры, `test.sh`, `validate.sh` обоих пакетов и
  real-spawn тест maind (`CORE_DIR` → `MONOREPO_ROOT`).

### Fixed

- **Валидный формат `plugin.json` для установки из marketplace.** Текущий Claude Code
  ужесточил схему — старый формат не ставился (`commands: Invalid input,
  mcpServers: Invalid input`): `commands` теперь массив путей (`["./commands"]`),
  `mcpServers` — путь с `./` (`"./.mcp.json"`). Битый YAML-frontmatter команд (`description`
  с двоеточием `academici: …` парсился как вложенный ключ) обёрнут в кавычки. Затронуты оба
  командных плагина (maind, skm) — проходят `claude plugin validate`. Тест `test_plugin.py`
  ловит эти дефекты до установки.

### Changed

- **Монорепо academici: верификация + массовый re-deploy потребителей (этап 7).** MCP-конфиги
  проектов перенацелены на новый путь хаба: `maind deploy` прогнан по 15 проектам реестра —
  14 обновлены (corex/azguard/edufy/memster/vintera/… → `packages/swissknifeman/packages/maind/`),
  1 пропущен (agelto: предсуществующий битый `.cursor/mcp.json` с дублем JSON — не трогаем).
  `swissknifeman update --all` обновил скиллы потребителей. Проверка `maind health` на проекте:
  статус `connected`. Доделаны хвосты этапа 4: тест `test_plugin.py` и `validate.sh` maind
  больше не требуют собственный marketplace.json пакета (он в корне репо).

### Added

- **Монорепо academici: зонтичная навигация (этап 6).** Корневой `CLAUDE.md` (карта
  монорепо: пакеты, консоль, core, marketplace) и корневой `README.md` зонтика. README
  swissknifeman перенесён в `packages/swissknifeman/README.md`. `docs:*`-скрипты
  swissknifeman нацелены на корневой `docs/` (`../../docs`). docs/ пакетов и два VitePress
  оставлены на местах (полное слияние сайтов — отдельная задача).

- **Монорепо academici: единая консоль `bin/academici` + зонтичный `install.sh` (этап 5).**
  `academici` — тонкий bash-роутер: `academici maind <cmd>` / `academici skm <cmd>` →
  под-бинарник пакета; уникальные команды авто-роутятся без префикса; конфликтные имена
  (`status`/`doctor`) дают сводку по обоим пакетам, `sync` требует домен. Под-бинарники
  `maind`/`swissknifeman` остаются самостоятельными (не ломаем `.mcp.json` и мышечную память).
  Зонтичный `install.sh` ставит `academici` и делегирует установку пакетных CLI их
  собственным `install.sh` (с пакетной пост-настройкой). Все три симлинка указывают в монорепо.

### Changed

- **Монорепо academici: единый marketplace + плагин maind под зонтиком (этап 4).** Корневой
  `.claude-plugin/marketplace.json` теперь объявляет 19 плагинов — 18 swissknifeman
  (бакеты + generate-skill + skm) и `maind` (`source: ./packages/maind`). Генератор
  `registry.py` сканирует соседние пакеты `packages/<name>/.claude-plugin/plugin.json`
  (источник истины — их манифест) и добавляет их в marketplace; `validate.sh` учитывает
  sibling-плагины в match-проверке. Собственный `packages/maind/.claude-plugin/marketplace.json`
  удалён (его роль берёт корневой). Плагин maind (`commands/` + `.mcp.json` с
  `${CLAUDE_PLUGIN_ROOT}`) переносим без правок. Миграция кэша Claude Code
  (`maind@maind` → `maind@swissknifeman`) — вручную в панели `/plugin`.

- **Монорепо academici: общий `core/academici_core` (этап 3).** Дословные дубли,
  исторически копировавшиеся между swissknifeman/maind/brain байт-в-байт, вынесены в
  общий stdlib-only пакет: `die/warn/now_iso/confirm` (`term`), `sanitize` (`text`),
  базовый `BaseEnv` (ядро root/cmd/home + `__post_init__`, `env`). `Env` каждого пакета
  теперь наследует `BaseEnv` и добавляет только свои path-property. Подключение — через
  PYTHONPATH (без pip): лаунчеры, `test.sh`, `validate.sh` добавляют `<repo>/core`
  (опционально — fallback на standalone-раскладку). `parse_args`/`parse_flags`, atomic
  JSON, HTTP, frontmatter, managed-block остаются в `common.py` пакетов (расходятся по
  контракту — не дословны). 5 smoke-тестов core; 113 (skm) + 235 (maind) зелёные.

- **Монорепо academici: maind внесён в `packages/maind/` (через `git subtree`, история
  сохранена).** Хаб памяти/графа теперь живёт под зонтиком рядом с реестром скиллов.
  `node_modules` (демон `@agentmemory/agentmemory`) переустановлен в новом месте (`npm ci`);
  systemd unit `maind-memory.service` перегенерён на новый путь (`maind service install`),
  демон памяти жив (порты 4111/4112). `.maind.json` (конфиг узла, `0600`) перенесён в пакет.
  `orchestrate.py`: путь к лаунчеру swissknifeman обновлён на `packages/swissknifeman/bin/...`
  (local_path остаётся корнем репо). `maind doctor` и 235 тестов зелёные из нового места.
  Re-deploy `.mcp.json` потребителей (≈18 проектов держат старый абсолютный путь) — этап 7.
- **Монорепо academici: переезд в `packages/swissknifeman/`.** Репозиторий становится
  зонтиком экосистемы — содержимое реестра (`lib/`, `bin/`, `skills/`, `skm/`,
  `generate-skill/`, `scripts/`, `configs/`, `buckets.json` …) переехало в
  `packages/swissknifeman/`; в корне остаются зонтичные артефакты (`.claude-plugin/`,
  `docs/`, `README`, `LICENSE`, `CHANGELOG`). Один `marketplace.json` в корне репо теперь
  объявляет плагины с `source: ./packages/swissknifeman/...` (генератор `registry.py`
  разводит корень-пакета vs корень-репо через поиск `.git`; `validate.sh` и
  `generate-graph.sh` адаптированы). `bin/swissknifeman` больше не требует marketplace.json
  в корне пакета. Симлинк переустанавливается `install.sh` из нового пути. Готовит почву
  для пакета `packages/maind/` под тем же зонтиком.

- **Ревью внешнего аудита: дизамбигуация overlap-кластеров + CI security-гейты.**
  По разбору `Audit.md` (вердикт — `docs/research/audit-2026-06-review.md`): из
  всех рекомендаций реальны 3 (остальное — already-done/дубли/вне scope/против
  stdlib-only инварианта). `frontend/vue-composition-api` (0.2.0) обрезан до дельты
  (ref-first + composables), базовый синтаксис отдан upstream `vue`/`vue-best-practices`
  (не удалён — служит якорем «паттерн composable» для ≈13 frontend-скиллов).
  `php/laravel-permissions` (0.3.1) и `frontend/vitest` (0.1.1) — острые
  description-триггеры против путаницы роутинга (vs `azguard`/`attribute-authorization`
  и vs `vitest-vue`). `devops/ci-cd` (0.3.0) — секция «Security gates» (SAST/PHPStan-taint,
  `composer`/`npm audit`+Dependabot, Trivy скан образа) + сниппет `github-actions-security.yml`.
- **Анти-bloat в существующих скиллах (вместо новых дублей).** `anti-drift`
  (0.2.0) — секция «Граница зависимого пакета: спроси перед расширением» +
  обновлён сниппет CLAUDE.md; `code-simplifier` (0.2.0) — чеклист
  speculative-generality (YAGNI) по свежему диффу; `api-design` (0.1.1) —
  cross-ref на эволюцию контракта пакета; внутренний `skill-authoring` —
  стандарт ревью скилла (универсальность, без имён проектов/пакетов).
  `CLAUDE.md`/`CONTRIBUTING.md` — указатели на методологию и анти-bloat гейты.

### Fixed

- **auto-approve: ложные `deny_hard` на `git rm` и `*-init`** — общий токен `rm`
  ловил `git rm` (обратим, файлы в индексе/истории), а токен `init` — `git init`/
  `npm init`/`composer init`/`swissknifeman topology init`. Теперь `analyze.sh`
  маскирует `git rm` перед deny_hard-проверкой (голый `rm`/`xargs rm`/`rm -rf`
  по-прежнему блокируются; `git rm` идёт как мутация — промпт в strict/permissive,
  разрешён в bypass), а `init` убран из общего списка и заменён точечным паттерном
  рантлевела (`telinit`/`init [0-6sS]`). `git rm` добавлен в `deny_block_approve`.
  Файлы хука обновляются `apply-permissions.sh --global` (для `config.json` —
  перезалить вручную, т.к. он не перезатирается)

### Added

- **Каталог интеграций `docs/integrations/` + курированные MCP-пресеты.** По разбору
  внешнего аудита (`CLAUDE_INTEGRATION_TASK.md`): новый раздел VitePress «Интеграции» —
  индекс + 11 страниц (context7, playwright, filesystem, fetch, memory,
  sequential-thinking, github, task-master, spec-kit, claude-code-router), приведённых к
  реальности хаба (remote-HTTP context7, механизм пресет→`integrate`, актуальные пакеты:
  fetch — `uvx mcp-server-fetch`, github — remote `api.githubcopilot.com/mcp/`; без
  устаревших model-id и выдуманных схем). Курированный сабсет пресетов в
  `configs/claude-code/mcp/` (`playwright`/`filesystem`/`fetch`/`memory`/
  `sequential-thinking`/`github`) — **opt-in** через новый флаг `swissknifeman integrate
  --mcp <a,b>` (в интерактиве — отдельный вопрос); `DEV_MCP` по умолчанию не расширен.
  `claude-code-router` — страница «инструмент есть, но под сомнением». **Скиллы из аудита
  сознательно не созданы** (анти-bloat): `playwright-e2e-tester` дублирует
  `quality/playwright-e2e`, `git-flow-ru` — `git-commit-rules`+`github-flow`+`writing-style`,
  а `context7-dart-flutter`/`fintech-api-context`/`pos-fiscal-assistant` нарушают запрет на
  имена конкретных продуктов в теле скилла и попали бы в CORE-бакет `general` — их место в
  `.ai/skills/` конкретных проектов.
- **`integrate`: MCP-серверы в среды разработки (context7).** Новый блок визарда
  `_block_mcp` вливает пресеты MCP-серверов в `<project>/.mcp.json` (merge-only,
  чужие серверы целы, бэкап `*.bak`, `--dry-run`). Пресеты —
  `configs/claude-code/mcp/<name>.json`; первый — `context7` (remote HTTP
  `mcp.context7.com/mcp`, up-to-date docs библиотек). Гейт «среда разработки»:
  раздаётся во всё, кроме `obsidian-vault`. Бандлы `recommended`/`full` включают
  по умолчанию, `minimal` — нет, `custom` — спрашивает.
- **Семантика loop'ов поверх скиллов (без отдельного реестра `loops/`).** По
  аудиту [loops.elorm.xyz](https://loops.elorm.xyz/loops): страница
  `docs/guide/loop-semantics.md` (VitePress, в сайдбаре «Гайд») — модель loop'а
  (Goal/Run mode/Max iterations/Between-check/Exit condition + anti-gaming
  guardrails), маппинг фаз на существующие скиллы и граница «скилл даёт гейты,
  раннер встроен (`/loop`, `/schedule`)». Скилл `task-brief-template` (0.4.0):
  поля `Loop verifier`/`Exit condition`/`Hard stop trigger` в шаблоне + сниппет
  `loop-kickoff.md` (стартовый шаблон итеративной задачи для `.claude/commands/`).
  Сознательно без дублей: iteration/stop уже в `anti-drift`, session-split — в
  `context-economy`, shared-code gate — в `package-contribution-protocol`.
- **`swissknifeman sync` догнал `vendor`/`connect`: манифест, CORE-политика и
  индекс скиллов.** Раньше `sync` только копировал скиллы и писал
  `skills-lock.json` — без `.swissknifeman-manifest.json` (контракт переустановки
  и источник для `generate-hub.sh`), без CORE-скиллов и без обновления
  managed-блока в корне проекта. Теперь `sync`: (1) пишет манифест в `skills_path`
  (`layout: flat`, `flat_name`/`source_path`); (2) раздаёт `CORE_SKILLS` по
  умолчанию и применяет `DEFAULT_EXCLUDE` (флаг `--no-core` отключает), как
  остальные каналы; (3) обновляет индекс скиллов (managed-блок `CLAUDE.md` /
  `.ai/guidelines/swissknifeman-hub.md`), если он уже есть в проекте или передан
  `--hub` (`--no-hub` отключает). `generate-hub.sh` дополнительно ищет манифест в
  `skills_path` из конфига (находит нестандартные раскладки вроде `.agents/skills`).
- **Методология против раздувания кода + скилл `architect/package-contribution-protocol`.**
  По аудиту практик разработки экосистемы «проект ↔ зависимый пакет» добавлен
  generic-гейт против Speculative Generality: главный вопрос (Rule of Three +
  YAGNI), принцип «остановись и спроси / субагент go/no-go перед расширением
  пакета», двухступенчатый gate (proposal → ADR), таблица «что НЕ идёт в пакет»,
  направление зависимостей и SemVer контрактов. Сниппеты: `proposal-issue.md`,
  `adr-template.md`, `claude-md-priority.md` (ручной «первый приоритет» в
  CLAUDE.md потребителя), `permissions-deny.md`. Скилл **opt-in** (бакет
  `architect`), без имён конкретных проектов/пакетов. Базовый рефлекс «спроси
  перед расширением» — в CORE-скилле `anti-drift` (едет во все проекты);
  глубокий протокол подключается выборочно (гибридная раздача).
- **Permissions-пресет `product-boundary`** (`configs/claude-code/settings.product-boundary.json`):
  deny на запись в зависимый пакет (`Write/Edit(vendor/**)`); вариант для
  path-репо (`packages/**`) — в сниппете скилла. Opt-in (не в автодетекте),
  применяется через `apply-permissions.sh --preset product-boundary`.
- **Страница `docs/guide/methodology.md`** (VitePress, в сайдбаре «Гайд») —
  методология анти-bloat с картой «принцип → скилл/конфиг» и гибридной раздачей.
- **Figma MCP-скиллы + новый бакет `mobile`.** Три скилла прокачивают работу
  агента с подключённым Figma Dev Mode MCP: `architect/figma-mcp-core` —
  фреймворк-агностичная дисциплина (реальные инструменты `get_metadata`/
  `get_variable_defs`/`get_code`/`get_code_connect_map`/`get_screenshot`/
  `search_design_system`, запрет извлечения значений из скриншотов,
  selection-driven алгоритм, W3C `tokens.json`, аудит design-system);
  `frontend/figma-to-vue` — маппинг в Vue + Tailwind v4 (`@theme`, cva, `.dark`);
  `mobile/figma-to-flutter` — маппинг в Flutter (`ThemeData`, Row/Column/Expanded,
  Stack/Positioned). Новый бакет `mobile` (Flutter) в `buckets.json`.
- **Vendor-режим `swissknifeman sync` — физический перенос скиллов по единому
  конфигу.** `.swissknifeman/config.json` — источник истины (правила:
  `include` конкретных скиллов + `buckets` целиком − `exclude`); `sync`
  разворачивает их в плоский набор по `skills.json`, копирует файлы в
  `skills_path` (по умолчанию `.claude/skills`) и пишет производный
  `skills-lock.json` с пометкой `managed`. Безопасный prune: удаляются только
  `managed=true` записи, исчезнувшие из конфига — чужой/ручной вендоринг
  (наследие Boost, другой хаб) не трогается. Конфиг распознаётся как маркер
  корня проекта; пример — `.swissknifeman.example/config.json`; доки —
  `docs/guide/vendor-mode.md`. Read-only композитор `lock` остаётся для
  проектов без vendor-режима.
- **Management-плагин `skm@swissknifeman`** — командное лицо CLI: каталог
  `skm/` со статичным `plugin.json` + slash-команды (`skm`, `skills`,
  `integrate`, `status`, `doctor`). Не бакет скиллов — `registry` добавляет
  запись в `marketplace.json` синхронно, `validate.sh` проверяет как обычный
  плагин. Install `skm@swissknifeman` даёт команды управления скиллами проекта.
- **Реализация бэклога аудита — ещё 14 универсальных скиллов + 1 расширение
  (batch-2).** Добиты все отложенные §5 кандидаты из
  `docs/research/practices-audit-2026-06.md`; всё обобщено (проект — только
  эвиденс, в скилл идёт переносимый паттерн + анонимизированные снипеты).
  **Фронтенд (7):** `frontend/reka-ui-cva` (headless-примитивы Reka UI + cva),
  `frontend/dark-mode` (composable light/dark/system, без вспышки, SSR-cookie),
  `frontend/naive-ui-theming` (GlobalThemeOverrides), `frontend/laravel-echo-client`
  (Echo/Reverb composable, X-Socket-ID), `frontend/filepond-upload` (vue-filepond
  + rahulhaque/laravel-filepond), `frontend/vue-dynamic-icons` (динамическая иконка
  по имени), `frontend/pinia-stores` (setup-сторы, композиция). **PHP (4):**
  `php/livewire-blade-attributes` (дельта-гочизы к Boost livewire),
  `php/spatie-settings`, `php/health-checks` (spatie/laravel-health),
  `php/laravel-data` (spatie/laravel-data DTO + `#[TypeScript]`). **Quality (2):**
  `quality/playwright-e2e`, `quality/mutation-testing` (Infection). **Blender (1):**
  `blender/parametric-config` (config-dataclass → profile/check без bpy).
  **Расширен** `php/laravel-testing` (Pest-композиция: трейты + fake/freeze/dataset).
  `skills.json` 138 → 152; Boost-границы соблюдены (complementary: `laravel-data`,
  `spatie-settings`, `livewire-blade-attributes`); `boost-compatibility.md` обновлён;
  `validate.sh` зелёный (0 warnings, 76 tests).
- **Скиллы из практик констелляции (аудит + 10 скиллов, фокус — фронтенд).**
  Read-only аудит всех проектов из `~/Vaults/Brain/.projects.json` + `unbox`,
  `art-kombinat/frontend`, `sova` (6 Explore-агентов, сверка кандидатов с живым
  реестром, чтобы отсечь вендоренные копии). Разбор — в
  `docs/research/practices-audit-2026-06.md` (стек-фингерпринты, поправка
  vendored-vs-local, авторённое, отложенный бэклог, вне охвата). **7 новых
  скиллов:** `frontend/tailwind-conventions` (Tailwind v4: CSS-first `@theme`,
  токены, тёмная тема, `cn()`, prettier-plugin-tailwindcss), `frontend/backend-type-sync`
  (`spatie/laravel-typescript-transformer` + `#[TypeScript]` → `App.Enums.*`/`App.Data.*`,
  в паре с `wayfinder`), `frontend/eslint-flat-config` (ESLint 9 flat для Vue/TS:
  `@stylistic`, границы импортов, цепочка Prettier), `php/test-isolation-guard`
  (bootstrap-страж против тестов по боевой БД/медиа-диску), `php/attribute-authorization`
  (`#[CheckPermission]` + reflection-middleware поверх Gate), `general/writing-style`
  (тон/язык комментариев, коммитов, описаний тестов — расширенная версия, объединена
  с одноимённым скиллом из flexcrm-экстракции ниже), `devops/db-test-preflight`
  (пре-флайт Postgres-БД перед тестами — аналог `node-pnpm-preflight`). **3 расширены:**
  `frontend/inertia-vue` (доменные срезы `features/<домен>/` + границы импортов, →0.3.0),
  `php/enum-attributes` (секция `#[TypeScript]` + экспорт типов, →0.2.0),
  `php/modular-architecture` (реализация на `nwidart/laravel-modules` + Filament discovery, →0.3.0).
  Снипеты анонимизированы; `validate.sh` зелёный (0 warnings).
- **Экстракция универсальных скиллов из flexcrm** (источник: local, авторские):
  `quality/testing-safety-report` (отчёт безопасности после миграций/рефакторинга),
  `php/php-upgrade-checklist` (чеклист апгрейда версии PHP — образ/CI, composer,
  phpstan-baseline, rector, RFC), `general/writing-style` (живой язык комментариев
  и текстов коммитов, дополняет `git-commit-rules`). Boost-владения (tailwind/mcp/
  pest) и уже существующее в реестре не дублировались; `fortify-development` оставлен
  локальным в проекте по решению владельца
- **Док-предупреждение про чистую переустановку** (`docs/guide/cli.md`): `vendor`/
  `update` удаляют ранее вендоренные скиллы, выпавшие из набора реестра, включая
  **незакоммиченные** локальные копии — проектные скиллы держать в git; превью
  удаляемого — `--dry-run`. (Острый угол, всплывший при онбординге flexcrm)
- **Визард интеграции `swissknifeman integrate`** (`lib/swissknifeman/integrate.py`)
  + [чеклист](docs/guide/integration-checklist.md) — единая точка входа: проходит
  чеклист «выбери, что хочешь из максимального функционала» и применяет выбранное,
  переиспользуя `do_connect`/`do_vendor` (скиллы), `apply-permissions.sh` (permissions),
  `generate_hub` (hub) + пишет per-project hook-JSON (auto-approve на PreToolUse
  Bash/ExitPlanMode) и `.swissknife.json:memory_brain` (членство в memory-brain).
  Бандлы `minimal|recommended|full|custom`; безопасно — `--dry-run`, merge-only с
  бэкапами `*.bak`, идемпотентно, пререквизиты (`topology init`, `--global`) только
  с подтверждением. Зарегистрирован в `cli.py`/лаунчере; тесты `tests/test_integrate.py`.
  В `CONFIG_KEYS` добавлены `memory_brain`/`coordinator_ignore` (валидны в `.swissknife.json`)

- **Гибкая «единая память» констелляции** — самодостаточная папка-хук
  `configs/claude-code/hooks/memory/` по образцу auto-approve: переключатель
  `memory.sh` (remember/recall/members/status/sync), режим в `env.ini`
  (`MODE=file|federation|agentmemory|off`), группы и участники в `config.json`,
  бэкенды в `modes/`. **Membership:** общий «мозг» (brain) видят только участники
  из его `members` (резолв узлов/проектов через топологию). Режимы взаимозаменяемы
  (file/federation на markdown без демона; agentmemory — прокси к стороннему
  демону на Brain, деградирует при недоступности), конфиг переопределяется
  per-project (`<project>/.claude/memory.{env.ini,config.json}` + `.swissknife.json:
  memory_brain`). Схема факта совместима с нативной памятью Claude Code, поэтому
  `federation` читает и `~/.claude/projects/<slug>/memory/` участников. Агент-обвязка —
  скилл `system/shared-memory`; установка через `apply-permissions.sh --global`.
  `validate.sh` теперь `bash -n`-ит все хук-скрипты `configs/claude-code/hooks/`
- **Межпроектный координатор кода** — `system/cross-project-coordinator` (скилл) +
  агент `system/agents/code-coordinator` (read-only). Поверх топологии обходит
  связанные проекты, перечисляя только git-отслеживаемые файлы (`git ls-files` —
  уважает `.gitignore`/`.git/info/exclude`, секреты и вендор/генерёжку не читает),
  и ищет по семи критериям: дубли между репо, расходящиеся реализации одного
  концепта, дрейф от реестра скиллов, копия-вместо-зависимости, расхождение
  конвенций/документации/зависимостей. Критерии переиспользуют `quality/`-скиллы
  (tech-debt-audit, refactoring-plan, code-simplifier, code-review). Выдаёт
  приоритизированный (impact×effort) отчёт с `file:line` по проектам и named
  extraction target; правок/PR не делает. `requires: local-topology`
- **Топология локальной среды** — корневой узел системы. Новый бакет `system`
  со скиллом `local-topology` (раздаётся всем проектам: добавлен в профили
  laravel-project/php-package/obsidian-vault), команда `swissknifeman topology
  [init|show]` (`lib/swissknifeman/topology.py`) и глобальный конфиг
  `~/.swissknifeman/topology.json` (version 1): три узла-хаба
  Brain-волт/swissknifeman/база-проектов (роли docs-hub/skills-hub/workspace).
  `init` — интерактивный сбор с авто-детектом дефолтов, атомарная запись с
  бэкапом `.bak`, сохранение `created_at`; предлагается при `install.sh` (TTY).
  Скилл объясняет схему и резолвит узлы по конфигу — любой агент в любом проекте
  видит, где лежат узлы, и доходит до кода/документации соседних проектов.
  Тесты `tests/test_topology.py` (+10). Roadmap: межпроектный агент-оптимизатор
- **Notification-hook `configs/claude-code/hooks/notify/notify.sh`** — ОС-уведомление,
  когда Claude Code ждёт человека: запрос разрешения на инструмент, утверждение
  плана (ExitPlanMode) или простой промпта дольше ~60 сек. Кросс-платформенно
  (Linux `notify-send`, macOS `terminal-notifier`/`osascript`, WSL/Windows toast).
  Регистрируется пресетом `global`, ставится через `apply-permissions.sh --global`,
  никогда не блокирует (`exit 0`)

### Added (продуктовая готовность)

- **`LICENSE` (MIT)** + поле `license` в `package.json` — юридическая основа для
  распространения; внешние (imported) скиллы сохраняют лицензии источников
  (`upstream.json`)
- **`SECURITY.md`** — порядок раскрытия уязвимостей, модель доверия импортируемых
  скиллов (sha256 в `upstream.json`, стратегии `notify`/`replace`), правило
  «нет секретов в snippets», приоритет «проект > источник > реестр»
- **`.github/workflows/test.yml`** — отдельный CI с матрицей Python 3.9–3.12
  (раньше тесты гонялись только хвостом `validate.sh` на одной версии)
- **Покрытие ядра CLI тестами** (38 → 57): `registry` (`build_registry`,
  `write_plugin_manifests`, provenance внешних скиллов, die без `buckets.json`),
  `state` (CRUD `projects.json`, сохранение `first_connected_at`, атомарность),
  `doctor`, `status`, `update` (реплей выбора, идемпотентность) — теперь у каждой
  команды есть прямой тест; хелпер `write_upstream` в `tests/fixtures.py`
- **`docs/guide/troubleshooting.md`** — диагностика (`command not found`, Claude
  Code не видит скиллы, конфликт `settings.json`, коллизии вендоринга, битый
  `projects.json`) и обновление (реестр, vendor `update`/`--all`, смена схемы);
  добавлена в sidebar
- **Бейджи в README** (Tests / Validate / Docs / License) + разделы
  «Безопасность» и «Лицензия»

### Changed (рефакторинг CLI: lib/ + тесты)

- **`bin/swissknifeman` → тонкий лаунчер**: вся Python-логика (раньше — heredoc
  на 1300 строк внутри bash) вынесена в пакет `lib/swissknifeman/` и разложена
  по модулям (`common`, `config`, `state`, `connect`, `vendor`, `update`,
  `status`, `listing`, `registry`, `doctor`, `boost`, `hub`, `cli`). Бинарник
  делает preflight-проверки и `exec python3 -m swissknifeman <root> <cmd>`.
  Поведение байт-в-байт прежнее (`registry` даёт идентичные `skills.json` и
  манифесты); установщик и симлинк не затронуты. Модульные глобали
  `root`/`cmd`/`argv` заменены явным `Env` — функции стали импортируемыми

### Added (тесты CLI)

- **`tests/` (stdlib unittest, без зависимостей)**: 27 юнит-тестов
  (frontmatter, парсинг флагов, sanitize, autodetect, precedence
  `resolve_selection`, транзитивный `requires`, коллизии flat-имён) и
  11 интеграционных — фейковый Laravel-проект в tmpdir, кейсы `connect`/`vendor`
  (autodetect, явные плагины, сохранение `false`, dry-run, bucket/flat-layout,
  pull `requires`, `--exclude`, синк `boost.json`, чистая переустановка).
  Синтетический реестр (`tests/fixtures.py`) — тесты не зависят от контента
  скиллов
- **`scripts/test.sh`** — раннер тестов (`-v` для подробного вывода), встроен в
  `scripts/validate.sh` (группа 12: импорт пакета + прогон сьюта). Тот же
  скрипт гоняет CI

### Added (gh-driven ревью и экономия контекста)

- **`oss-dev/gh-review` (0.1.0)**: ревью и хендофф изменений через GitHub CLI
  с экономией контекста — `gh pr diff/view/comment/review` отдают точечный срез
  (дифф, треды), `gh api .../contents` тянет один файл вместо загрузки целиком.
  Чёткая граница: локальный VCS (commit/branch/diff/log/rebase) — за `git`,
  платформа (PR/issue/release/api) — за `gh`. `requires: context-economy`,
  `produces_for: github-flow`; snippet-шпаргалка команд
- **`scripts/update-upstreams.sh` — канал `gh api`**: для GitHub raw-URL и при
  наличии `gh` файл тянется через `gh api repos/{o}/{r}/contents/{path}?ref=...`
  (авто-аутентификация из `gh auth`, rate-limit, один файл). Тихий откат на
  `urllib`+`GITHUB_TOKEN`, если `gh` недоступен; отключение — `UPSTREAM_NO_GH=1`.
  Касается импортируемых скиллов (`source: github`)

### Changed

- **`general/context-economy` 1.0.0 → 1.1.0**: раздел «Платформенный слой —
  через `gh`, не файлами» (`gh` дополняет `git`, не заменяет; экономия на
  точечном срезе) + пункт чеклиста; ссылка на `oss-dev/gh-review`
- **`oss-dev/github-flow` 0.1.0 → 0.2.0**: шаг Review ссылается на `gh-review`
  (`requires += gh-review`); ревью PR — через `gh`, не загрузкой файлов
- **Документация**: этап «dev-review через gh» в межсистемной цепочке
  (`docs/workflows/index.md`), канал `gh api → urllib` в
  `docs/guide/upstream-sync.md`

### Added (интеграция с Laravel Boost — совместимое ядро)

- **`php/named-arguments` (0.1.0)**: правило обязательных именованных аргументов
  в PHP-вызовах с границами применения и исключениями (один аргумент, встроенные
  функции, splat). Извлечено и де-агельтизировано из проектного скилла;
  `source: local`. Дополняет, а не дублирует — реестр раньше только *использовал*
  именованные аргументы в примерах, отдельного правила не было
- **`php/pennant-development` (0.1.0)**: feature-флаги Laravel Pennant
  (`define`/`active`/`for`-scope, директива `@feature`, активация/раскатки).
  Извлечено из `laravel/boost` (`upstream.json` strategy=notify) — единственный
  чистый static-`.md` generic-кандидат без версионной развилки; Blade-скиллы
  Boost (`folio`/`volt`/`mcp`) остаются за Boost (нужен render-контекст)
- **`php/laravel` → `eloquent-model.md`**: секция «Accessors и mutators» дополнена
  правилами `Attribute::make()` (видимость `protected`, camelCase→snake_case,
  позиция в классе, миграция с legacy-аксессоров) — слито из проектного
  `laravel-attributes` вместо создания дубля

### Added (CLI и хаб — установка в Boost-проекты)

- **Boost-aware `vendor`/`update`**: при наличии `boost.json` в целевом проекте
  CLI (1) автоматически использует **flat-раскладку** `.ai/skills/<name>/SKILL.md`
  — Boost обнаруживает user-скиллы через `glob('.ai/skills/*')` на один уровень,
  bucket-подпапки он бы не нашёл; (2) идемпотентно дозаписывает вендоренные
  скиллы в `boost.json::skills` (по frontmatter-`name`) и подсказывает
  `php artisan boost:update`. Скиллы автоматически расходятся по всем агентам
  Boost из единого источника `.ai/skills/`
- **`generate-hub.sh --root-files A,B`**: managed-блок хаба (между маркерами
  `swissknifeman:hub:start/end`) дополнительно пишется в указанные корневые файлы
  (`AGENTS.md`, `GEMINI.md`, …) для тулз вне Boost; контент вне маркеров не
  трогается

### Fixed

- **Рассинхрон маркера хаба**: `bin/swissknifeman` искал
  `<!-- swissknifeman:hub:begin -->`, тогда как `generate-hub.sh` пишет
  `:start`/`:end`. Из-за этого `hub_artifacts_exist()` не находил managed-блок в
  `CLAUDE.md`, и `update`/повторный `connect` не понимали, что хаб уже стоит.
  Приведено к единому `hub:start`

### Changed (документация концепции ядра)

- **Политика совместимого ядра** зафиксирована явно: `docs/guide/index.md`
  (принцип №6 «Совместимое ядро» + таблица прецедентов), `README.md`,
  `references/laravel-boost.md` (критерий извлечения static/версионность/generic,
  что извлечено, что нет и почему), `docs/guide/installation.md` (раздел
  «Проект с Laravel Boost»). Поток обновлений инвертирован: generic-скиллы
  внешнего источника обновляются сначала в реестре, затем подтягиваются в проекты

### Added (субагенты Laravel)

- **`php/agents/` — первые агент-определения в плагине**: бакет-плагин теперь
  несёт каталог `agents/` (Claude Code обнаруживает его в корне плагина
  автоматически; реестр и валидатор каталоги без SKILL.md игнорируют;
  доступно только в plugin-канале — `vendor` агентов не копирует).
  Агенты: `laravel-reviewer` (read-only ревью свежим контекстом:
  PHPStan/Pint/целевые Pest, Laravel-критерии, структурированные находки без
  правок) и `laravel-test-writer` (Pest-тесты по готовому коду в стиле
  существующих тестов проекта; прикладной код не меняет — расхождения
  репортит)
- **`php/laravel-subagents` (0.1.0)**: протокол оркестрации субагентов на
  крупных Laravel-задачах — порог срабатывания (≥3 слоёв/доменов или целая
  фича; мелкое/среднее — напрямую, явный анти-триггер), исследование через
  Explore-агентов, архитектурный код пишет оркестратор, параллель только для
  независимых подзадач (иначе worktree), `laravel-reviewer` после каждой
  единицы, `laravel-test-writer` по готовому коду, анти-паттерны конвейера
  ролевых агентов

### Added (github-flow)

- **`oss-dev/github-flow` (0.1.0)**: процессная цепочка Issue → Branch → PR →
  Merge → Tag → Release на GitHub — naming Issue/веток/PR, labels, SemVer-оракул
  по типам коммитов, контрольные точки с обязательными вопросами агента;
  PHP/Packagist-гейт в `references/php-package-gate.md`; snippets с шаблонами
  PR/Issue; `requires: git-commit-rules, release-engineering` (формат коммитов
  и changelog/pipeline не дублируются)

### Changed (github-flow)

- **`general/git-commit-rules` 0.1.0 → 0.2.0**: расширен список типов
  (`perf`, `style`, `build`, `ci`, `revert`), раздел «Conventional Commits:
  scopes и breaking changes» (источник scope — commitlint, footer
  `BREAKING CHANGE` / `!` после типа), ссылка на SemVer-оракул github-flow

### Added (CLI swissknifeman + внутренние скиллы)

- **CLI `bin/swissknifeman`**: единая точка входа — `connect` (marketplace
  Claude Code), `vendor` (вендоринг), `update [--all]` (детект каналов по
  маркерам диска, adopt незарегистрированных проектов, починка path-drift
  marketplace при переезде реестра), `status`, `list [--prune]`, `registry`
  (бывший `sync.sh --update-registry`), `validate`, `doctor`, `version`.
  Корень проекта ищется вверх от CWD (`.swissknife.json` → `.claude/` →
  `.git`) — флаг `--target` больше не нужен
- **Карта проектов `~/.swissknifeman/projects.json`** (schema v1, ключ
  path+channel): пополняется автоматически при connect/vendor/update; явный
  выбор (`--profile`/`--plugins`/`--buckets`) воспроизводится при `update`,
  автодетект пере-резолвится с диска; атомарная запись, самовосстановление
  adopt-ом после потери файла
- **Внутренние скиллы `.claude/skills/`** (не экспортируются): полная карта
  пакета (`package-architecture`), процедура авторинга скиллов с проверкой
  пересечений и обязательным upstream.json для внешних (`skill-authoring`),
  дисциплина завершения изменений (`release-discipline`), решение об
  обновлении docs/ после задач (`docs-maintenance`)
- **validate.sh секции 10–11**: мягкий линт внутренних скиллов
  (name+description, kebab-case == каталог, warning при коллизии с реестром);
  `bash -n` всех скриптов + исполняемость CLI
- **`docs/guide/cli.md`**: справочник команд CLI, схема projects.json,
  поиск корня проекта, troubleshooting

### Changed (CLI swissknifeman)

- **`install.sh` перепрофилирован в установщик CLI** (симлинк
  `~/.local/bin/swissknifeman` → `bin/swissknifeman`, идемпотентен,
  PATH-подсказка под шелл); **breaking**: legacy-вендоринг
  `./install.sh <dir> <bucket>` удалён — `swissknifeman vendor`
- `scripts/connect-claude.sh` и `./sync.sh --update-registry` —
  deprecation-wrapper'ы на один релиз, переадресуют в CLI
- `docs/guide/installation.md` переписан под двухшаговую установку
  (CLI один раз → `connect`/`vendor` из проекта); README и остальные
  страницы docs переведены на команды CLI

### Removed (CLI swissknifeman)

- **Brain-sync** (`sync_to_brain`, `BRAIN_PATH`, workflow
  `.github/workflows/sync-to-brain.yml`): зеркалирования в brain больше нет —
  brain подключается как обычный проект
  (`cd <brain> && swissknifeman vendor`, дальше `swissknifeman update`)

### Added (improvement report v2: граф зависимостей + методология)

- **Dependency resolution в install.sh**: frontmatter `requires` разрешается
  транзитивно при выборочной установке (`--buckets`/`--exclude`), в том числе
  кросс-бакетно; `--exclude` побеждает зависимость с предупреждением; дотянутые
  скиллы помечаются в `--list`/`--dry-run` как `(dependency of <skill>)`
- **Валидация графа в validate.sh** (секция 9): существование имён в
  `requires`/`produces_for`, self-reference, циклы по `requires` (DFS);
  warning на не-inline списки
- **`scripts/generate-graph.sh`**: Mermaid-граф зависимостей →
  `docs/guide/graph.md` (subgraph на бакет, только связные узлы, изолированные —
  таблицей); вызывается из `sync.sh --update-registry`; в VitePress подключён
  `vitepress-plugin-mermaid`
- **Реестр skills.json v5**: поля `tags`, `requires`, `produces_for`
  в записях скиллов (опциональны, опускаются если пусты)
- **`general/anti-drift` (0.1.0)**: методология Karpathy (think-before-coding,
  simplicity-first, surgical-changes, goal-driven) + circuit-breaker пороги;
  сниппет-блок для CLAUDE.md целевого проекта
- **`general/spec-interview` (0.1.0)**: grill-me-style интервью перед кодом —
  вопросы по одному, агент сам читает кодовую базу, рекомендованный ответ
  к каждому вопросу; итог — заполненный task-brief-template
- **`general/session-handoff` (0.1.0)**: протокол передачи контекста между
  сессиями/агентами; сниппет handoff-template.md
- **`quality/code-simplifier` (0.1.0)**: упрощение свежего диффа без изменения
  поведения; сниппет GitHub Actions `simplify-on-push.yml`
- **`php/laravel-security-audit` (0.1.0)**: sharp-edges-аудит Laravel
  (raw-запросы, mass assignment, XSS в Blade, CSRF/redirect,
  сериализация/авторизация) с references/ по каждой грани; сниппет
  GitHub Actions `security-audit-scheduled.yml`; requires: static-analysis
- **`docs/workflows/background-agents.md`**: фоновые агенты в CI — шаблоны,
  требования, ограничение стоимости, анти-дрифт правила

### Changed (improvement report v2)

- `general/task-brief-template` 0.2.0 → 0.3.0: секции «Явные предположения»,
  «Out of Scope», «Definition of Done» в шаблоне ТЗ
- `oss-dev/dependency-audit` 0.1.0 → 0.2.0: `references/composer.md` —
  composer-специфика аудита (composer audit/outdated/licenses,
  roave/security-advisories, reproducible installs, composer-грабли, SBOM)
- `php/filament`: `produces_for: [backend-dev, fullstack-dev]` → `[]` — таких
  скиллов не существует (поймано новой валидацией графа)
- `docs/boost-compatibility.md`: ссылка на карточку laravel-boost ведёт на
  GitHub (относительный путь вне docs-корня ломал сборку VitePress)

### Rejected (improvement report v2, по итогам анализа)

- `registry.json` — уже существует как `skills.json` (богаче: sha256,
  provenance, upstream)
- Tier-система (0–4) во фронтматтере — дублирует ось бакеты+профили+requires
- `caveman`-скилл — покрыт `general/compact-responses`
- `composer-audit` как отдельный скилл — расширение `dependency-audit`
- Фоновые workflow в самом реестре — только шаблоны для целевых проектов

### Added (token optimization wave)

- **`php/pao` (1.0.0)**: скилл по laravel/pao — агентно-оптимизированный вывод
  PHPUnit/Pest/PHPStan/Rector/Artisan (~20 токенов JSON вместо тысяч);
  установка, проверка, ограничения
- **`general/context-economy` (1.0.0)**: экономия контекста Claude Code —
  CLAUDE.md ≤200 строк, path-scoped `.claude/rules/` с `paths:`, /compact vs
  /clear, Plan→Clear→Execute, аудит MCP, нативная маршрутизация моделей;
  сниппеты: шаблон правила, команды /prime //plan //execute, чеклист аудита
  CLAUDE.md
- deny-блок «токен-шума» в пресетах `configs/claude-code/settings.laravel.json`
  и `settings.node.json` (`storage/logs`, `node_modules`, `*.lock`, кэши,
  бандлы); `vendor/` сознательно не блокируется — там Boost-гайдлайны

### Changed

- **`php/filament` 0.2.0 → 1.0.0**: переписан с v3 на Filament v5 — структура
  v5-генератора (Schemas/ + Tables/), таблица корректных namespaces
  (`Filament\Actions\*`, `Filament\Schemas\Components\*`), CLI-справочник
  `make:filament-*`, union-типы свойств, типичные ошибки из официальных
  Boost-гайдлайнов; snippets обновлены под v5 + новый
  `forms-tables-reference.md`; upstream.json отслеживает
  filamentphp/filament `boost/guidelines/core.blade.php` (strategy=notify)
- `general/compact-responses` 0.1.0 → 0.2.0: поведенческие шаблоны цикла
  разработки (`✓ tests passed (N)`, только упавший тест при ошибке) и формат
  единственного развёрнутого финального отчёта
- `general/task-brief-template`: раздел Plan→Clear→Execute (план и выполнение —
  раздельные сессии)

### Rejected (по итогам фактчека отчётов Perplexity)

- `.claudeignore` — не существует в Claude Code (рабочий механизм —
  `permissions.deny: Read(...)`)
- `paths:` frontmatter для SKILL.md — `paths:` работает только в
  `.claude/rules/`; скиллы и так загружаются лениво
- claude-code-router — сторонний прокси; нативный `/model` достаточен
- waaseyaa/agent-output как стандарт — перекрывается laravel/pao
- `deny Read(vendor/**)` — ломает чтение Boost-гайдлайнов

## [0.3.0] - 2026-06-11

### Added

- **Нативный plugin marketplace Claude Code**: `.claude-plugin/marketplace.json`
  + `plugin.json` на каждый bucket (генерируются `sync.sh --update-registry`,
  метаданные в `buckets.json`); плагин = bucket, скиллы с неймспейсом
  `<bucket>:<skill>`, версия плагина = git SHA
- **`scripts/connect-claude.sh`**: подключение проекта к marketplace —
  автодетект профиля, идемпотентный merge `extraKnownMarketplaces` +
  `enabledPlugins` в `.claude/settings.local.json`, `--dry-run`/`--list`,
  миграция со старого вендоринга (`--cleanup-vendored` удаляет только
  манифестные копии)
- **`buckets.json`**: description/category/tags на bucket; описания попадают
  в plugin-манифесты и skills.json (registry v4)
- **Схема-валидация `.swissknife.json`** в install.sh и connect-claude.sh:
  неизвестный ключ/тип → ошибка с подсказкой (`did you mean 'buckets'?`)
- **Манифест и коллизии в bucket-режиме install.sh**: `.swissknifeman-manifest.json`
  теперь пишется и в generic/cursor-режиме (чистая переустановка), существующие
  чужие папки — ошибка-коллизия, перезапись только с `--force`
- validate.sh: проверки buckets.json, свежести plugin-манифестов,
  уникальности имён скиллов

### Changed

- `generate-skill/` реструктурирован в layout плагина
  (`generate-skill/generate-skill/SKILL.md`)
- `--agent claude` в install.sh — deprecated (предпочтителен marketplace);
  `.claude-plugin/` исключён из вендоринга и brain-sync
- Документация: адаптер Claude Code переписан вокруг marketplace,
  гайд установки разделён на каналы Claude Code / Cursor-generic
- Ссылки на `references/` в `oss-dev/oss-development` исправлены на
  относительные к скиллу (`../references/...`)

### Added (docs & configs wave)

- **Документация на VitePress** (`docs/`): гайд (принципы, установка, профили,
  анатомия скилла, upstream-sync, реестр, сканер, CI), конфиги, адаптеры,
  примеры, roadmap; деплой на GitHub Pages (`docs.yml`)
- **Пресеты permissions для Claude Code** (`configs/claude-code/`):
  base/laravel/php-package/node/python/docker/yolo +
  `scripts/apply-permissions.sh` (merge в settings.local.json, автодетект стека,
  dry-run, бэкап)
- **Vendor-skills**: универсальный механизм публикации скиллов из Composer-пакета
  потребителю через `vendor:publish` — док-страница + переработанный скилл
  `php/laravel-packages` (v0.3.0) со сниппетом `boost-skill-publisher.php`
- **Спецификация адаптерных дельт**: формат `Override:`/`Additional:`,
  pre-flight хуки, критерии «когда дельта нужна»
- Критерии качества сниппетов для сканера (порог 60/100) в документации
- Roadmap: ближайшие фазы + стратегические/технические/экспериментальные идеи
  (перенесено из tmp-черновиков master-plan v3, черновики удалены)

## [0.2.0] - 2026-06-11

### Added

- **Upstream-sync система**: per-skill `upstream.json` (source, strategy replace/notify,
  sha256, fetched_at), `scripts/update-upstreams.sh` (--check/--apply/--force, exit-коды
  для CI), еженедельный workflow `upstream-sync.yml` с PR-ревью
- `upstream.json` + baseline для всех 12 `skills/imported/*` (get-zeked super-skills)
- **Контекстная установка**: `install.sh` v2 — автодетект типа проекта, `profiles/*.json`
  (obsidian-vault, laravel-project, php-package, standalone), `.swissknife.json` override,
  `--agent claude` с плоской раскладкой под `.claude/skills/` и manifest-cleanup
- **`references/`** — каталог 15 внешних источников с принципом выборочного отбора
- `scripts/validate.sh` — единая валидация (frontmatter, upstream.json, profiles,
  реестр, snippet-манифесты) локально и в CI
- Provenance в `skills.json`: `source: local|github|http`, `upstream`, `fetched_at`
- `.swissknife.example.json`

### Fixed

- `validate.yml`: glob `skills/**` не работал в bash без globstar — CI фактически
  не валидировал скиллы
- `sync.sh`: name/description парсились по всему файлу, а не только из frontmatter
- `skills/pm/prd-from-brd`: отсутствовало поле `version` во frontmatter

## [0.1.0] - 2026-06-11

### Added

- Skills registry v3 with 65 skills across 10 buckets
- Migration of 36 skills from `academici/brain`
- New buckets: devops, php, roles, imported
- 12 perplexity super-skills in `skills/imported/`
- PHP skills: laravel, laravel-permissions (with AzGuard patterns), laravel-testing, laravel-packages, php-patterns, botkit, filament
- DevOps skills: docker (php, vite, postgres, dev-prod), ci-cd, gitops
- Roles: startup-cto, tech-lead, open-source-maintainer, solo-founder
- `install.sh`, `sync.sh`, scanner pipeline
- CI: validate, sha256-update, sync-to-brain, scanner-pr
- Adapters: cursor, claude-code, perplexity
- `generate-skill/` meta-skill
