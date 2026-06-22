---
name: project-tooling-runbook
description: Раннбук управления инструментами проектов экосистемы — мультиисточниковая система скиллов (swissknifeman ДВУМЯ каналами — connect/marketplace и vendor/физ.перенос через .swissknifeman/config.json — + собственные local-скиллы; Laravel Boost только как MCP, не как канал скиллов; карта в skills-lock.json) и двусторонний синк документации с Brain-валтом. Используй, когда нужно «добавить проекту скиллы разработчика/проектировщика», установить/выбрать скиллы (ВСЕГДА спрашивай канал connect vs vendor), поменять набор, разрулить источники, или синхронизировать docs/ с Brain. Дополняет ecosystem-integration (онбординг в хаб) операционным слоем skills+docs.
---

# Раннбук: скиллы проекта (мультиисточник) + doc-sync (brain)

Этим управляешь ты. Хаб maind (онбординг/память/граф) — отдельно, см. [ecosystem-integration].
Этот скилл — про **скиллы ролей проекта** (из нескольких источников) и **синхронизацию документации**.

## Скиллы проекта — КОМПОЗИЦИЯ источников (не один swissknifeman)

Скиллы проекта приходят из **нескольких независимых источников**, у каждого свой конфиг, и они
**мирно складываются в один набор**. Это by design — гибкая система, а не «только swissknifeman».

| Источник | Свой конфиг | Что это |
|:--|:--|:--|
| **swissknifeman** | `skills.json` (реестр) → **два канала установки** (см. ниже) | курируемые бакеты/скиллы ролей |
| **Laravel Boost** | `boost.json` (`mcp`/`guidelines`/`skills[]`) | **только MCP + guidelines** — как канал скиллов НЕ используем (см. ниже) |
| **local** (свои) | — (просто папка `.claude/skills/<name>/`) | твои собственные / раскатанные из другого хаба (напр. `ecosystem-mcp` от maind) |

### ⚠️ swissknifeman ставит скиллы ДВУМЯ каналами — СПРОСИ пользователя, каким

Перед установкой/добавлением скиллов из swissknifeman **всегда уточни у пользователя канал** (это
не дефолт — выбор меняет, что попадёт в репо и какой гранулярностью управляешь):

| Канал | Команда | Что делает | Гранулярность | В репо |
|:--|:--|:--|:--|:--|
| **connect** (marketplace) | `skiller connect` | включает плагины-бакеты через `enabledPlugins` в `.claude/settings.local.json` | **только бакет целиком** | файлы скиллов НЕ копируются |
| **vendor** (физ. перенос) | `skiller sync` | копирует выбранные скиллы в `.claude/skills/`, пишет `skills-lock.json` (`managed`) | **отдельные скиллы** (include/buckets/exclude) | да, видно и коммитится |

- **connect** — когда фиксация в репо не нужна и устраивает «весь бакет».
- **vendor** — когда нужно: видеть скиллы в репо, выбрать ровно нужные позиции из разных областей,
  обновлять из библиотеки по lock. Конфиг — `.swissknifeman/config.json` (`mode: "vendor"`,
  `include`/`buckets`/`exclude`). См. swissknifeman docs → гайд «Vendor-режим (sync)».

> Спрашивай через AskUserQuestion: «connect (плагины-бакеты, не в репо)» vs «vendor (физический
> перенос конкретных скиллов в репо + lock)». Рекомендация по умолчанию — **vendor**, если
> пользователь хочет контроль над набором и фиксацию в репозитории.

**`skills-lock.json`** (коммитится, как `composer.lock`) пишут **две** команды — какая, зависит от канала:
- **vendor**: `skiller sync` пишет lock сам — на каждый перенесённый скилл запись
  `source: swissknifeman` + **`managed: true`** + `sha256`. При синке выбывшие из конфига `managed`
  удаляются; **чужие записи (не `managed`) не трогаются**.
- **connect / смешанный**: `skiller lock` (read-only композитор) — сканирует установленное
  (`.claude|.cursor|.ai/skills`) ∪ `boost.json::skills[]` и проставляет `source`: имя в реестре →
  `swissknifeman` (wins); в `boost.json::skills` → `laravel-boost`; иначе → `local`. Конфликт (имя в
  нескольких) **не теряется**: победитель в `source`, проигравший в `also_in`. **Boost не «съедает»
  local-скиллы только потому, что подключён.**

В vendor-режиме арбитр — это `sync` (config → managed-lock). `lock` нужен для connect/смешанных
проектов. Собственные local-скиллы **легитимны** — пиши их, когда нужен проектный контекст, которого
нет в библиотеке (`sync` их не перетирает — они не `managed`).

### Бакеты swissknifeman (роли)

| Роль | Бакет | Что внутри (примеры) |
|:--|:--|:--|
| **Проектировщик** | `architect` | architecture, api-design, data-schema, security-design, tech-stack-selection, observability-design |
| **Разработчик (PHP/Laravel)** | `php` | laravel, laravel-best-practices, laravel-testing, database, modular-architecture, repositories, static-analysis |
| **Фронт** | `frontend` | vue-composition-api, pinia-stores, vitest, tailwind-conventions, inertia-vue, vite-* |
| Прочее | `quality` `devops` `operator` `system` `founder` `pm` `general` | тесты/CI/инциденты/конвенции/бизнес |

