# Control-surface проекта (4 слоя)

Инструменты проекта в экосистеме — это **четыре независимых слоя**. Их состояние и
пере-синхронизацию контролирует **скриптовый control-surface**: одной командой посмотреть
полный инвентарь, точечно пере-синкать любой слой. Всё машиночитаемо (`--json`) — пригодно
и человеку, и агенту (Claude Code сам видит drift и чинит точечно).

## Четыре слоя

| Слой | Что это | Источник истины / lock | Статус | Точечная починка / re-sync |
|:--|:--|:--|:--|:--|
| **Скиллы** | знания (connect-плагины / vendor-копии) | `.claude/settings.local.json` (enabledPlugins) · `skills-lock.json` | `skiller status [--json]` | `skiller connect`/`sync` · `skiller update` |
| **Роли/агенты** | субагенты + workflow + review-gate | `.claude/agent-pack.lock.json` | `harness agent-packs doctor --target . [--json]` | `harness agent-packs render/upgrade` · `maind sync --only agent-pack` |
| **MCP** | инструменты (память/код-граф/…) | `.mcp.json` | `maind health --project <id>` | `maind sync --only mcp` · `maind deploy` |
| **Память/граф** | общий контекст + федерация связей | демон `:4111` · графы хаба · `.claude/memory.env.ini` | `maind verify [--json]` · `maind status` | `maind sync --only memory,graph,code-graph` · `maind start --only memory` |

> Слои **независимы** (skiller / harness / maind не знают друг о друге); единая точка — зонтичный
> CLI и оркестратор `maind`.

## Проверка проекта одной командой

```bash
swissknifeman status <project-id>        # единый 4-слойный инвентарь проекта
swissknifeman status --all               # весь флот (по строке на проект)
swissknifeman status --all --json        # машиночитаемо (для агента/панели)
```

Вывод (по строке на проект): `status · mcp[a/m/c] · trust · skills=N · packs=N · scope` —
плюс **drift→fix подсказки** (`⚠ слой: проблема → команда починки`). `<project-id>` фасадит в
`maind projects status --project <id>`; bare `swissknifeman status` (или `--target`) — back-compat
в `skiller status` (скиллы текущего проекта).

```
Проекты (1) — слои: mcp[a/m/c] · skills · packs(роли) · trust:
  connected   agelto   mcp[-mc] trust· skills=42  packs=1  project:agelto
      ⚠ agent-pack: профиль ожидает паки backend-laravel — не установлены → maind sync --only agent-pack --project agelto
```

В `--json` каждый проект несёт `skills`, `agent_packs`, `configured` (MCP), `status` и массив
`fixes` (`{layer, issue, fix}`) — агент читает `fixes` и выполняет точную команду.

## Операционный цикл: status → точечный re-sync

1. **Status** — `swissknifeman status <id> --json` (или `--all`). Смотри `status` и `fixes`.
2. **Drift** — каждый `fixes[]` даёт точную команду на слой (не «пере-настрой всё»).
3. **Re-sync** — выполни её; почти всегда это `maind sync --only <cap> --project <id>`
   (capability-granular, идемпотентно, `--dry-run` для предпросмотра, `--json` для разбора):

```bash
maind sync --project <id> --only mcp                 # только MCP
maind sync --project <id> --only agent-pack          # только роли/агенты (render/upgrade)
maind sync --project <id> --only memory,graph        # только память/граф
maind sync --project <id> --only mcp,graph --dry-run --json   # план без записи
```

Провиженеры `maind sync --only`: `mcp · code-graph · graph · memory · memory-hook ·
health-hook · health-doc · feature-log-hook · ecosystem-skill · agent-pack`.

## Машиночитаемость (для агента)

