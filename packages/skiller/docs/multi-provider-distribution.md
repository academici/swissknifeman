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
- Хаб-генератор (`scripts/generate-hub.sh`, обёртка `hub.py:14`) умеет писать управляемый блок в
  `CLAUDE.md`/`AGENTS.md` (маркеры `<!-- swissknifeman:hub:start/end -->`) — но это **индекс**
  установленных скиллов, а не **агрегация текста** `.ai/guidelines/*.md`.
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

## Связанное

- [Совместимость с Laravel Boost](./boost-compatibility) — текущая модель сосуществования (Boost как
  источник скиллов vs skiller); этот документ описывает следующий шаг — увод раздачи из Boost.
