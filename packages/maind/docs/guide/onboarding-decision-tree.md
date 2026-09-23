# Дерево решений: настройка проекта

Полный чек-лист сценариев онбординга и эксплуатации проекта в экосистеме **academici**.
Это **единый источник истины** по веткам настройки — каждый слой в формате
**вопрос → варианты → действие/условие**. Цель: подбирать **оптимальный** набор под проект,
а не включать «всё подряд». Если выбор неочевиден — **спрашивать пользователя**, не угадывать.

> Один вход для всего дерева: `maind onboard <project|path>` (оркеструет skiller + harness +
> память + граф). Точечные изменения — `skiller …` / `harness …` / `maind sync …`.

## Слой 0 — Тип проекта (детект)

**Вопрос:** какой стек у проекта? Определяется автоматически (`core/project.py`,
порядок от частного к общему):

| Маркер в корне | Тип | Профиль (`profiles/<type>.json`) |
|:--|:--|:--|
| `.obsidian/` | `obsidian-vault` | quality |
| `composer.json` + `artisan` | `laravel-project` | system, architect, php, devops, quality, operator |
| `composer.json` | `php-package` | php, devops, … |
| `pubspec.yaml` | `dart-flutter` | … |
| `pyproject.toml`/`requirements.txt`/`setup.py` | `python-backend` | system, architect, python, devops, quality, operator |
| `package.json` + UI-фреймворк (vue/nuxt/react/…) | `node-frontend` | system, architect, frontend, quality, devops |
| `package.json` | `node-package` | system, oss-dev, quality, devops |
| — нет маркеров — | `standalone` | **`["*"]` = поставить всё** |

**⚠ Условие — тип НЕ распознан (`standalone`):** это **не** сигнал «ставь всё».
- Авто/неинтерактив (`--yes`): ставится **минимальный набор** (`general, oss-dev, system`) +
  громкий warn с предложением указать профиль (`autodetect-fallback`, см. `resolve_selection`).
- Интерактив (`skiller integrate` визард): спросить профиль из списка.
- Явный «поставь всё» возможен только осознанно: `--profile standalone`.

## Слой 1 — Механизм памяти

**Вопрос:** как вести память/контекст проекта? `maind onboard --memory <…>` (дефолт `manual`).

| Вариант | Действие | Когда |
|:--|:--|:--|
| **manual** (реком.) | mAInd через MCP/CLI по запросу; без SessionStart digest; `autoMemoryEnabled:false` | по умолчанию для узлов экосистемы |
| **maind** | явно включить SessionStart digest mAInd | только при измеренной пользе авто-контекста |
| **native** | вернуть нативную авто-память Claude Code; `MODE=off`, revert хука | проект вне экосистемы |
| **off** | память выключена | временно/особый случай |

## Слой 2 — Namespaces (изоляция связей)

**Вопрос:** в каких namespace живёт проект? `--namespace a,b` (дефолт `["axioma", <id>]`).
Память **общая внутри** namespace, **изолирована между**.

- **Общий** (экосистемный/продуктовый) — связывает группу: напр. `dterema` для back+front одного продукта.
- **Раздельный личный** — свой у каждого подпроекта: напр. `dterema-cms` (back), `dterema-web` (front).
- **Wildcard `*`** — инфраструктура, видимая всем (`global`): пакеты-ядро (corex/azguard/…).

**Условие — несколько подпроектов одного продукта:** дать общий продуктовый ns (связь) **и**
раздельный личный каждому (изоляция). Новый ns регистрировать в секции `namespaces` хаба.

## Слой 3 — Канал скиллов (ВСЕГДА спрашивать)

**Вопрос:** как доставлять скиллы? Выбор меняет, что попадёт в репо.

| Канал | Команда | Гранулярность | В репо | Когда |
|:--|:--|:--|:--|:--|
| **connect** | `skiller connect` | бакет целиком (`enabledPlugins`) | нет | устраивает «весь бакет», фиксация не нужна, автообновление из реестра; ⚠️ нужен доступ к реестру swissknifeman (marketplace = локальный путь) |
| **vendor** | `skiller sync` (`.swissknifeman/config.json`) | отдельные скиллы (+`skills-lock.json`) | да | контроль набора, видимость и коммит в репо, выбор позиций; **проект отдают внешним разработчикам без swissknifeman** (файлы в репо) |

Дерево выбора: проект уходит сторонним разработчикам / нужна фиксация в git / точечный выбор →
**vendor**; иначе (своё окружение, экосистема) → **connect**. Laravel Boost — **только MCP**.

Канал спрашивается на онбординге и пробрасывается флагом `--skills-channel connect|vendor`
(`maind onboard` / `swissknifeman setup` / `skiller integrate`). При `vendor` `integrate` для
Claude-проекта сам генерит `.swissknifeman/config.json` из профиля и применяет `sync` (физ. копии
в `.claude/skills/`). Выбор канала касается **только скиллов** — память/граф/MCP от него не зависят.

## Слой 4 — Профиль/бакеты (оптимальный набор)

**Вопрос:** какие бакеты ролей? По умолчанию — из профиля типа (Слой 0). **Не** включать `php`/
`python`/`mobile` на чистом фронте и наоборот. CORE (`general`, `oss-dev`) раздаётся всегда
(`--no-core` отключает). Неочевидно → спросить (2-3 курированных варианта).

## Слой 5 — Окружение (harness)