| Команда | Что даёт |
|:--|:--|
| `swissknifeman status --all --json` | весь флот: per-project 4 слоя + `fixes` |
| `maind projects status --project <id> --json` | один проект, то же |
| `maind projects health --all --evidence-set <file> --json` | exact-set provider/axis health по sealed redacted evidence; без repair |
| `skiller status --json --target .` | детальный слой скиллов (каналы, профиль, бюджет, overlap) |
| `harness doctor --settings --provider claude-code\|codex --target . --json` | provider-qualified settings audit |
| `harness agent-packs doctor --target . --json` | слой ролей (каталог паков + установленные) |
| `maind verify --json` | пруф-оф-лайф памяти/графа/код-графа (не «поднято», а «реально пишут») |

## Диагностика окружения (не проектный инвентарь)

`swissknifeman doctor` — fan-out по трём пакетам (`skiller`/`harness`/`maind` doctor): здоровье
**самих инструментов** (PATH, реестр, демон, пресеты). Это про машину/установку, а
`swissknifeman status` — про **состояние конкретного проекта/флота**.

## Исполнение плана волной

`swissknifeman env run <PLAN-ID> <Pn>` ведёт готовые `plan-run` items одной фазы
последовательно: сначала строит очередь, затем останавливается на первом RED. Начинай с
`--dry-run`: он показывает, какие items водитель возьмёт или откажется вести, и ничего не
пишет. Ручные и terminal items остаются за оператором; контракт, журнал и итоговый verdict
сохраняют обычные владельцы.

## Три слоя источника: canonical → generated → effective

Слои выше отвечают «что подключено». Отдельная ось — «откуда это взялось и что реально
активно»; путать её со слоями нельзя, потому что чинятся они разными командами:

| Слой | Что это | Кто владеет | Как проверить (read-only) |
|:--|:--|:--|:--|
| **canonical** | рукописный источник истины: `packages/*/skills/**`, `packages/task/commands/*.md`, конфиги пакетов | человек/пакет | обычный `git diff`, ревью |
| **generated** | проекции канона: `skills.json`, оба `marketplace.json`, `adapters/**`, `.claude/skills`+`.agents/skills`, publication-locks, часть страниц доков | генератор (`skiller registry`, `render-provider-commands.py`) — **руками не правится** | `skiller registry --check` · `python3 packages/task/scripts/render-provider-commands.py --check --root .` |
| **effective** | что реально видит агент в сессии: активная семантическая идентичность, её провенанс, коллизии, владелец хука, качество трассы | рантайм провайдера | `skiller doctor --effective-source [--json]` |

**Правило:** дрейф `generated` чинится **перегенерацией владеющей командой**, а не правкой
файла; ручная правка сгенерированного — дефект, который поймает `--check`. Диагноз слоя
`effective` — только чтение: `skiller doctor --effective-source` ничего не пишет (доказано
сравнением `git status --porcelain=v1` до и после) и печатает по каждому диагносту
`owner/source/status/evidence/quality/next_command` со статусом `ok`/`degraded`/`unknown`/`n/a`.

**Quality is printed as measured, never rounded.** Where a source is incomplete, the diagnostic prints a named `unknown` gap instead of `ok` (for example `trace-quality` while no per-project trace store exists). Details and common cases: [диагностика skiller](/skiller/guide/troubleshooting).

Один конкретный механизм, живущий целиком в слое `generated` (двенадцать проекций
`CLAUDE.md`/`AGENTS.md` из общего канона, два наблюдения дрейфа, два машинных гейта) —
[канон корневых инструкций](/harness/reference/instruction-canon). Соседний носитель того же
рода (схема-контракт → данные → stdlib-гейт `[10/10]` в `validate.sh`) —
[декларативная политика исполнения](/harness/reference/execution-policy).

## Полная настройка проекта

Порядок «дать проекту всё» (все 4 слоя) — операционный раннбук `project-tooling-runbook`
(скилл) и [дерево решений онбординга](/maind/guide/onboarding-decision-tree). Кратко:
онбординг в хаб → скиллы (канал) → **agent-packs (роли)** → MCP/Boost → память/граф →
auto-approve → `swissknifeman status <id>` на проверку.
