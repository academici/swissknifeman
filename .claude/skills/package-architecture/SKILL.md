---
name: package-architecture
description: "Полная карта пакета swissknifeman: каналы дистрибуции, CLI, скрипты, конфиги, генерируемые артефакты и что чем регенерируется. Активировать в начале любой задачи в этом репозитории, затрагивающей skills/, bin/, scripts/, configs/, profiles/, реестр или манифесты."
---

# Архитектура пакета swissknifeman

Внутренний скилл (не экспортируется). Только **факты** — карта пакета.
Процедуры: создание скиллов → `skill-authoring`, завершение изменений →
`release-discipline`, документация → `docs-maintenance`.

## Когда активировать

- В начале любой нетривиальной задачи в этом репозитории.
- Перед изменением любого скрипта, конфига или схемы.
- При ответах на вопросы «как работает пакет».

## Каналы дистрибуции

1. **Claude Code plugin marketplace** (основной для Claude Code).
   Бакет = плагин: `skills/<bucket>/.claude-plugin/plugin.json`, корневой
   каталог — `.claude-plugin/marketplace.json` + плагин `generate-skill`.
   Версия плагина = git SHA: потребители видят изменения **только после
   коммита**. Подключение проекта: `swissknifeman connect` (пишет
   `extraKnownMarketplaces` + `enabledPlugins."<bucket>@swissknifeman"` в
   `.claude/settings(.local).json` проекта; merge-only, явный `false` не
   перетирается, бэкап в `.bak`).
2. **Vendoring** (Cursor и другие агенты): `swissknifeman vendor` — копирует
   скиллы в проект (`.cursor/skills` / `.ai/skills`; flat-layout для
   `--agent claude` deprecated). Профили `profiles/*.json`
   (laravel-project, obsidian-vault, php-package, standalone), precedence:
   флаги > `.swissknife.json` проекта > autodetect (`.obsidian/` /
   `artisan`+`composer.json` / `composer.json`). Транзитивный резолв
   frontmatter `requires`; `--exclude` побеждает зависимость. Манифест
   `.swissknifeman-manifest.json` — чистая переустановка без слепых перезаписей.

## CLI `bin/swissknifeman`

Устанавливается симлинком в `~/.local/bin` через `./install.sh`; путь к
реестру выводит из `readlink -f` самого себя (конфиг пути не нужен; репо
переехал → перезапустить install.sh). Состояние: `~/.swissknifeman/projects.json`
(version 1, записи с ключом path+channel) — пополняется автоматически при
connect/vendor/update; диск всегда источник истины, записи — дефолты replay.

Команды: `connect`, `vendor`, `update [--all]` (детект каналов по маркерам,
adopt незарегистрированных, починка path-drift marketplace), `status`, `list
[--prune]`, `registry` (мейнтейнер), `validate`, `doctor`, `version`. Корень
проекта ищется вверх от CWD: `.swissknife.json` → `.claude/` → `.git`.
Внутри самого реестра project-команды отказываются работать.

`scripts/connect-claude.sh` и `sync.sh` — deprecation-wrapper'ы на один релиз.
Brain-sync удалён: brain — обычный потребляющий проект.

## Генерируемые артефакты — руками не править

| Артефакт | Генератор |
|---|---|
| `skills.json` (реестр v5: sha256, provenance, requires/produces_for) | `swissknifeman registry` |
| `skills/*/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | `swissknifeman registry` |
| `docs/guide/graph.md` (Mermaid-граф зависимостей) | `swissknifeman registry` → `scripts/generate-graph.sh` |
| Хаб в проекте (managed-блок CLAUDE.md или `.ai/guidelines/swissknifeman-hub.md`) | `scripts/generate-hub.sh` |
| Permissions-пресеты в проекте | `scripts/apply-permissions.sh` (пресеты в `configs/claude-code/`) |

## Валидация — `scripts/validate.sh` (== CI)

Группы проверок: (1) frontmatter SKILL.md — для локальных обязательны
name/bucket/version/description, при наличии upstream.json только
name/description; (2) схема upstream.json; (3) profiles/*.json;
(4) skills.json парсится; (5) snippet-манифесты; (6) buckets.json 1:1 с
каталогами бакетов; (7) свежесть плагин-манифестов; (7b) запрет вложенных
SKILL.md; (8) уникальность имён в бакете (через бакеты — warning);
(9) requires/produces_for: существующие имена, без self-ref и циклов;
(10) мягкий линт внутренних скиллов `.claude/skills/` (name+description,
kebab-case == имя каталога); (11) `bash -n` всех скриптов + исполняемость CLI.

## Прочие инструменты и контракты

- `scripts/update-upstreams.sh --check|--apply` — синк внешних скиллов по
  upstream.json (sha256, fetched_at).
- `scripts/scan-skills.sh` / `scan-and-pr.sh` — сканер кандидатов,
  порог качества ≥60 (`.skills-scanner.json`).
- `references/` — жизненный цикл внешних источников: planned → imported/rejected.
- `buckets.json` — обязательная мета каждого бакета (description/category/tags).
- `SKILL_TEMPLATE.md` — каноническая схема frontmatter.
- `docs/` — VitePress (`docs/.vitepress/config.mts` — sidebar).

## Матрица синхронизации («что за чем тянется»)

| Изменение | Обязательные действия |
|---|---|
| Скилл добавлен/изменён/перенесён/удалён | `validate.sh` → `swissknifeman registry` → коммит регенерированного |
| Новый бакет | запись в `buckets.json` |
| `requires`/`produces_for` изменены | регенерация графа (входит в `registry`) |
| Внешний файл скилла обновлён | `update-upstreams.sh --apply` (sha256 + fetched_at) |
| Содержательное изменение | CHANGELOG `[Unreleased]` → `release-discipline` |
| Процесс/возможность изменены | оценка docs/ → `docs-maintenance` |

## Связанные скиллы

- `skill-authoring` — процедура создания/правки скиллов.
- `release-discipline` — завершение изменения (validate → registry → CHANGELOG → PR).
- `docs-maintenance` — решение об обновлении docs/ после задачи.

## Ссылки

- `CONTRIBUTING.md` — канонический процесс контрибуции.
- `README.md`, `docs/guide/index.md`, `docs/guide/cli.md`.
