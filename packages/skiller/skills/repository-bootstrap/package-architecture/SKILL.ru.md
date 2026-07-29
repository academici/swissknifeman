---
name: package-architecture
bucket: repository-bootstrap
version: 0.1.0
description: "Полная карта пакета swissknifeman: каналы дистрибуции, CLI, скрипты, конфиги, генерируемые артефакты и что чем регенерируется. Активировать в начале любой задачи в этом репозитории, затрагивающей skills/, bin/, scripts/, configs/, profiles/, реестр или манифесты."
risk: read
persona: oss-dev
tags: [skiller, architecture, distribution, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Архитектура пакета swissknifeman

Внутренний скилл (не экспортируется). Только **факты** — карта пакета.
Процедуры: создание скиллов → [skill-authoring], завершение изменений →
[release-discipline], документация → [docs-maintenance].

[skill-authoring]: ../skill-authoring/SKILL.md
[release-discipline]: ../release-discipline/SKILL.md
[docs-maintenance]: ../docs-maintenance/SKILL.md

## Когда активировать

- В начале любой нетривиальной задачи в этом репозитории.
- Перед изменением любого скрипта, конфига или схемы.
- При ответах на вопросы «как работает пакет».

## Каналы дистрибуции

1. **Claude Code plugin marketplace** (основной для Claude Code).
   Бакет = плагин: `skills/<bucket>/.claude-plugin/plugin.json`, корневой
   каталог — `.claude-plugin/marketplace.json` + плагин `generate-skill`.
   Версия плагина = git SHA: потребители видят изменения **только после
   коммита**. Подключение проекта: `skiller connect` (пишет
   `extraKnownMarketplaces` + `enabledPlugins."<bucket>@swissknifeman"` в
   `.claude/settings(.local).json` проекта; merge-only, явный `false` не
   перетирается, бэкап в `.bak`).
2. **Vendor через `sync`** (физ. перенос в репо — основной для Claude вне
   marketplace). Конфиг `.swissknifeman/config.json` (`mode: vendor`,
   `include`/`buckets`/`exclude`) → `skiller sync` копирует скиллы в
   `.claude/skills/<name>/`, пишет `skills-lock.json` (`managed: true` +
   sha256) и манифест `.swissknifeman-manifest.json`. **Файлы коммитятся в
   репо проекта** — канал для проектов, отдаваемых сторонним разработчикам без
   доступа к реестру swissknifeman (в отличие от `connect`, где marketplace
   указывает на локальный путь к реестру). Безопасное удаление по `managed`,
   чужие скиллы не трогаются (`--force` перетирает занятый путь). Реализация —
   `skillset.py`; `do_sync` — точка входа для `integrate`/`onboard`.
3. **Legacy vendoring** (Cursor и другие агенты): `skiller vendor` — копирует
   скиллы в `.cursor/skills` / `.ai/skills` (flat-layout для `--agent claude`
   **deprecated** — для Claude используй `sync`). Профили `profiles/*.json`
   (laravel-project, obsidian-vault, php-package, standalone), precedence:
   флаги > `.swissknife.json` проекта > autodetect (`.obsidian/` /
   `artisan`+`composer.json` / `composer.json`). Транзитивный резолв
   frontmatter `requires`; `--exclude` побеждает зависимость. Манифест
   `.swissknifeman-manifest.json` — чистая переустановка без слепых перезаписей.

**Класс A private/source-only исключение (P1.2, D31).** Бакет `repository-bootstrap`
существует ТОЛЬКО как источник для 13 root-bootstrap identities (13 канонических пар
`SKILL.ru.md`/`SKILL.md`, 26 тонких проекций `.claude/skills/<id>/`+`.agents/skills/<id>/`).
`build_registry` индексирует его для owner/hash-lookup, но `build_publication_catalog`
исключает его из обычных Claude/Codex bucket-юнитов, из членства в `core` и из обоих
marketplace; consumer vendor/connect отклоняет source-only записи вместо копирования их в
проект-потребитель. Единственный производитель root-проекций — `registry.py` →
`publication.py` root-bootstrap рендерер из `configs/repository-bootstrap-skills.json`;
`skillset.py` реализует только consumer-исключение, никогда не является этим self-host
продюсером (см. [semantic-identity-ownership-v1](../../../../../plans/archive/2026.07.24-AGENT-RELIABILITY/root/contracts/semantic-identity-ownership-v1.md)).

## Два конфига проекта (не путать, не сливать)

- **`.swissknife.json`** — лёгкий конфиг для **connect** (+ legacy vendor):
  `project_type/buckets/exclude/presets/agent` (+ agent-framework `shape/stacks/skills_map`).
  Ключи `CONFIG_KEYS` (`common.py`), валидатор `config.validate_config`. **bucket-granular.**
- **`.swissknifeman/config.json`** — канонический SoT **vendor-режима** (`sync`):
  `version/mode/agent/skills_path/presets/include/buckets/exclude`. Ключи `SKILLSET_KEYS`
  (`skillset.py`), валидатор `load_skillset_config`. **skill-granular.**
- JSON-схемы обоих — `schema/*.json` (DX/IntelliSense через `$schema`); рантайм-валидация
  ручная, stdlib-only; синхрон схемы↔код держат `tests/test_schema.py` и `skiller doctor`.
- Бутстрап vendor-конфига — `skiller init` (из автодетекта, без копий). Мост: `sync`/`init`
  лениво материализуют `.swissknifeman/config.json` из профиля/legacy, недеструктивно.

## Потребление скиллов в рантайме (анти-straw-man)

Тела скиллов в рантайме читает **сам Claude Code**, а не Python-процесс skiller: vendor →
с диска `.claude/skills/<name>/SKILL.md`; connect → из реестра через marketplace. **Нет
`load_skill`/`loader.py`** — skiller только копирует/регистрирует и парсит фронтматтер
(для метаданных). Поэтому «кэш загрузки скиллов» внутри skiller **не имеет вызывающего**;
экономию даёт автоматический prompt caching Claude Code. Полный канон —
`docs/guide/skills-architecture.md`.

## CLI `bin/skiller`

Устанавливается симлинком в `~/.local/bin` через `./install.sh`; путь к
реестру выводит из `readlink -f` самого себя (конфиг пути не нужен; репо
переехал → перезапустить install.sh). Состояние: `~/.swissknifeman/projects.json`
(version 1, записи с ключом path+channel) — пополняется автоматически при
connect/vendor/update; диск всегда источник истины, записи — дефолты replay.

Команды: `connect`, `vendor`, `integrate`, `update [--all]` (детект каналов по
маркерам, adopt незарегистрированных, починка path-drift marketplace),
`init` (создать `.swissknifeman/config.json` без копирования), `sync` (vendor),
`lock`, `status`, `budget` (`--first-turn` — always-on футпринт первого хода
проекта: skills+agents+CLAUDE.md/rules+живой прогон хуков+MCP, target ≤7K/warn
>10K; флот — `maind doctor --context`), `list [--prune]`, `topology [init|show]`,
`registry` (мейнтейнер), `validate`, `doctor`, `version`. Корень проекта ищется
вверх от CWD: `.swissknife.json` → `.claude/` → `.git`. Внутри самого реестра
project-команды отказываются работать.
Лаунчер `bin/skiller` whitelist'ит команды в `case` — новую команду
добавлять и в `COMMANDS` (`lib/skiller/cli.py`), и в `case`.

**Гигиена каналов (`status.channel_overlap`).** `status` ловит бакет, активный
ОДНОВРЕМЕННО как плагин (connect, `enabledPlugins`) и вендоренный (vendor, манифест
`source_path` → бакет) → `⚠ ДУБЛЬ КАНАЛОВ`. Проверка одна, в skiller (владелец
скиллов); зонтик дёргает её через `swissknifeman skills status`, по пакетам НЕ
дублируется. Инвариант синка: трогаем только `managed: true` — чужие/ручные записи
`skills-lock.json` переживают `sync`.

**Топология (`topology`, `lib/skiller/topology.py`).** Глобальная карта
локальной среды `~/.swissknifeman/topology.json` (version 1): три узла-хаба
`brain`/`swissknifeman`/`projects_base` (роли `docs-hub`/`skills-hub`/`workspace`).
`init` — интерактивный сбор (авто-детект дефолтов: swissknifeman = корень реестра,
projects_base = общий предок путей из `projects.json`, brain = `~/Vaults/Brain`),
атомарная запись с бэкапом `.bak`, сохранение `created_at`. `show [--json]` —
печать. Файл машинно-специфичен, в проекты не коммитится. Предлагается при
`install.sh` (TTY). Раздаваемый скилл `skills/system/local-topology` объясняет
схему и резолвит узлы по этому файлу.

`scripts/connect-claude.sh` и `sync.sh` — deprecation-wrapper'ы на один релиз.
Brain-sync удалён: brain — обычный потребляющий проект.

## Генерируемые артефакты — руками не править

| Артефакт | Генератор |
|---|---|
| `skills.json` (реестр v5: sha256 + content_sha256, provenance, requires/produces_for, опц. `level`) | `skiller registry` |
| `skills/*/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` | `skiller registry` |
| `docs/guide/graph.md` (Mermaid-граф зависимостей) | `skiller registry` → `scripts/generate-graph.sh` |
| 26 тонких root-bootstrap проекций (`.claude/skills/<id>/`+`.agents/skills/<id>/`) + `adapters/repository-bootstrap/publication-lock.json` | `skiller registry` → root-bootstrap рендерер `publication.py` |
| Хаб в проекте (managed-блок CLAUDE.md или `.ai/guidelines/swissknifeman-hub.md`) | `scripts/generate-hub.sh` |
| Permissions/MCP/хуки в проекте | пакет **`harness`** (`harness permissions\|mcp\|hooks`); skiller делегирует через subprocess |

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
Описания: `DESC_WARN_MAX=300` (warn) / `DESC_ERROR_MAX=450` (hard error) +
burn-down-рэтчет `scripts/desc-burndown.txt` (унаследованный долг >300 легален
только пока внесён в список; новый долг вне списка — error; one-way — протухшие
записи предупреждают на удаление).

## Визард `integrate` (`lib/skiller/integrate.py`)

Чеклист-обёртка над командами: пререквизиты → скиллы → permissions → **MCP** →
auto-approve → memory → hub → brain. Бандлы `minimal`/`recommended`/`full`/`custom`
(`BUNDLES` = пред-ответы). Все записи merge-only, бэкап `*.bak`, `--dry-run`.

**Канал скиллов (`--skills-channel connect|vendor|skip`).** `_resolve_channel`:
флаг > интерактивный вопрос (TTY) > дефолт бандла (`connect`). Блок скиллов
роутит: `connect` → `do_connect`; `vendor` + `agent=claude` → **`do_sync`**
(физ. копии в `.claude/skills/` через `.swissknifeman/config.json`); `vendor` +
`cursor|generic` → legacy `do_vendor`. `maind onboard`/`swissknifeman setup`
пробрасывают тот же флаг и тоже спрашивают канал (только для скиллов; память/граф —
отдельные плоскости, от канала не зависят).

**Окружение делегируется в `harness`.** Блоки permissions / MCP / auto-approve /
memory не пишут файлы сами — зовут `harness permissions|mcp|hooks` через subprocess
(резолв лаунчера: `harness_bin(env)` → `SKM_HARNESS_BIN` или
`<монорепо>/packages/harness/bin/harness`; нет harness → блок мягко пропускается).
Здесь остаётся ПОЛИТИКА выбора: `_default_mcp(target)` раздаёт `DEV_MCP` (сейчас
`context7`) во всё, **кроме** `obsidian-vault`; `recommended`/`full` включают dev-MCP,
`minimal` — нет, `custom` — спрашивает. Сами пресеты MCP/permissions и их merge —
в пакете `harness` (`configs/claude-code/`). Добавить сервер: пресет в
`packages/harness/configs/claude-code/mcp/`, при необходимости — `DEV_MCP` в integrate.

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
| Скилл добавлен/изменён/перенесён/удалён | `validate.sh` → `skiller registry` → коммит регенерированного |
| Новый бакет | запись в `buckets.json` |
| `requires`/`produces_for` изменены | регенерация графа (входит в `registry`) |
| Внешний файл скилла обновлён | `update-upstreams.sh --apply` (sha256 + fetched_at) |
| Содержательное изменение | CHANGELOG `[Unreleased]` → [release-discipline] |
| Процесс/возможность изменены | оценка docs/ → [docs-maintenance] |

## Связанные скиллы

- [skill-authoring] — процедура создания/правки скиллов.
- [release-discipline] — завершение изменения (validate → registry → CHANGELOG → PR).
- [docs-maintenance] — решение об обновлении docs/ после задачи.

## Ссылки

- `CONTRIBUTING.md` — канонический процесс контрибуции.
- `README.md`, `docs/guide/index.md`, `docs/guide/cli.md`.

## Провенанс (root-bootstrap, P1.2)

Класс A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
канонический источник — этот файл; тонкие проекции — `.claude/skills/package-architecture/SKILL.md`
и `.agents/skills/package-architecture/SKILL.md` (генерируются `skiller registry`, не редактируются
руками). Бакет `repository-bootstrap` — приватный, не публикуется как обычный unit/core/marketplace,
не вендорится/коннектится в проекты-потребители.
