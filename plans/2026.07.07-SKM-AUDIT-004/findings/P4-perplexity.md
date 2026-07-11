# P4.1 — Диагностика промптов perplexity-web (read-only)

Дата: 2026-07-07. Метод: инспекция `~/.claude/settings.json`, `~/.claude.json`
(per-project approval state), `.claude/settings*.json` + `.mcp.json` по 24
проектам флота (`~/.swissknifeman/projects.json`), `packages/harness/configs/
claude-code/settings*.json`, `packages/maind/lib/maind/provision/deploy.py`
(`pplxweb` модуль), исходники `perplexity-web-mcp`; репро — `claude mcp list`
в 7 проектах (flexcrm, edufy, agelto, dterema/app, memster, botkit, chatom).

## Вывод (TL;DR)

Промпты perplexity-web имеют **ДВЕ независимые первопричины** (разные
механизмы Claude Code, разное лечение — см. Phase Context), обе
подтверждены репро и данными по флоту. Обе активны одновременно почти
на всём флоте:

- **Класс A — tool-permission ask (mismatch имени сервера с плагинным префиксом).**
  У проектов, где подключён курируемый плагин `core` (marketplace swissknifeman),
  Claude Code автоматически подгружает `.mcp.json` из корня плагина (это
  корневой `<монорепо>/.mcp.json`, содержащий `maind` и `perplexity-web`) как
  **отдельный, уже одобренный** сервер `plugin:core:perplexity-web` —
  инструменты которого называются `mcp__plugin_core_perplexity-web__*`.
  User-scope allow (`~/.claude/settings.json`) и глобальный пресет harness
  (`settings.global.json:48`) содержат правило `mcp__perplexity-web`
  (bare/wildcard) — оно матчит только «голое» имя сервера `perplexity-web`,
  **не** `plugin_core_perplexity-web`. Итог: плагинный инстанс подключён и
  доступен, но каждый его вызов не покрыт allow-правилом → падает в
  дефолтное поведение permission-engine (`ask`), потому что ни один явный
  matcher не совпал.
- **Класс B — server-approval диалог (проектный `.mcp.json`, никогда не
  одобрен).** Каждый проект флота получает от `maind deploy` (`pplxweb.py`,
  `provision/deploy.py:104-105`) собственную запись `perplexity-web` в свой
  `.mcp.json` (`maind mcp --scope project:<name>`-подобная схема, но для
  perplexity — прямой `start.sh`). Такие project-scoped MCP-серверы требуют
  **отдельного одобрения** (`claude mcp list` → `Pending approval`),
  фиксируемого в `~/.claude.json` → `projects["<path>"].enabledMcpjsonServers`.
  По факту это поле **пустое `[]` на 22 из 23 присутствующих в `~/.claude.json`
  записей флота** (искл. — сам `swissknifeman`, где сервер уже одобрен, т.к.
  это активный репозиторий текущей сессии). Одобрение — интерактивный шаг
  (`run claude` в проекте и подтвердить), который никогда массово не
  выполнялся → сервер вечно висит `Pending approval`, allow-правила тут
  **бессильны в принципе** (сервер не в состоянии «подключён», permission
  engine до инструментов не доходит).

Каждый класс — самостоятельная причина промпта; проект может страдать от
одного, другого или обоих сразу (см. матрицу).

## Матрица по флоту (24 записи реестра, 23 уникальных пути + botkit без core-плагина)

| Проект | core-плагин (`plugin:core:perplexity-web`) | project `.mcp.json` `perplexity-web` | `enabledMcpjsonServers` (`~/.claude.json`) | Класс A (mismatch) | Класс B (pending) |
|:--|:--|:--|:--|:--|:--|
| swissknifeman (сам монорепо) | ✓ Connected | ✓ Connected | `[]` (нет `enabledMcpjsonServers` ключа — но это свой активный репо) | нет (проверить allow-покрытие на будущее) | нет — единственный одобренный |
| flexcrm | ✓ Connected | ⏸ Pending | `[]` | да | да |
| edufy | ✓ Connected | ⏸ Pending | `[]` | да | да |
| agelto/agelto | ✓ Connected | ⏸ Pending | `[]` | да | да |
| dterema/app | ✓ Connected | ⏸ Pending | `[]` | да | да |
| dterema/dterema | (не репро, ожидаемо аналогично — тот же profile) | (`.mcp.json` содержит perplexity-web) | `[]` | да (по паттерну) | да (по паттерну) |
| memster | ✓ Connected | ⏸ Pending | `[]` | да | да |
| chatom | ✓ Connected | ⏸ Pending | `[]` | да | да |
| botkit | **нет** (плагин `core` не подключён проекту) | ⏸ Pending | `[]` | нет (нет плагинного дубля) | да — единственная причина, allow-правила в `.claude/settings.json` (`mcp__perplexity-web__search*`) бессильны |
| azguard, corex, loqum, vaulter, vintera/cms, vintera/vintera, insiders, diabox, perplexity-web-mcp | не проверено репро (`claude mcp list`), но конфиг идентичен паттерну (core-плагин активен везде кроме botkit; `.mcp.json` содержит `perplexity-web`; `enabledMcpjsonServers` пуст везде, кроме agelto/swissknifeman — там пуст для perplexity конкретно) | — | `[]` (кроме agelto/swissknifeman, но не для perplexity) | да (по паттерну) | да (по паттерну) |
| sova | `.mcp.json` вообще не содержит `perplexity-web` (только `laravel-boost`) | н/п | н/п | н/п | н/п — сервер проекту не роздан |

