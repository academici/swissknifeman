# P4-safedirs — Аудит подсистемы safe-dirs по флоту (read-only)

Вход: `packages/harness/lib/harness/safedirs.py`, хук
`configs/claude-code/hooks/auto-approve/lib/safedirs.py`, `config.json` хука,
`<монорепо>/safe-dirs.json` (+ `.example.json`), `packages/harness/CLAUDE.md`.
Реестр флота: `~/.swissknifeman/projects.json` (19 уникальных путей).

## Вердикт по вопросам (a)–(d) из Code Guidance

### (a) Миграция legacy → корень монорепо

**Завершена, `_state_file` резолвится в репо фактически** (не только по коду).
- `<монорепо>/safe-dirs.json` существует (`version:1`, 3 explicit `dirs` +
  `include_registered_projects:true`).
- `~/.swissknifeman/safe-dirs.json.migrated` присутствует (старое содержимое:
  один `dirs: ["/home/vostrikov/projects"]`) + `.bak` рядом — миграция
  прошла, легаси-файл переименован, хук его больше не видит (репо-путь стоит
  выше в лестнице `_config_path`).
- Функциональный репро хука (`echo '{"tool_input":{"command":"rm -rf
  <путь-в-репо>"},...}' | python3 lib/safedirs.py` в
  `configs/claude-code/hooks/auto-approve/lib/`) → `safe` (exit 0):
  резолвер `_repo_root()` находит монорепо через `realpath` лаунчера из PATH
  и грузит `safe-dirs.json` корректно.
- `harness safe-dirs list` (read-only CLI) подтверждает те же 22 эффективных
  корня, что видит хук (3 explicit + 19 из реестра).

**Вердикт: OK, действий не требуется.**

### (b)/(c) STATIC_ASK-правила (`PRUNE_ASK_RULES`) vs реальные settings флота

`PRUNE_ASK_RULES = ("Bash(rm -r *)", "Bash(rm -rf *)")` в `safedirs.py` —
это исторические правила, которые ДЕЙСТВИТЕЛЬНО были в `ask[]` пресетов
`settings.base.json`/`settings.global.json` (git-история подтверждает: сняты
тем же коммитом, что вводил safe-dirs, `7062063 feat(harness): safe-dirs —
path-scoped разрешение rm/rmdir в auto-approve`). Значит список **был**
актуален на момент введения фичи.

Проверка по факту (grep `permissions.ask`/`allow`/`deny` во всех
`.claude/settings.json` + `.claude/settings.local.json` 19 проектов флота +
`~/.claude/settings.json` user-scope): **ни в одном текущем конфиге нет**
`Bash(rm -r *)` / `Bash(rm -rf *)` ни в `ask`, ни где-либо ещё под именем,
которое матчило бы голый `rm`/`rmdir`. Единичные `rm`/`rmdir`-упоминания на
флоте — это либо точечные one-off `allow`-записи (`Bash(rm -rf
<конкретный-путь>)`, `Bash(rmdir *)`, `Bash(rmdir docker *)` — не блокируют,
наоборот разрешают шире), либо `docker rm`/`docker rmi`/`docker volume rm` в
`ask` (docker-пресет, к safe-dirs/голому `rm` отношения не имеет).

**Вердикт: капкан «статический ask душит hook-allow» на текущем флоте
НЕ проявлен** — все 19 проектов уже чисты (либо провижинились после
коммита 7062063, либо `prune-ask` уже применялся ранее). `prune-ask` как
защитный механизм остаётся корректным и рабочим (код проверен, логика
`remove_permission_rules` снимает ровно эти две строки) — просто сейчас
не находит целей. Список `STATIC_ASK` **не отстал** от пресетов: он и не
обязан совпадать с ТЕКУЩИМ содержимым пресетов — это whitelist-снятие
конкретно ЭТИХ двух исторических строк из чужих/старых settings, работает
независимо от того, генерит ли пресет их сейчас.

### (d) `additionalDirectories` vs safe-dirs — роли не путаются

`permissions.additionalDirectories` (user-scope `~/.claude/settings.json`,
27 путей) — даёт Claude Code доступ (Read/Write/Bash cwd) к директориям ВНЕ
текущего проекта (в основном подкаталоги смежных пакетов — `azguard/tests`,
`doc-vault/...`, `botkit/packages/bot-assistant`, и т.п., накопленные
вручную по мере работы). `safe-dirs.json` — это ДРУГОЙ, узкий allowlist
именно для авто-одобрения `rm`/`rmdir` мимо `deny_hard`, читает его только
хук `auto-approve`. Пересечения по смыслу нет: `additionalDirectories`
не даёт auto-approve на `rm` (permissions ≠ hook-вердикт), а safe-dirs не
даёт доступа к директориям вне разрешённых permissions. Ролевой конфликт
не найден.

