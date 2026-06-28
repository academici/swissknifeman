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
| `skiller status --json --target .` | детальный слой скиллов (каналы, профиль, бюджет, overlap) |
| `harness agent-packs doctor --target . --json` | слой ролей (каталог паков + установленные) |
| `maind verify --json` | пруф-оф-лайф памяти/графа/код-графа (не «поднято», а «реально пишут») |

## Диагностика окружения (не проектный инвентарь)

`swissknifeman doctor` — fan-out по трём пакетам (`skiller`/`harness`/`maind` doctor): здоровье
**самих инструментов** (PATH, реестр, демон, пресеты). Это про машину/установку, а
`swissknifeman status` — про **состояние конкретного проекта/флота**.

## Полная настройка проекта

Порядок «дать проекту всё» (все 4 слоя) — операционный раннбук `project-tooling-runbook`
(скилл) и [дерево решений онбординга](/maind/guide/onboarding-decision-tree). Кратко:
онбординг в хаб → скиллы (канал) → **agent-packs (роли)** → MCP/Boost → память/граф →
auto-approve → `swissknifeman status <id>` на проверку.
