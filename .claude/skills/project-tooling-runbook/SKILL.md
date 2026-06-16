---
name: project-tooling-runbook
description: Раннбук управления инструментами проектов экосистемы — мультиисточниковая система скиллов (swissknifeman-бакеты + Laravel Boost + собственные local-скиллы, склеиваются через skills-lock.json) и двусторонний синк документации с Brain-валтом. Используй, когда нужно «добавить проекту скиллы разработчика/проектировщика», поменять набор плагинов, разрулить источники скиллов, или синхронизировать docs/ проекта с Brain. Дополняет ecosystem-integration (онбординг в хаб) операционным слоем skills+docs.
---

# Раннбук: скиллы проекта (мультиисточник) + doc-sync (brain)

Этим управляешь ты. Хаб maind (онбординг/память/граф) — отдельно, см. [ecosystem-integration].
Этот скилл — про **скиллы ролей проекта** (из нескольких источников) и **синхронизацию документации**.

## Скиллы проекта — КОМПОЗИЦИЯ источников (не один swissknifeman)

Скиллы проекта приходят из **нескольких независимых источников**, у каждого свой конфиг, и они
**мирно складываются в один набор**. Это by design — гибкая система, а не «только swissknifeman».

| Источник | Свой конфиг | Что это |
|:--|:--|:--|
| **swissknifeman** | `skills.json` (реестр) + marketplace-плагины | курируемые бакеты ролей |
| **Laravel Boost** | `boost.json` (`skills[]`) | Laravel сам ставит свои скиллы/guidelines (`php artisan boost:install`) |
| **local** (свои) | — (просто папка `.claude/skills/<name>/`) | твои собственные / раскатанные из другого хаба (напр. `ecosystem-mcp` от maind) |

**Арбитр — `swissknifeman lock`** → пишет в проект `skills-lock.json` (коммитится, как `composer.lock`):
- universe = установленные скиллы (`.claude|.cursor|.ai/skills`) ∪ `boost.json::skills[]`;
- `source`: имя в реестре swissknifeman → `swissknifeman` (wins); имя в `boost.json::skills` → `laravel-boost`;
  иначе → `local`. **Boost не «съедает» local-скиллы только потому, что подключён.**
- конфликт (имя в нескольких) **не теряется**: победитель в `source`, проигравший в `also_in`.

Прогоняй `swissknifeman lock` после изменения любого источника (добавил бакет / `boost:install` /
свой скилл) — карта пересоберётся. `--dry-run` покажет состав без записи. Собственные local-скиллы
**легитимны** — пиши их, когда нужен проектный контекст, которого нет в бакетах/Boost.

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
swissknifeman status                       # что подключено: профиль, бакеты, канал
swissknifeman connect --profile laravel-project          # подключить по профилю
swissknifeman connect --plugins a,b,c                    # точный набор бакетов (перезаписывает enabledPlugins)
swissknifeman connect --plugins ... --dry-run            # предпросмотр (сохраняет permissions/bypass)
swissknifeman integrate --bundle recommended --yes       # визард: скиллы+хуки+память+hub
swissknifeman lock [--dry-run]             # пересобрать skills-lock.json (карта всех источников)
swissknifeman update                       # обновить подключение проекта
```

Laravel Boost (если проект на Laravel и нужны его скиллы/guidelines) — отдельный источник, ставится
из проекта: `composer require laravel/boost --dev` → `php artisan boost:install --skills --guidelines`
(**без `--mcp`** — `.mcp.json` управляется maind, не дай Boost'у его переписать). После — `swissknifeman lock`.

**Добавить роль к проекту** = добавить бакет: `connect --plugins <текущие>,<новый>`. Текущие смотри
в `swissknifeman status` (или `enabledPlugins` в `.claude/settings.local.json`). `connect` сохраняет
`permissions`/`defaultMode` (в т.ч. bypass, см. [[auto-approve-bypass]]). После — рестарт сессии
или `/plugin marketplace update swissknifeman`.

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
2. Скиллы ролей — бакеты swissknifeman: `connect --plugins …` (architect+php[+frontend]).
3. (Laravel) Boost — `composer require laravel/boost --dev` + `boost:install --skills --guidelines`.
4. Зафиксировать карту источников — `swissknifeman lock` → `skills-lock.json` в репо.
5. Doc-sync — `repo:` в control-ноту + `brain sync all <proj>`.
6. Авто-аппрув без промптов — bypass, см. [[auto-approve-bypass]].
7. Проверка: `swissknifeman status` · `cat skills-lock.json` · `maind health --project <id>` · `brain status <proj>`.

## Ссылки

- [ecosystem-integration] — подключение проекта к хабу mAInd (память/граф/MCP).
- [maind-overview] — устройство хаба и namespace'ов.
- память: [[brain-doc-sync]] · [[auto-approve-bypass]].