**Вердикт: OK, роли разведены корректно, путаницы нет.**

## Таблица покрытия флота — установка hook'а auto-approve

19 уникальных путей реестра `~/.swissknifeman/projects.json`. Проверялось:
наличие `PreToolUse`→`auto-approve.sh` в `.claude/settings.json` ИЛИ
`.claude/settings.local.json`; `permissions.defaultMode` проекта.

| Проект | auto-approve hook | defaultMode | В allowlist safe-dirs | Вывод |
|:--|:--|:--|:--|:--|
| agelto/agelto | ✅ (settings.json) | стандартный | ✅ (explicit + registry) | OK |
| packages/vaulter | ✅ (settings.local.json) | стандартный | ✅ (registry) | OK |
| flexcrm | ✅ (settings.local.json) | стандартный | ✅ (registry) | OK |
| sibintek/projects/sova | ✅ (settings.local.json) | стандартный | ✅ (explicit+registry) | OK |
| packages/azguard | ✅ (settings.local.json) | стандартный | ✅ (registry) | OK |
| packages/corex | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| memster | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| vintera/cms | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| edufy | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| dterema/dterema | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| dterema/app | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| diabox | ✅ (settings.local.json) | стандартный | ✅ (registry) | OK |
| sibintek/projects/insiders | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| packages/chatom | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| packages/perplexity-web-mcp | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| packages/botkit | ✅ (settings.local.json) | стандартный | ✅ (registry) | OK |
| packages/swissknifeman | ✅ (settings.json) | стандартный | ✅ (registry) | OK |
| **vintera/vintera** | ❌ нет `PreToolUse` вообще (ни `settings.json`, ни `.local.json`) | **`bypassPermissions`** (yolo-пресет) | ✅ (registry, но неактуально) | **не дефект** — см. ниже |
| packages/loqum | ✅ (settings.json) | стандартный | ✅ (registry) | OK |

**18/19 — hook установлен, safe-dirs активен и функционален.**

**1/19 (vintera/vintera) — hook отсутствует, но это НЕ дефект safe-dirs**:
проект на `settings.yolo.json`-пресете (`defaultMode: "bypassPermissions"`).
В bypass-режиме разрешения не спрашиваются вообще (`rm` не промптит и без
хука) — устанавливать auto-approve/safe-dirs в yolo-проект бессмысленно,
хук там ничего не решает. `settings.yolo.json` целенаправленно НЕ включает
`hooks` (только `permissions.ask`/`deny` с узким списком: force-push,
`sudo`, ssh/aws-ключи, `.pem`) — соответствует своему назначению.
Наблюдение вне scope P4.2 (не safe-dirs, а общая yolo-политика): в bypass-
режиме `deny_hard`-паттерны хука (`mkfs`/`dd of=`/`shutdown` и т.п.) тоже
не действуют — риск шире, чем `rm`, но это осознанный trade-off самого
yolo-пресета, не пробел покрытия safe-dirs.

## Итог: список действий для P4.3

Аудит НЕ находит активных дефектов safe-dirs на текущем флоте — все 4
вопроса (a)–(d) закрыты с вердиктом OK/не-проявлено. Конкретных
обязательных фиксов для P4.3 по этой части нет:

1. **Нет действия** — миграция и резолвинг конфига работают штатно (a).
2. **Нет действия** — `prune-ask` не находит целей на текущем флоте (b/c);
   код `prune-ask` оставить как есть (защита от регресса при провижининге
   из старых бэкапов/legacy-конфигов остаётся полезной).
3. **Нет действия** — `additionalDirectories` и `safe-dirs.json` не
   конфликтуют по ролям (d).
4. **Не фикс, а наблюдение** — vintera/vintera без hook объясняется yolo-
   режимом, устанавливать hook туда не нужно; если понадобится общий
   контрольный список «yolo-проекты исключены из safe-dirs coverage
   намеренно» — можно one-line отметить в `packages/harness/CLAUDE.md`
   (не обязательно, nit-уровень, решение — за P4.3/Approval Owner).

P4.3 использует этот файл вместе с `findings/P4-perplexity.md` как ТЗ —
из P4.2 в P4.3 переносить нечего по safe-dirs-контуру: фикс-фаза
фокусируется на Классе A/Классе B из P4.1 (perplexity-web permissions).

## После фикса (P4.3, 2026-07-07)

Подтверждено: P4.3 не вносил изменений в safe-dirs-контур (не требовалось —
см. «Итог» выше). `prune-ask`/init/add не вызывались, конфиг `safe-dirs.json`
и hook не трогались. Nit-наблюдение про yolo-исключение (vintera/vintera) —
оставлено как есть, не материализовано (nit-уровень, не блокирует P4.3).
