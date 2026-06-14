# Changelog

## [Unreleased]

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