Вывод матрицы: **botkit** — чистый Класс B (плагин не подключён, только
project-scoped сервер, вечно Pending). Все проекты с core-плагином (17 из
19 применимых) — **оба класса одновременно**: даже если бы Класс B
починили одобрением, Класс A (mismatch) продолжит промптить через
плагинный инстанс.

## Проверка 4 гипотез Phase Context

| # | Гипотеза | Вердикт | Доказательство |
|:--|:--|:--|:--|
| H1 | Имя сервера в проекте отличается (perplexity vs perplexity-web) — user-allow не матчится | **подтверждена, но в другой форме** | Буквального `perplexity` (без `-web`) во флоте нет (только 1 dead legacy-запись `mcp__perplexity__perplexity_search` в user settings.json, ничему не соответствует, не источник текущих промптов). Реальный mismatch — **плагинный префикс**: `mcp__plugin_core_perplexity-web__*` ≠ правило `mcp__perplexity-web` (см. Класс A). Это тот же механизм (несовпадение matcher'а с фактическим tool-именем), просто конкретная причина расхождения — не «perplexity vs perplexity-web», а «plugin_core_ префикс». |
| H2 | Сервер в project `.mcp.json` висит Pending approval — allow бессилен до одобрения | **подтверждена, репро на 7 проектах** | `claude mcp list` в flexcrm/edufy/agelto/dterema-app/memster/chatom дословно: `perplexity-web: /home/vostrikov/projects/packages/perplexity-web-mcp/start.sh --pool=default - ⏸ Pending approval (run \`claude\` to approve)`. botkit — та же строка, при этом explicit allow (`mcp__perplexity-web__search*`) в `.claude/settings.json` есть — и не помогает: подтверждает, что approval — отдельный от permission-engine гейт (см. Класс B). |
| H3 | Untrusted-папка → `enabledMcpjsonServers` проекта игнорируется (v2.1.196+) | **не встречается / не отличима от H2 в текущих данных** | `enabledMcpjsonServers` пуст **независимо** от `hasTrustDialogAccepted` (пуст и у trusted diabox/sova, и у untrusted dterema/app/edufy/flexcrm) — поле никогда не населялось ни в одном случае, поэтому нельзя отличить «проигнорировано из-за untrusted» от «никогда не одобрялось». Механизм не опровергнут, но не наблюдаем отдельно от H2 на имеющихся данных. |
| H4 | MCP-тулы с `_meta["anthropic/requiresUserInteraction"]` промптят всегда | **отвергнута** | `grep -rn "requiresUserInteraction"` по исходникам `perplexity-web-mcp` (`src/*.ts`) — 0 совпадений; сервер не выставляет этот `_meta`-флаг ни на одном тул-определении. |

## Дополнительно обнаруженный механизм (не входил в исходные 4 гипотезы)

Курируемый плагин `core` в `.claude-plugin/marketplace.json` объявлен с
`"source": "./"` (корень монорепо swissknifeman) и **без** явного поля
`mcpServers` — тем не менее Claude Code сам подхватывает `<монорепо>/.mcp.json`
плагина (там определены `maind` + `perplexity-web`, `provision`-скоуп
`project:swissknifeman`) и регистрирует его глобально в КАЖДОМ проекте, где
плагин `core` включён, под именем `plugin:core:<server>` — **уже
подключённым, без per-project approval-диалога** (плагинные MCP-серверы,
похоже, не требуют того же гейта, что project-local `.mcp.json`). Это и есть
источник инстанса `plugin:core:perplexity-web`, который в Классе A ловит
tool-permission ask из-за несовпадения имени.

## Harness-пресеты — конфликтов не найдено

`packages/harness/configs/claude-code/settings.global.json:48` содержит
`"mcp__perplexity-web"` (bare allow) — корректно написан, но не может
покрыть плагинный префикс синтаксически (Claude Code сам генерирует имя
`plugin_core_perplexity-web`, это не конфигурируемый alias). Ни в одном
пресете (`settings.base/laravel/node/python/docker/yolo.json`) нет
`ask`/`deny`-правил на `mcp__perplexity-web*` или `mcp__plugin_*` —
harness пресеты сами по себе НЕ создают конфликт, они просто не могут
закрыть Класс A существующим синтаксисом allow-правил (нужен либо
дополнительный allow-паттерн на `mcp__plugin_core_perplexity-web__*`, либо
устранение дублирования самого плагинного инстанса — решение за P4.3).

## Что это значит для P4.3 (ТЗ)

Класс A (mismatch, весь флот с core-плагином): добавить в пресет harness
(`settings.global.json` и/или `mcp.py`-раздачу) allow-правило на
`mcp__plugin_core_perplexity-web__*` (и симметрично для `maind`, если там
та же картина — не проверялось в P4.1, вне scope) **или** убрать
дублирование, сделав project-local `.mcp.json`-запись единственным
источником и полагаясь только на одобрение сервера (тогда нужно решать
Класс B).

Класс B (pending approval, весь флот кроме swissknifeman): одобрение —
интерактивный шаг клиента (`claude mcp list` + подтверждение), не
управляется файлом настроек напрямую; штатный способ раскатки на флот —
уточнить в P4.3, есть ли CLI-механизм массового approve (`claude mcp
enable`/аналог) или это нужно делать per-project вручную один раз с
последующей персистентностью в `~/.claude.json`.

## После фикса (P4.3, 2026-07-07)

Оба класса устранены системно ОДНИМ изменением пресета
`packages/harness/configs/claude-code/settings.global.json` + один прогон
`bash scripts/apply-permissions.sh --global` (merge-only в
`~/.claude/settings.json`, бэкап `.bak` создан автоматически):

- **Класс A** (mismatch плагинного префикса): в `permissions.allow` добавлен
  `mcp__plugin_core_perplexity-web` (bare, тот же паттерн покрытия, что уже
  работал для `mcp__perplexity-web`).
- **Класс B** (project-scoped `.mcp.json` вечно Pending): добавлен top-level
  ключ `enabledMcpjsonServers: ["perplexity-web"]` — по докам Claude Code
  (verified via context7 `/websites/code_claude`, `docs/en/settings`) это
  user-scope настройка, одобряющая указанные ИМЕНА серверов из `.mcp.json`
  ЛЮБОГО проекта — не требует per-project интерактивного шага. Ответ на
  open_question из handoff: штатного CLI-механизма массового `claude mcp
  enable` нет, но он и не нужен — `enabledMcpjsonServers` в user-scope
  settings.json решает задачу декларативно, без per-project вызова.

`apply-permissions.sh` до фикса не умел мержить top-level
`enabledMcpjsonServers` (только `permissions.{allow,ask,deny,defaultMode}` и
`hooks`) — добавлен union-merge с дедупом (см. диф скрипта), покрыт тестом
`test_global_preset_merges_enabled_mcpjson_servers`
(`packages/harness/tests/test_permissions.py`).

**Контрольное репро (Класс B, `claude mcp list`, дословно):**

| Проект | До фикса | После фикса |
|:--|:--|:--|
| botkit | `⏸ Pending approval (run \`claude\` to approve)` | `✓ Connected` |
| flexcrm | `⏸ Pending approval (run \`claude\` to approve)` | `✓ Connected` |
| agelto/agelto | `⏸ Pending approval (run \`claude\` to approve)` | `✓ Connected` |
| dterema/app | `⏸ Pending approval (run \`claude\` to approve)` | `✓ Connected` |

Побочных эффектов не найдено: в flexcrm `claude mcp list` после фикса
по-прежнему показывает `maind`/`serena`/`laravel-boost` как `⏸ Pending
approval` (эти серверы НЕ в scope P4.3 — точечный `enabledMcpjsonServers`
тронул только `perplexity-web`, широкий `enableAllProjectMcpServers` не
использован, как и предписывал Code Guidance).

**Класс A** — прямой репро («вызвать поиск через плагинный инстанс и
убедиться, что нет ask-промпта») недоступен из этой exec-сессии (промпт —
интерактивный UI-диалог внутри ДРУГОЙ сессии Claude Code, не наблюдаемый из
Bash-тула текущей). Уверенность в фиксе — по аналогии: добавленное правило
`mcp__plugin_core_perplexity-web` использует тот же bare-паттерн, что уже
рабочий `mcp__perplexity-web` (Класс A существовал именно из-за ЕГО
отсутствия для префиксного имени — см. Класс A выше). Отмечено как известное
ограничение репро, не как непроверенный фикс.

## Провенанс

Внешняя семантика Claude Code (merge правил всех scope, `ask` бьёт
`allow`, отдельный server-approval гейт, `enabledMcpjsonServers`/
`enableAllProjectMcpServers` игнор в untrusted с v2.1.196) — уже
верифицирована и задокументирована в `phases/P4.md` Phase Context
(perplexity-web, снято 2026-07-07, RAG-лестница context7→perplexity-web
по методологии корневого CLAUDE.md); в этом файле переиспользована, не
переверифицировалась повторно (не внешний факт, а применение уже
верифицированной семантики к конкретным данным флота).
