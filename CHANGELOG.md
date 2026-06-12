# Changelog

## [Unreleased]

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