| Решение | Варианты | Действие |
|:--|:--|:--|
| **permissions-пресеты** | base, laravel, php, node, python, docker, … | autodetect по стеку; merge в `settings.json` |
| **MCP-серверы** | context7, playwright, fetch, github, … | dev-дефолт `context7` (кроме obsidian) + профиль + `--mcp` |
| **auto-approve** | strict / permissive / bypass / off | `.claude/auto-approve.env.ini` + PreToolUse-хук |
| **brain-memory** | file / federation / agentmemory / off | `.swissknife.json` + memory-хук |

### PHP-инструменты: PAO (инвариант для php/laravel-проектов)

**Вопрос:** для `laravel-project`/`php-package` (PHP≥8.3) — установлен ли `laravel/pao`
(agent-optimized вывод PHP-тестов/анализа, прямая токен-экономия — тесты/PHPStan/Rector/
Artisan схлопываются в ~20-токенный JSON вместо тысяч строк)? Онбординг детектит по файловым
фактам (`composer.lock`/`vendor/laravel/pao` + `php -v`) и действует так:

| Состояние | Действие |
|:--|:--|
| не php-тип / PHP < 8.3 | skip (не применимо / не поддерживается) |
| осознанный opt-out (`project.pao_opt_out`) | skip, без warn |
| отсутствует, интерактивная сессия | спросить, установить ли `composer require laravel/pao --dev` |
| отсутствует, `--yes`/неинтерактив | **не ставить молча** — громкий warn с рекомендацией |
| уже установлен | skip, `status:ok` |

Инвариант: **php-проект (≥8.3) ⇒ `laravel/pao` установлен ИЛИ зафиксирован opt-out.**
Видимость отсутствия в диагностике — doctor-гейт (`plans/2026.07.07-SKM-AUDIT-004` P6.3); скилл-инструкция
для агента — `php/pao` (`packages/skiller/skills/php/pao/SKILL.md`).

## Слой 6 — Deploy (MCP + код-граф)

- **MCP-таргеты:** `.mcp.json` (claude) всегда; `.cursor/mcp.json` если есть `.cursor/`; vscode по флагу.
- **Код-граф (Serena):** `--with-code` → MCP-сервер кода + `.serena/project.yml` (язык по типу,
  ignores). Нет бинаря Serena → пропуск с warn.

## Слой 7 — Граф + seed-память

- **derive графа** из источников истины (composer/package/docs/skills-lock) → стор проекта + индекс.
- **seed-память:** базовый факт о связях в `project:<id>` + `ns:<группа>`.
- Отключается `graph.enabled=false` / `--dry-run`.

## Слой 8 — Agent-packs

Субагенты по профилю (`profile.agent_pack` + `model_tiers`): laravel→`backend-laravel`,
python→`python-backend`, frontend→`node-frontend`. Профиль без `agent_pack` → пропуск.

## Слой 9 — Brain doc-sync

`--with-brain` → подсказка по двустороннему синку `docs/` с Brain-валтом (нужен `repo:` во
frontmatter control-ноты). Команды — `~/Vaults/Brain/bin/brain status|sync <proj>`.

**Doc-папки и их видимость** считываются из конфига, не угадываются по имени. Модель папки —
`{id, vault, repo, visibility}` (имя сторон и статус развязаны): источник истины — frontmatter
control-ноты Brain, maind кэширует в `docs_folders`. Дефолт `visibility` по типу проекта
(`core.docs_visibility_for`): **пакет/библиотека** (`php-package`/`node-package`/`dart-flutter`)
→ `docs` **public** (публичная VitePress-документация); **продукт** (`laravel-project`/
`node-frontend`/`python-backend`/…) → `docs` **private** (внутренняя). При онбординге
`_ensure_project` проставляет дефолт по типу; переопределяется во frontmatter (плоские ключи
`docs_folders`/`docs_public`/`docs_repo_map` — вариант A, parser наивный). Публичная папка не
несёт `[[wikilinks]]` (гейт brain). Деталь — Brain `docs/workflow/docs-watcher.md`.

> **Внутренний AI-гайд агент-пака** (`subagents-and-workflows.md`) живёт в `.claude/guidelines/`,
> НЕ в `docs/` — это артефакт для агентов, не публичная документация (иначе утёк бы в публикацию
> и в Brain-валт). agent-pack стек-паки (backend-laravel и пр.) пишут его туда по дефолту.

## Слой 10 — Эксплуатация (ongoing)

| Задача | Команда | Ветки |
|:--|:--|:--|
| **перераскатать артефакты** | `maind sync [--only mcp,graph,…] [--project\|--namespace\|--all] [--mode install\|update\|auto]` | provisioner-порядок: mcp → code-graph → graph → memory → memory-hook → health-hook → health-doc → feature-log → ecosystem-skill → setup-skill → agent-pack |
| **сменить канал скиллов** | `skiller status` → connect/vendor (Слой 3) | connect↔vendor; lock не теряет чужие записи |
| **миграция** | `maind migrate …` | legacy `.maind.json`→`config.json`, adapter-нормализация |
| **диагностика** | `maind health` (round-trip), `skiller status`, `maind doctor` | health=connected — гейт «реально пишет», а не «поднято» |

## Принципы

- **Оптимально, не максимально.** Набор под стек и роль; «всё подряд» — только осознанно.
- **Неочевидно → спросить.** AskUserQuestion с 2-3 курированными вариантами, не угадывать.
- **Спрашивать канал скиллов всегда** (connect vs vendor) — он меняет, что коммитится.
- Связанные доки: [Namespaces](./namespaces.md) · [Sync](./sync.md) · [Healthcheck](./health.md) ·
  [Граф кода](./code-graph.md) · skiller `integration-checklist`.
