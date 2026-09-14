---
title: Раздача локального .ai/ контента на провайдеры (dev-план)
---

# Мультипровайдерная раздача локального `.ai/` контента (dev-план)

> **Статус:** план разработки, фича НЕ реализована. Документ фиксирует задачу и целевой дизайн,
> чтобы skiller смог заменить роль `php artisan boost:update` как кросс-провайдерного генератора
> контекста для AI-агентов. Reference-имплементация «руками» — пилот в проекте `sibintek-insiders`
> (см. раздел [Миграция с Boost](#миграция-с-boost)).

## Зачем

Проекты экосистемы (Laravel) держат источник правды контекста агентов в собственном каталоге
`.ai/`: `.ai/guidelines/*.md` (постоянные правила) и `.ai/skills/<name>/SKILL.md` (узкие контексты).
Сегодня раздачу этого **локального** контента на провайдеров делает **Laravel Boost** (`boost:update`):
генерит `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`, кладёт скиллы в `.claude/skills`/`.cursor/skills`,
пишет `.cursor/rules/*.mdc`. Мы хотим увести эту роль из Boost (оставить Boost только MCP) и отдать
её **skiller** — единому раздатчику экосистемы, чтобы Cursor/Gemini/Codex работали так же, как Claude.

## Проблема / гэп

skiller сегодня раздаёт **только свой реестр** (`env.root/skills/<bucket>`), не локальный `.ai/`
консьюмера:

- `vendor.py` `collect_skills()` (≈`vendor.py:154`) и `skillset.py` `resolve_skillset()`
  (`skillset.py:130-179`) резолвят выбор против индекса реестра (`skills.json`), не против каталога
  целевого проекта. Источник — всегда реестр.
- Хаб-генератор (`scripts/generate-hub.sh` — тонкий лаунчер поверх `lib/skiller/hub.py`) умеет
  писать управляемый блок в `CLAUDE.md`/`AGENTS.md` (маркеры
  `<!-- swissknifeman:hub:start/end -->`) — но это **индекс** установленных скиллов, а не
  **агрегация текста** `.ai/guidelines/*.md`. Форма блока провайдер-зависима: цели с нативным
  листингом скиллов (`CLAUDE.md`, Boost-фрагмент, `AGENTS.md`) получают краткую форму без
  подтверждённых нативным набором имён. Для `AGENTS.md` генератор читает реальный offline
  `codex debug prompt-input` из cwd проекта; неподтверждённые имена сохраняет.
  Цели без листинга (`GEMINI.md`, раскладки Cursor) получают полную форму; `--full-index` возвращает индекс
  всем целям. Сокращение допускается только после машинной сверки обнаружения — см.
  [installation.md](./guide/installation) («Форма блока: по каналу-цели, а не по проекту»).
- Фан-аут провайдеров узкий: `AGENT_DEFAULTS` (`common.py:23`) знает только пути скиллов для
  `claude`/`cursor`/`generic`. Нет генерации `.cursor/rules/*.mdc`, `GEMINI.md`, нет агрегации
  guidelines.

Итог: «локальный `.ai/` → все провайдеры» сейчас нечем закрыть. Нужна новая способность.

## Целевой дизайн команды

Новая команда (рабочее имя) **`skiller distribute`** (альтернатива — расширить `vendor --source`):

```bash
skiller distribute [--source .ai] [--providers claude,cursor,gemini,agents] \
                   [--target DIR] [--dry-run]
```

- **источник** — произвольный локальный каталог проекта (`.ai/skills` + `.ai/guidelines`), НЕ реестр;
- идемпотентно, merge-only, бэкап `*.bak` (конвенция skiller);
- сосуществует с реестровыми `connect`/`vendor` (разные источники — не конфликтуют).

## Матрица провайдеров

| Провайдер | guidelines → | скиллы → | формат скилла |
|:--|:--|:--|:--|
| **claude** | `CLAUDE.md` | `.claude/skills/<name>` (симлинк на `.ai/skills/<name>`) | `SKILL.md` как есть |
| **cursor** | `.cursor/rules/<slug>.mdc` (frontmatter `alwaysApply: true`) | `.cursor/skills/<name>` (симлинк) | `SKILL.md` как есть |
| **gemini** | `GEMINI.md` | — | — |
| **agents/codex** | `AGENTS.md` | — | — |

Реализация: расширить `AGENT_DEFAULTS` (`common.py:23`) до таблицы target-путей per-provider
(guidelines-файл + skills-каталог + стратегия), вынести в единый провайдер-реестр.

## Движок агрегации guidelines

- вход: `.ai/guidelines/*.md` (top-level markdown, сортировка по имени);
- выход: конкатенация в провайдер-файл с управляемым заголовком + разделителями `=== <name> ===`
  (тот же стиль, что был у Boost-блока — обратная совместимость восприятия);
- для `cursor` — обернуть во frontmatter `.mdc` (`alwaysApply: true`);
- **не-md форматы** (`.blade.php` и т.п.) **игнорировать** — они требуют рендера Boost (Blade+Roster),
  вне ответственности skiller. Управляемый блок — между маркерами, чтобы не затирать ручной контент.

## Симлинк vs копия

Сейчас vendor только **копирует** (`shutil.copytree`, `vendor.py`). Для **локального** источника
скиллы уже лежат в проекте (`.ai/skills/`) — дублировать копией бессмысленно: используем **симлинки**
`.claude/skills/<name> → ../../.ai/skills/<name>` (как сделано вручную в пилоте insiders). Стратегия
per-provider: реестровый источник → копия (как сейчас), локальный источник → симлинк.

## Идемпотентность / манифест / lock

- переиспользовать `.swissknifeman-manifest.json` (раздел для distribute-источника) и `skills-lock.json`
  (`lock.py` уже различает источники `swissknifeman`/`laravel-boost`/`local` — добавить `local-ai`);
- чистка stale — только managed-записи distribute; ручные симлинки/файлы не трогать;
- маркировка `managed: true` + путь источника, как в `skillset.py:316-322`.

## Миграция с Boost

Рецепт «Boost → только MCP» (отработан вручную в пилоте `sibintek-insiders`):

1. `boost.json`: `guidelines:false`, `skills:[]`, `mcp:true` (Boost остаётся MCP-сервером).
2. Снести Boost-инсталлы скиллов (`.claude/skills`/`.cursor/skills` — не-симлинк каталоги пакетов)
   и Boost-guideline-артефакты (`.cursor/rules/laravel-boost.mdc`, `.ai/guidelines/*.blade.php`).
3. Отцепить `@php artisan boost:update` из `composer.json` `post-update-cmd`.
4. Раздать локальный `.ai/` через skiller (целевая фича); до неё — временный
   `scripts/build-agent-docs.sh` в проекте (Claude-only).

Раскатка на остальные одинаково устроенные проекты (`flexcrm`, `sova` и др. — те же
`<laravel-boost-guidelines>` + `.ai/` + симлинки) — той же командой.

## Фазы (milestones)

1. **M1 — провайдер-реестр**: таблица target-путей per-provider из `AGENT_DEFAULTS`; только claude
   (паритет с `scripts/build-agent-docs.sh`).
2. **M2 — агрегация guidelines**: движок конкатенации `.ai/guidelines/*.md` → `CLAUDE.md`/`AGENTS.md`,
   управляемые маркеры, индекс скиллов.
3. **M3 — cursor**: `.cursor/rules/*.mdc` + симлинки `.cursor/skills`.
4. **M4 — gemini/agents** + lock/manifest интеграция, `--dry-run`, очистка stale.
5. **M5 — миграционный хелпер**: `skiller distribute --from-boost` (автоматизирует рецепт миграции).

## Тест-план

- `scripts/test.sh` (unittest, stdlib-only, без сети/php) — фикстуры консьюмера в tmpdir:
  синтетический `.ai/guidelines/*.md` + `.ai/skills/*/SKILL.md`;
- проверки: идемпотентность (повторный прогон не меняет байты), merge-only (ручной контент цел),
  симлинки указывают на `.ai/skills`, управляемый блок ограничен маркерами, `--dry-run` без записи;
- `scripts/validate.sh` зелёный; после правок реестра — `skiller registry`.

## Явный проектный выбор Codex plugins

```bash
packages/skiller/bin/skiller connect --target /path/to/project --native-codex --dry-run
packages/skiller/bin/skiller connect --target /path/to/project --native-codex
```

`--native-codex` требует Python 3.11+ (stdlib `tomllib`) и согласует `[plugins."<name>@swissknifeman"].enabled` в проектном
`.codex/config.toml` с выбранным набором Connect. Выбранные плагины получают `true`,
остальные известные и унаследованные Swissknifeman-плагины — `false`. Глобальные defaults,
сторонние плагины, permissions, остальные TOML-поля и комментарии сохраняются. Перед изменением делается
полный parse/render preflight; изменённый файл имеет `.bak`, повторный запуск идемпотентен.
Нестандартная inline/dotted раскладка plugin tables отклоняется до изменения проекта;
используйте отдельные `[plugins."name@swissknifeman"]` таблицы. Codex читает проектную
конфигурацию в trusted проектах. Флаг не устанавливает cache: наличия `.agents/plugins/bundles`
недостаточно для native activation. Установите недостающие плагины явным `codex plugin add`,
затем проверьте `codex plugin list --json` и `codex debug prompt-input` из cwd потребителя.

В сочетании с `--hub` native selection применяется до генерации хаба; для обычного
проекта обновляются `CLAUDE.md` и `AGENTS.md` с сохранением текста вне managed-блоков.
В Boost-проекте сохраняется существующий путь через guideline-фрагмент.

`--cleanup-codex-vendored` архивирует manifest-declared legacy copies отдельно от установки.
`--cleanup-codex-links` архивирует только распознанные managed links: либо native replacement
совпадает по всем исходным файлам скилла, либо этот точный путь явно выключен в проектном
`[[skills.config]]`. При несовпадении, чужом ownership или изменённой ссылке данные сохраняются.
Уникальные локальные скиллы без явного отключения остаются. Это также позволяет снять старые
ссылки в клиентах, где project-level per-skill selection ещё не влияет на discovery.

## Codex publication — consumer-acceptance гейт (P5.5)

> Не относится к `skiller distribute` (фича выше остаётся нереализованным dev-планом) — это
> отдельная, уже РАБОТАЮЩАЯ проверка существующей раздачи Codex-плагинов через
> `.agents/plugins/marketplace.json`. Помещена на этой странице как единственном месте,
> где документируется поведение мультипровайдерной раздачи Codex.

**Зачем.** Внутренние generator/unit-проверки (`test_codex_publication.py` и др.) сверяют
только СТАТИЧЕСКУЮ схему сгенерированных артефактов — они никогда не спрашивают ничего у
настоящего `codex` CLI. Azguard, 2026-07-21: этот класс проверок был GREEN, а свежая
Codex-сессия не видела `task-plan-run`/`task-plan-exec` — sibling-плагин `task` был
невидим нативному marketplace discovery. Package-level GREEN без прохождения всей цепочки
`source → marketplace → install/cache → clean consumer → fresh session` не является release
GREEN (`roadmap/codex-publication-consumer-acceptance.md`, снят этим item'ом).

**Что проверяет** `packages/skiller/tests/test_codex_consumer_acceptance.py`:

1. Независимый (не через `publication.render_codex_publication`) inventory ожидаемых
   Codex-плагинов — собран напрямую с диска (`buckets.json`, `configs/core-policy.json`,
   `skm/.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` соседних пакетов) — сверяется
   с тем, что реально отдаёт `codex plugin list --available --json` из изолированного
   `CODEX_HOME`.
2. Установка `task@swissknifeman` в изолированный temp `CODEX_HOME` + сверка кэша
   байт-в-байт с исходником, без касания реального `~/.codex`.
3. `codex debug prompt-input` (офлайн-рендер prompt'а модели, без сети/auth) из temp
   consumer-каталога ВНЕ репозитория — подтверждает, что `task-plan-run`/`task-plan-exec`
   видны по имени и резолвятся из изолированного кэша, а не из репозиторного
   `.agents/skills` (последнее — доказанный источник ложного GREEN, см. тест
   `test_repo_local_skills_would_mask_a_real_publication_failure`: тот же прогон из корня
   репозитория действительно подмешивает `.agents/skills` в discovery).
4. Дрейф экспортируемой поверхности без version bump — RED (`InventoryDriftDetectionCase`,
   не требует живого `codex`).

**Явное поведение при отсутствии `codex`.** `scripts/validate.sh` (гейт 18) печатает
`SKIP: ... гейт НЕ прогонялся` и остаётся зелёным, если бинарь `codex` не найден в `PATH` —
skip и GREEN различимы в выводе. Локально (где `codex` установлен) гейт исполняется
живым прогоном; в CI бинарь сегодня недоступен — гейт там SKIP, вопрос установки `codex`
в CI-раннер вне скоупа этого item'а.

## Current operator boundary

The M1–M5 distribution design above remains a roadmap, not an instruction to delete or rewrite a
consumer. For committed provider distribution, first inspect the generated root
`docs/provider-support.md` matrix and run a no-write command:

```bash
packages/skiller/bin/skiller connect --dry-run
packages/skiller/bin/skiller sync --target <project> --dry-run
```

`connect` updates the Claude Code marketplace projection; `sync` writes selected managed skill
projections only when the project's config selects that channel. `sync --repair` is a separate
managed-drift operation, not a general overwrite. Unsupported capabilities, missing provider
evidence, and a skipped consumer-acceptance probe remain non-green. Apply only after the command's
ownership/backup gate is satisfied; preserve the managed preimage and use the same declared target
for readback or rollback. Neither command authorizes a release, tag, or publication.

## Связанное

- [Совместимость с Laravel Boost](./boost-compatibility) — текущая модель сосуществования (Boost как
  источник скиллов vs skiller); этот документ описывает следующий шаг — увод раздачи из Boost.
