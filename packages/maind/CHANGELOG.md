# Changelog

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
версионирование — [SemVer](https://semver.org/lang/ru/).

## [Unreleased]

### Added
- **Роль-паки субагентов (вариант A+C)**: 4 кросс-стек персона-пака в harness
  (`role-tech-lead`/`role-cto`/`role-founder`/`role-maintainer`, `shape:role`, без
  `stack.project_type`/`detect`). Доставка: `project.roles` в `config.json` → карта `role_packs`
  (новый TOP_KEY) маппит роль → пак; `_resolve_agent_pack` (sync.py) добавляет роль-паки
  аддитивно к стековому паку профиля. Роль-скиллы skiller получили `role_agent_pack` во
  frontmatter; тонкий выбор одной роли — через vendor.
- **Дерево решений настройки проекта** — канонический док `docs/guide/onboarding-decision-tree.md`
  (10 слоёв с условными ветками: тип → память → namespaces → канал скиллов → бакеты → окружение →
  граф → agent-packs → brain → эксплуатация). Принцип «оптимально, не максимально; неочевидно — спроси».
- **Distributed-скилл `ecosystem-setup`** — раскатывается в проекты (как `ecosystem-mcp`) через новый
  провиженер `setup-skill` (`skilldoc.apply_setup_skill`, в `sync` ORDER и в `onboard`). Доставляет
  дерево решений тулинга в т.ч. во ВНЕШНИЕ репо, где governance-скиллы maind вне скоупа. Подстановка
  `{{TYPE}}` добавлена.
- `onboard` больше НЕ передаёт `--profile standalone/unknown` в skiller — нераспознанный тип уходит
  в autodetect-fallback (минимум + warn), а не «ставит всё».
- **Доставка субагентов по типу проекта (хаб → проект)**: профиль skiller называет
  `agent_pack` (строка или список — композиция), а `maind onboard`/`maind sync` детерминированно
  раскатывают пак(и) в `.claude/agents/` через `harness agent-packs render --auto` — БЕЗ агента в
  цикле. Новый провиженер `agent-pack` (10-й в `sync` ORDER), capability `env:agent-pack`/
  `env:agent-pack-upgrade` в orchestrate, шаг в onboard. `profile.model_tiers` пре-заполняют
  модельные тиры агентов.
- **Единый детектор типа проекта в `core.project`**: `maind._infer_type` (×2) и
  `skiller.autodetect` сведены к одной таксономии (`core.detect_project_type`); `language_by_type`
  тянется из `core.LANGUAGE_BY_TYPE`. Устранены 3 расходящиеся копии детекта.
- `maind onboard` передаёт `--profile <type>` в `skiller integrate` — выбор скиллов/пресетов/MCP
  идёт по профилю типа, а не только по дефолтам бандла.
- **Авто-загрузка памяти на старте сессии** (`maind memory digest` + SessionStart-хук):
  при `MODE=maind` онбординг ставит `.claude/maind-memory.sh`, который инжектит дайджест
  памяти проекта в контекст Claude Code (`additionalContext`), и **выключает нативную
  авто-память** (`autoMemoryEnabled:false`). Так демон становится единым источником
  контекста — закрывает дыру «у демона нет авто-загрузки, агент должен помнить про recall».
  Дайджест детерминирован (list+фильтр по scope-маркеру, приватный scope первым, свежее
  сверху), хук-безопасен (демон лёг → тихий no-op). Откат на native — `revert_memory_hook`.
- **Гибкий выбор механизма памяти**: `maind onboard --memory maind|native|off` (дефолт
  `maind`; в интерактиве — вопрос чек-листа). `native` возвращает авто-память Claude Code.
  `maind health` проверяет консистентность: `MODE=maind ⇒ native off + digest-инжект на месте`.
- **Провиженер `memory-hook` в `maind sync`** — авто-загрузка памяти теперь докатывается на
  уже подключённые проекты одной командой (`maind sync --all --only memory-hook`), не гоняя
  полный `onboard`. Интент берётся из `.claude/memory.env.ini` (`MODE=maind` → ставит
  digest-инжект + native off; `off` → revert на native; нет конфига → пропуск). Включён в
  дефолтный набор `sync`, идемпотентен (drift по content-hash). Закрывает разрыв: шаблон
  хука уже ссылался на эту команду, но провиженера в `sync` не было.

### Changed
- **Память проекта раскатывается только сервером `maind`** — raw MCP-сервер `agentmemory`
  больше НЕ деплоится и активно УДАЛЯЕТСЯ из `.mcp.json` при `deploy`/`sync` (он писал мимо
  scope-маркера → записи невидимы для scoped-recall, footgun изоляции). Legacy-возврат —
  `maind deploy --with-agentmemory`. Статус проекта (`probe`/`health`) теперь определяется
  наличием сервера `maind`, а не `agentmemory`. `mcpconfig.remove_server` — новый хелпер.

### Docs
- **`guide/memory.md` переписан под правду**: изоляция — на стороне maind (демон —
  единый пул, `namespace`/`sessionId` игнорирует, `type` переопределяет; scope-маркер в
  контенте), единый путь хук+MCP через `MODE=maind`, контракт `forget {memoryId}`, проверка
  round-trip + troubleshooting, снята коллизия имён `federation` (память-файлы vs граф).
  `guide/federation.md` получил врезку «не путать с памятью». Скилл `system/shared-memory`
  → 0.2.0 (канон `MODE=maind`, мульти-namespace, membership по namespaces).

### Added
- **Онбординг авто-проводит память**: `maind onboard` доводит проводку памяти и для уже
  подключённого проекта — задаёт `namespaces` (дефолт «общий `axioma` + свой `<id>`»,
  `--namespace a,b` для нескольких; клиентам — явный список без `axioma`) и пишет
  `<project>/.claude/memory.env.ini` `MODE=maind`. Шаг `memwire` в отчёте.
- **`maind health` — round-trip памяти**: проба write→recall→forget по temp-факту в
  приватном scope + проверка, что хук в режиме `MODE=maind`. Ловит раскол (хук пишет не
  в тот стор), сломанный forget и потерю изоляции. `--strict` падает при провале round-trip.
- **`maind memory remember|recall|forget` (scope-aware CLI)**: единый путь записи/чтения
  памяти для человека И хука. scope считается из конфига проекта через `namespaces.py`
  (`--project`/cwd/`--scope`): `remember` пишет в приватный `project:<id>` (+ `--share`
  в общие `ns:<тег>`); `recall` объединяет приватный + группы + `global` с дедупом.
- **Изоляция памяти НА СТОРОНЕ maind**: agentmemory 0.9.x — единый глобальный пул, поле
  `namespace` он игнорирует, `type` переопределяет (сверено живым `curl`). Поэтому maind
  встраивает scope-маркер `[[s:<scope>]]` в контент при записи и фильтрует результаты по
  нему при чтении (см. `store`/`recall`, `mark_scope`/`split_scope`). Приватность и
  «общее-по-тегу» теперь реально работают; `maind_memory_recall` (MCP) разворачивает
  `project:<id>` в полный набор recall-scope'ов.

### Fixed
- **`maind memory forget`**: payload теперь `{memoryId}` вместо `{namespace, id}` —
  прежний вариант давал `HTTP 400` от agentmemory 0.9.x (сверено живым `curl`), удаление
  не работало. `FakeMemoryServer` в тестах получил `/agentmemory/forget` (по `memoryId`),
  тест `test_memory_forget_deletes_by_id` доказывает round-trip store→recall→forget→gone.

## [0.2.0] — 2026-06-15

### Added
- **Федерация графа**: граф **на проект** (`data/graphs/<id>.db`) + тонкий регенерируемый
  `_index.db` вместо единого `graph.db`. Запрос через границу — federate-on-read (union сторов).
  `graph_store: local` кладёт стор в сам репо проекта.
- **Derive-движок**: граф строится из **источников истины** (`composer.json`/`package.json`,
  Brain frontmatter, `<repo>/.maind.graph.json`, `skills-lock.json`) с пометкой плана (`via`),
  а не из ручного дубля. Команды `graph derive` / `graph rebuild` / `graph --project` / `graph --cross`.
- **Namespaces**: изоляция межпроектных связей по группам (`projects[].namespaces`) — внутри
  группы общее, между группами изолировано; `["*"]` — общая инфраструктура. Применяется и к
  графу (точка создания ребра), и к **памяти** (бакеты `ns:<имя>`).
- **Namespace-паритет памяти**: scope-ярус `ns:<имя>` рядом с `project:<id>`/`global`; seed
  пишет cross-ref о связях в бакеты группы; `maind_memory_links` отдаёт память из всех
  релевантных бакетов (`project:<id>` + `ns:<группы>` + `global`).
- **Healthcheck** (`maind health [--cwd|--project] [--fix] [--strict]`): статус
  `connected|partial|standalone` + подсказки; провиженеры доставки «приоритета №1» в проекты
  (SessionStart-хук + управляемый блок в `CLAUDE.md`).
- **Единый провижининг** `maind sync`: фан-аут управляемых артефактов на проекты через реестр
  провиженеров (`mcp` · `graph` · `memory` · `health-hook` · `health-doc`), режимы
  `install|update|auto` с честным `changed` по content-hash; `deploy` = `sync --only mcp`.
- **Workspace trust** (`maind workspace sync|status`): доверие Claude к проектам экосистемы
  через `.claude/settings.local.json` (отдельно от allow/deny).
- **MCP harden+extend**: крэш-устойчивый цикл (ошибка инструмента → `isError`, сервер жив),
  эхо `protocolVersion`, stderr-логи, conformance-тест на реальный spawn. **11 tools**
  (+`graph_path`, `graph_project`, `memory_forget`, `memory_links`, `projects_status`).
- **graphify** как со-равный agent-memory механизм связей (граф **кода** проекта),
  раскатывается отдельным MCP-сервером (`deploy --with-graphify`).
- Локальный скилл `.claude/skills/maind-overview` + корневой `CLAUDE.md` (карта кода/конвенции).
- Гайды: federation, namespaces, graphify, health, sync (ru-RU, с примерами).

### Changed
- **Единственная раскладка графа — федерация**: легаси-путь `seed_*` (единый `graph.db` из
  конфига) удалён; всё строится через `derive`. `graph.adapter` канонически
  `federation`/`disabled`; устаревшие `memory`/`graphify`/`networkx` принимаются с
  предупреждением и нормализуются в `federation`.
- Чтение графа — через единый фасад `federation.graph_reader`.
- Документация и `.maind.example.json` приведены к текущей модели; удалено мёртвое поле
  `graph_node`; команда `graph migrate-federation` убрана.

### Performance
- Federation кэширует in-memory union в пределах инстанса (read-only) — query/neighbors/path/
  stats не пересобирают union на каждый вызов.

### Tests
- Покрытие `cli`/`doctor`/`constants` (26/26 модулей), namespace-изоляция памяти,
  graphify-деплой, честный `changed` в sync. 166 → 189 тестов.

## [0.1.0] — 2026-06-14

### Added
- Ядро на Python + bash (тонкий лаунчер `bin/maind` → `python3 -m maind`), stdlib-only.
- **Память**: оркестрация Node-демона `@agentmemory/agentmemory` (`memory start/stop/status`)
  + HTTP-обёртка со scope'ами (`store/recall/forget/export`), сверенная с реальным API
  agentmemory 0.9.x (`/agentmemory/remember` · `/agentmemory/search` · `/agentmemory/health`).
  Порты — из env/конфига, без хардкода.
- **Граф**: stdlib property-граф (`node/edge/neighbors/path/subgraph/stats`) с персистом
  в node-link JSON; `networkx`/`graphify` как опциональные адаптеры через `graph.adapter`.
  Автозасев проектов/связей из конфига (`depends_on`/`uses`/`belongs_to`).
- **Реестр агентов**: `register/heartbeat/list/kill/reap` (`~/.maind/agents.json`),
  деривация состояния `alive/stale/dead` из heartbeat + живости pid.
- **Реестр проектов**: `.maind.json` (надмножество brain `.projects.json`) + fallback на
  legacy с предупреждением; `projects sync --from brain` (маппинг реальной схемы brain).
- **MCP-сервер**: `maind mcp` — stdio JSON-RPC, 6 tools (memory/graph/agents/projects).
- **Миграция**: `migrate from-brain` (конфиг + граф), `migrate from-agentmemory` (iii-config).
- **CLI**: `start`, `status`, `doctor`, сводный статус узла.
- `install.sh`, `.maind.example.json`, `.env.example`, `config/memory/iii-config.yaml`
  (service_name: maind), `scripts/test.sh`, `scripts/validate.sh`.
- Документация (VitePress, ru-RU), 65 unit-тестов (без живого демона — `FakeMemoryServer`).

[Unreleased]: https://github.com/academici/maind/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/academici/maind/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/academici/maind/releases/tag/v0.1.0