**Профили** (`profiles/*.json`) = готовые наборы бакетов под тип проекта:
- `laravel-project` → `system, architect, php, devops, quality, operator` (без фронта!)
- `php-package`, `obsidian-vault`, `standalone`.

CLI — `swissknifeman` (запускать из каталога проекта; корень ищется вверх от CWD):

```bash
skiller status                       # что подключено: профиль, бакеты, канал
# --- канал CONNECT (плагины-бакеты, не в репо) ---
skiller connect --profile laravel-project          # подключить по профилю
skiller connect --plugins a,b,c                    # точный набор бакетов (перезаписывает enabledPlugins)
skiller connect --plugins ... --dry-run            # предпросмотр (сохраняет permissions/bypass)
# --- канал VENDOR (физ. перенос конкретных скиллов в репо) ---
#   1) создать .swissknifeman/config.json (mode:vendor, include/buckets/exclude)
skiller sync --dry-run               # план: +add ~update -remove =keep
skiller sync                         # применить (managed-скиллы в .claude/skills/ + lock)
skiller sync --force                 # перетереть занятый чужим путь версией из библиотеки
# --- общее ---
skiller integrate --bundle recommended --yes       # визард: спросит канал (connect/vendor) + хуки/память/hub
skiller lock [--dry-run]             # карта источников для connect/смешанных (read-only композитор)
skiller update                       # обновить подключение проекта
```

**Laravel Boost** — держим как **MCP-сервер** (database-query/tinker/logs/docs) и при желании его
guidelines, но **НЕ как канал скиллов**. В `boost.json`: `"mcp": true`, `"guidelines": true` (опц.),
`"skills": []`. Его прежние скиллы заменяй прямыми аналогами из библиотеки через vendor (`frontend/
inertia-vue`, `frontend/tailwind-conventions`, `frontend/wayfinder` и т.п.). Нужный, но отсутствующий
в библиотеке Boost-скилл — импортируй в неё как external. MCP-сервер `laravel-boost` остаётся в
`.mcp.json` (его дописывает maind при онбординге, если у проекта `boost.json`).

**Добавить роль к проекту** (сначала спроси канал, см. выше):
- **connect**: `connect --plugins <текущие>,<новый>` (текущие — в `skiller status` /
  `enabledPlugins`). Сохраняет `permissions`/`defaultMode` (bypass, см. [[auto-approve-bypass]]).
  После — рестарт сессии или `/plugin marketplace update swissknifeman`.
- **vendor**: допиши скиллы в `.swissknifeman/config.json` (`include`/`buckets`) → `skiller sync`.
  Скиллы появятся в `.claude/skills/` сразу (рестарт нужен, чтобы Claude их подхватил).

> Типичный кейс «дай проекту скиллы разработчика+проектировщика»: laravel-project уже даёт `php`
> (разработчик) + `architect` (проектировщик). Если фронт на Vue/Nuxt — добавь `frontend`.

## Doc-sync: документация проекта ↔ Brain-валт

Двусторонний синк `docs/` и `docs-public/` между Brain-валтом и код-репо — CLI `~/Vaults/Brain/bin/brain`
(git 3-way merge, merge-base в `~/.brain/sync/`). Подробности — [[brain-doc-sync]]. Кратко:

```bash
~/Vaults/Brain/bin/brain status <proj>             # состояние пары папок
~/Vaults/Brain/bin/brain sync all <proj> --dry-run # предпросмотр слияния
~/Vaults/Brain/bin/brain sync all <proj>           # слить (первый раз = seed из валта)
```

Условие: в control-ноте валта (`<Name>.md`) должен быть frontmatter `repo: ~/projects/<path>` —
иначе `brain` не видит проект.

## Порядок «дать проекту всё» (полный)

1. Онбординг в хаб — [ecosystem-integration] (`maind onboard …`, namespace, health=connected).
2. Скиллы ролей — **спроси канал** (connect/vendor), затем:
   - connect: `connect --plugins …` (architect+php[+frontend]); или
   - vendor: `.swissknifeman/config.json` (include/buckets) → `skiller sync`.
3. (Laravel) Boost — как **MCP** (`composer require laravel/boost --dev`, `boost.json: mcp:true,
   skills:[]`); скиллы Boost НЕ ставим — берём аналоги из библиотеки (vendor).
4. Зафиксировать карту — vendor: уже в `skills-lock.json` от `sync`; connect/смешанный: `skiller lock`.
5. Doc-sync — `repo:` в control-ноту + `brain sync all <proj>`.
6. Авто-аппрув без промптов — bypass, см. [[auto-approve-bypass]].
7. Проверка: `skiller status` · `cat skills-lock.json` · `maind health --project <id>` · `brain status <proj>`.

## Ссылки

- [ecosystem-integration] — подключение проекта к хабу mAInd (память/граф/MCP).
- [maind-overview] — устройство хаба и namespace'ов.
- память: [[brain-doc-sync]] · [[auto-approve-bypass]].
