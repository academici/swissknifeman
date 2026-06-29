---
name: project-tooling-runbook
description: Раннбук управления инструментами проектов экосистемы — мультиисточниковая система скиллов (swissknifeman ДВУМЯ каналами — connect/marketplace и vendor/физ.перенос через .swissknifeman/config.json — + собственные local-скиллы; Laravel Boost только как MCP, не как канал скиллов; карта в skills-lock.json) и двусторонний синк документации с Brain-валтом. Используй, когда нужно «добавить проекту скиллы разработчика/проектировщика», установить/выбрать скиллы (ВСЕГДА спрашивай канал connect vs vendor), поменять набор, разрулить источники, настроить роли/агенты проекта (agent-packs: субагенты + workflow + review-gate через harness — ОТДЕЛЬНО от скиллов), синхронизировать docs/ с Brain, ИЛИ когда пишешь/правишь конфиг с локальными абсолютными путями или секретами (.mcp.json любого провайдера, .cursor/.vscode/mcp.json, .claude/*) — гигиена: индирекция через .env либо gitignore реального + синхронный .example с плейсхолдерами (как .env↔.env.example). Дополняет ecosystem-integration (онбординг в хаб) операционным слоем skills+docs.
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
| **connect** (marketplace) | `skiller connect` | включает плагины-бакеты через `enabledPlugins` в `.claude/settings.local.json`; `extraKnownMarketplaces` указывает на **локальный путь к реестру swissknifeman** | **только бакет целиком** | файлы скиллов НЕ копируются |
| **vendor** (физ. перенос) | `skiller sync` | копирует выбранные скиллы в `.claude/skills/`, пишет `skills-lock.json` (`managed`) | **отдельные скиллы** (include/buckets/exclude) | да, видно и коммитится |

- **connect** — когда фиксация в репо не нужна и устраивает «весь бакет». ⚠️ **Требует доступа к
  реестру swissknifeman** (marketplace = локальный путь): у разработчика без репо swissknifeman
  плагины не подключатся — скиллов он не увидит. Годится для твоего окружения / внутренней экосистемы.
- **vendor** — когда нужно: **отдать скиллы внешним разработчикам, у которых нет доступа к
  swissknifeman** (файлы лежат в самом репо проекта); видеть скиллы в репо; выбрать ровно нужные
  позиции из разных областей; обновлять из библиотеки по lock. Конфиг — `.swissknifeman/config.json`
  (`mode: "vendor"`, `include`/`buckets`/`exclude`). См. swissknifeman docs → гайд «Vendor-режим (sync)».

> **Два конфига, не путать:** `.swissknife.json` (connect + legacy vendor, bucket-granular) vs
> `.swissknifeman/config.json` (vendor `sync`, skill-granular). Канон —
> swissknifeman docs `guide/skills-architecture.md` §6.

> Спрашивай через AskUserQuestion: «connect (плагины-бакеты, не в репо; нужен доступ к реестру)» vs
> «vendor (физ. копии скиллов в репо + lock; работает у внешних разработчиков)». Рекомендация по
> умолчанию — **vendor**, если проект отдают сторонним разработчикам или нужен контроль набора и
> фиксация в репозитории.

> **Только скиллы.** Выбор канала касается ТОЛЬКО скиллов (у них нет другого функционала, кроме
> раздачи файлов). Память / граф / MCP-инструменты хаба mAInd настраиваются как обычно независимо
> от канала скиллов.

**Канал спрашивается и на онбординге** (`swissknifeman setup` / `maind onboard` / `skiller integrate`):
- `swissknifeman setup <p>` и `maind onboard <p>` интерактивно спрашивают `connect/vendor` (флаг
  `--skills-channel connect|vendor` для неинтерактива; дефолт `connect`).
- `skiller integrate` принимает `--skills-channel`; при `vendor` для Claude-проекта **роутится в
  современный `sync`** (генерит `.swissknifeman/config.json` из профиля → физ. копии в `.claude/skills/`).
- Канал `vendor` для **Cursor/Gemini** (`.ai/.cursor/skills`) — это отдельная legacy-команда
  `skiller vendor --agent cursor|generic` (для `--agent claude` deprecated; используй `sync`).

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
| **Разработчик (PHP/Laravel)** | `php` (ядро) + `laravel-*` | `php`=laravel/structure/DI/database/repositories/patterns/static-analysis; feature-бакеты: `laravel-testing`, `laravel-filament`, `laravel-livewire`, `laravel-data-layer`, `laravel-auth`, `laravel-architecture`, `laravel-extras`; `php-packages` (разработка пакетов); `azguard`/`botkit` (свои пакеты) |
| **Фронт** | `frontend` (ядро) + `frontend-*` | ядро: web-design-guidelines/document-writer/filepond; feature-бакеты: `frontend-{vue,nuxt,tailwind,naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}` |
| Прочее | `quality` `devops` `operator` `system` `founder` `pm` `general` | тесты/CI/инциденты/конвенции/бизнес |

**Профили** (`profiles/*.json`) = готовые наборы бакетов под тип проекта (линяный дефолт):
- `laravel-project` → `system, architect, php, laravel-testing, laravel-auth, laravel-data-layer, devops, quality, operator` (Filament/Livewire — точечно бакетом или пресетом `laravel-admin`).
- `php-package`, `obsidian-vault`, `standalone`.

**Пресеты** (`presets/*.json`) = именованные сквозные стеки поверх бакетов (vendor): `laravel-admin`,
`laravel-enterprise`, `laravel-inertia`, `laravel-livewire-stack` + кластеры frontend/architect/pm/general/quality.
В `.swissknifeman/config.json`: `presets: [...]` (+ `include`/`exclude`). Подробно — `docs/guide/presets.md`.

### ⚠️ Подбирай ОПТИМАЛЬНЫЙ набор под проект — не дамп «всё подряд»

При постановке задачи «настроить проект» (онбординг, добавить/поменять скиллы или плагины) **подбирай
ровно релевантный набор** под стек и роль проекта, а не включай все бакеты скопом. Лишние роли
(`php`/`python`/`mobile` на чистом фронте, фронт на backend-пакете и т.п.) — шум: засоряют контекст
и обесценивают курирование.

- Стек **определяет** набор: фронт (Nuxt/Vue) → `frontend (+ general, quality, devops, system, roles)`;
  Laravel-сервис → профиль `laravel-project` (`php, architect, …` без фронта); пакет → `php-package`.
- Бери **профиль** как основу, потом добавляй/убирай точечно под конкретный проект.
- **Если оптимальный набор неочевиден** (гибридный/неясный стек, несколько ролей, спорные бакеты) —
  **СПРОСИ пользователя** через AskUserQuestion (предложи 2-3 курированных варианта), не угадывай и
  не включай по максимуму «на всякий случай».
- **Нераспознанный тип** (autodetect → `standalone`): `skiller connect/vendor` теперь ставит
  МИНИМАЛЬНОЕ ядро + печатает warn (а не «всё подряд»); укажи `--profile <type>` явно. «Поставить
  всё» доступно только осознанно — `--profile standalone`.

> **Гранулярность и размещение** (general=кросс-стек/CORE, stack→stack-бакет, project→project-local,
> connect=грубо/vendor=тонко, lean SKILL.md) — канон в skiller docs `guide/skill-taxonomy.md`.
> Полное дерево всех слоёв настройки (память/ns/канал/окружение/граф) с ветками — канонический
> документ maind [«Дерево решений: настройка проекта»](../../../packages/maind/docs/guide/onboarding-decision-tree.md).

CLI — `swissknifeman` (запускать из каталога проекта; корень ищется вверх от CWD):

```bash
skiller status                       # что подключено: профиль, бакеты, канал; ⚠ ловит ДУБЛЬ КАНАЛОВ
                                     #   (бакет и в плагинах, и вендорен) — доступно и как swissknifeman skills status
# --- канал CONNECT (плагины-бакеты, не в репо) ---
skiller connect --profile laravel-project          # подключить по профилю
skiller connect --plugins a,b,c                    # точный набор бакетов (перезаписывает enabledPlugins)
skiller connect --plugins ... --dry-run            # предпросмотр (сохраняет permissions/bypass)
# --- канал VENDOR (физ. перенос конкретных скиллов в репо) ---
skiller init                         # создать .swissknifeman/config.json (mode:vendor) из автодетекта
#   (или вручную: include/buckets/exclude; $schema даёт автодополнение в редакторе)
skiller sync --dry-run               # план: +add ~update -remove =keep
skiller sync                         # применить (managed-скиллы в .claude/skills/ + lock)
skiller sync --force                 # перетереть занятый чужим путь версией из библиотеки
# --- общее ---
skiller integrate --bundle recommended --yes       # визард: спросит канал (connect/vendor) + хуки/память/hub
skiller integrate --skills-channel vendor --yes    # vendor без вопроса → sync в .claude/skills (для внешних)
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

## Агенты/роли проекта (agent-packs) — ОТДЕЛЬНО от скиллов

Скиллы (connect/vendor) дают **знания**, но НЕ ставят **субагентов и workflow**. Роли/агенты — это
отдельная подсистема **`harness agent-packs`**: ставит `.claude/agents/*`, `.claude/workflows/*`,
review-gate хук (SubagentStop) и `.claude/rules/*`. **Без этого шага большая задача НЕ развернётся
в ролевое «slice → test → review»** — будет только встроенный `/code-review` и ad-hoc субагенты.
Поэтому «настроить проект» = скиллы **И** agent-packs (не одно вместо другого).

| Тип пака | Паки | Что ставит |
|:--|:--|:--|
| **стек** (детект по стеку) | `backend-laravel` (artisan/composer), `node-frontend` (vite/nuxt), `python-backend` (pyproject), `dart-flutter` (pubspec) | dev-loop субагенты slice-builder/test-writer/reviewer (+component-builder/type-checker), workflow, review-gate, rules |
| **роль** (поверх стека) | `role-tech-lead`, `role-maintainer`, `role-cto`, `role-founder` | персона-субагенты (review-gatekeeper/sprint-planner; issue-triager/contribution-reviewer/release-conductor; …) |

```bash
harness agent-packs list                          # каталог паков + detect
harness agent-packs render --pack <stack> --target . --auto      # детект стека → субагенты + review-gate
harness agent-packs render --pack backend-laravel --pack role-tech-lead --target . --auto \
        --answer TEST_DB=<имя> --answer CHECK_CMD='<статик-чек>'  # стек+роль, override интервью
harness agent-packs doctor  --target .            # проверка; lock — .claude/agent-pack.lock.json
harness agent-packs upgrade --pack <p> --target . # бережный апгрейд (conflict → *.pack-new)
```

> **Автоматический путь:** полный `maind onboard` / `swissknifeman setup` с **типом проекта**
> (`laravel-project`/`node-frontend`/`python-backend`/`dart-flutter`) ставит стек-пак САМ из профиля
> (`packages/skiller/profiles/<type>.json: agent_pack`; роли — `config.role_packs` по `project.roles`).
> Ручной `harness agent-packs render` нужен, когда проект настраивали ВНЕ полного онбординга (напр.
> ручным `connect`) или у его записи в `projects.json` нет `type` — тогда шаг agent-packs легко
> пропустить (типичная причина «у проекта нет ролей/код-ревью»).

> **Стек-пак ≠ полное совпадение инфры.** Отрендеренные агенты несут допущения origin-пака (PHP-бинарь,
> тип БД, защищённый `.env`, Pest/PHPUnit). После install **сверь и поправь** отрендеренные
> `.claude/agents/*` + `workflow` + `rules/tests.md` под реальную инфру проекта (раннер, MySQL/Postgres,
> тестовая БД, фреймворк тестов). `requires.skills` пака должны быть покрыты подключённым набором
> (connect/vendor). Деталь подсистемы (структура пака, шаблонизация, lock/upgrade) — скилл [harness-operations].

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

### Doc-папки: имя ↔ видимость развязаны (читается из конфига, не из имени)

Папка документации — модель `{id, vault, repo, visibility}`: имена сторон vault/repo могут
отличаться, а **статус** (`public`|`private`) независим от имени. Источник истины — frontmatter
control-ноты Brain; maind кэширует в `docs_folders`. Дефолт `visibility` **по типу проекта**:
**пакет/библиотека** → `docs` public (публичная VitePress-док-ция); **продукт** (закрытый
сервис/фронт) → `docs` private (внутренняя). Публичная папка не несёт `[[wikilinks]]` (гейт).

Задать/переопределить — плоские ключи во frontmatter (parser наивный, вариант A):
```yaml
docs_folders: docs-public        # CSV vault-имён (нет → дефолт docs+docs-public)
docs_public:  docs-public        # CSV vault-имён, что публичны (опц.)
docs_repo_map: docs-public=docs  # CSV пар vault=repo: в валте docs-public, в репо публикуем docs
```
Старый плоский `["docs","docs-public"]` мигрируется на лету. Деталь — Brain
`docs/workflow/docs-watcher.md` (модель папки) + `brain-cli.md` (wikilink-гейт по visibility).

> **Внутренний AI-гайд агент-пака** (`subagents-and-workflows.md`) кладётся в **`.claude/guidelines/`**,
> НЕ в `docs/`: это артефакт для агентов, не публичная документация (иначе утёк бы в публикацию и
> в Brain-валт). Стек-паки harness (backend-laravel и пр.) пишут его туда по дефолту (`DOCS_DIR`).
> `.claude/guidelines/` — коммитится (не gitignore); `docs/` остаётся под реальную документацию.

## Гигиена machine-specific конфигов (gitignore + синхронный `.example`)

Конфиг, в который «запекается» **абсолютный локальный путь** (`/home/<user>/…/bin/maind`, путь
проекта в Serena), **секрет** (прокси-креды, токен) или **личный хост:порт**, нельзя коммитить как
есть: у другого разработчика/на CI путь иной, секрет утечёт в историю git. Касается **всех** MCP-конфигов
любого провайдера (`.mcp.json`, `.cursor/mcp.json`, `.vscode/mcp.json`) и machine-specific содержимого
в `.claude/` (`settings.local.json` и т.п.). Две стратегии, в порядке предпочтения:

**1) Индирекция (предпочтительно) — конфиг остаётся портируемым и коммитится.** Machine-specific
значение выноси в `.env` (gitignored), а в конфиге ссылайся на него: `${VAR}` (Claude Code раскрывает
env в `.mcp.json`) или тонкий враппер, читающий `.env` на старте. Тогда сам конфиг не содержит ни
путей, ни секретов → его можно коммитить, `.example` не нужен.
> Пример (playwright-прокси): секрет — только в `.env` (`PLAYWRIGHT_MCP_PROXY_SERVER=…`), а сервер в
> `.mcp.json` грузит его враппером `bash -c 'export …=$(grep … .env); exec npx @playwright/mcp'`.
> Переменную документируй в `.env.example` (пустой плейсхолдер).

**2) gitignore + `.example` (fallback) — когда значение обязано лежать прямо в файле** (индирекция
невозможна):
- реальный файл → в `.gitignore` (уже трекался — `git rm --cached <файл>`);
- рядом коммитится `<файл>.example` с **плейсхолдерами**: `<ABS_PATH_TO_SWISSKNIFEMAN>/packages/maind/bin/maind`,
  `<REPO_ROOT>`, `<TOKEN>`;
- **синхронизация обязательна и одновременна**: меняешь реальный файл (добавил MCP-сервер, поменял
  аргументы/путь) — в **том же** изменении правишь `.example`. Та же дисциплина, что `.env` ↔
  `.env.example`, не «когда-нибудь потом».

**Что machine-specific** (→ индирекция или `.example`): абсолютные пути `/home/<user>/…`, `/Users/…`;
секреты/токены/креды; личные хост:порт. **Что портируемо** (коммить как есть): относительные команды
(`php artisan boost:mcp`), значения, одинаковые у всех.

> Перед коммитом: `git diff --cached` по `*.json`/`.mcp.json`/`.claude/*` на абсолютные пути (`/home/`,
> `/Users/`) и секреты. Нашёл — вынеси в `.env` (стратегия 1) либо gitignore + обнови `.example` (стратегия 2).

> **Механизм vs дисциплина.** Пока это **дисциплина агента**: maind при `deploy`/`sync` пишет реальный
> `.mcp.json` с абсолютными путями, но `.example`/gitignore сам не ведёт. Если ловишь это повторно —
> кандидат на доработку maind (`lib/maind/mcpconfig.py`/`deploy.py`: эмитить `.example` + дописывать
> `.gitignore`), маршрутизируй через [field-feedback-loop].

## Порядок «дать проекту всё» (полный)

Настройка проекта = **четыре слоя**: скиллы (знания) **+ agent-packs (роли/агенты)** + окружение
harness (permissions/mcp/hooks) + maind (память/граф). Порядок обязан коснуться всех четырёх:

1. Онбординг в хаб — [ecosystem-integration] (`maind onboard …`, namespace, health=connected).
   Раскатывает слои **MCP + память/граф** (демон, серверы в `.mcp.json`, граф/код-граф).
2. Скиллы ролей — **спроси канал** (connect/vendor), затем:
   - connect: `connect --plugins …` (architect+php[+frontend]); или
   - vendor: `.swissknifeman/config.json` (include/buckets) → `skiller sync`.
3. **Агенты/роли** — `harness agent-packs render --pack <stack> [--pack <role>] --target . --auto`
   (детект стека → субагенты + workflow + review-gate). **Сверь отрендеренные агенты с инфрой проекта.**
   Без этого шага ролевого «slice→test→review» не будет — см. раздел «Агенты/роли» выше.
4. **MCP / память / граф** — раскатаны онбордингом; пере-раскатать точечно:
   `maind sync --only mcp,memory,graph,code-graph --project <id>`. (Laravel) Boost — как **MCP**
   (`composer require laravel/boost --dev`, `boost.json: mcp:true, skills:[]`); скиллы Boost НЕ ставим.
5. Зафиксировать карту — vendor: уже в `skills-lock.json` от `sync`; connect/смешанный: `skiller lock`.
6. Doc-sync — `repo:` в control-ноту + `brain sync all <proj>`.
7. Авто-аппрув без промптов — bypass, см. [[auto-approve-bypass]].
8. **Коммит-гигиена конфигов** — `.mcp.json`/`.claude/*` с абсолютными путями или секретами:
   индирекция через `.env` либо gitignore + синхронный `.example` (см. «Гигиена machine-specific конфигов»).
9. **Проверка — одной командой:** `swissknifeman status <id>` (единый 4-слойный инвентарь + drift→fix);
   `--all --json` для агента. Плюс `brain status <proj>` (doc-sync).

## Control-surface: статус → точечный re-sync

Состояние всех 4 слоёв проекта — одной командой, и точечная починка каждого. Канон —
[Control-surface проекта](../../../docs/control-surface.md) (умбрелла-док).

```bash
swissknifeman status <id>            # 4 слоя: status·mcp[a/m/c]·skills·packs·trust + drift→fix
swissknifeman status --all --json    # весь флот машиночитаемо (агент читает .projects[].fixes)
maind sync --project <id> --only <cap>   # точечный re-sync: mcp|memory|graph|code-graph|agent-pack|…
```

Цикл: `status --json` → читаешь `fixes[]` (каждый = `{layer, issue, fix}`) → выполняешь точную
команду (обычно `maind sync --only <cap>`), а **не** «пере-настрой всё». Машиночитаемо по слоям:
`skiller status --json` (скиллы) · `harness agent-packs doctor --target . --json` (роли) ·
`maind verify --json` (пруф памяти/графа).

## Ссылки

- [Control-surface проекта](../../../docs/control-surface.md) — единый статус 4 слоёв + точечный re-sync.
- [ecosystem-integration] — подключение проекта к хабу mAInd (память/граф/MCP).
- [harness-operations] — подсистема agent-packs (роли/агенты), пресеты permissions/mcp/hooks.
- [maind-overview] — устройство хаба и namespace'ов.
- память: [[brain-doc-sync]] · [[auto-approve-bypass]].
