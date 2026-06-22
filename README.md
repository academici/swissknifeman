# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Монорепозиторий-зонтик экосистемы **academici**: один швейцарский нож над несколькими
> независимыми пакетами и плагинами Claude Code. Единая консоль, единый marketplace, общий core.

## Пакеты

| Пакет | Роль | CLI |
|:--|:--|:--|
| [`packages/skiller`](packages/skiller/) | реестр AI-скиллов — раздаёт навыки в проекты (connect/vendor) | `skiller` (алиас `swissknifeman`) |
| [`packages/maind`](packages/maind/) | хаб памяти, графа и координации экосистемы (MCP-шина) | `maind` |

Общий фундамент — пакет [`core`](core/) (stdlib-only: `Env`, вывод, slug).

## Установка

```bash
./install.sh                  # ставит skiller (+ алиас swissknifeman) и maind в PATH
```

`install.sh` делегирует пакетную пост-настройку их собственным установщикам
(`packages/*/install.sh`). Два независимых CLI в PATH — единой консоли-обёртки нет.

## CLI

```bash
maind <cmd>                   # команды хаба (memory, graph, onboard, deploy, sync, …)
skiller <cmd>                 # команды реестра (connect, vendor, integrate, registry, …) — алиас swissknifeman
```

## Плагины Claude Code

Один marketplace (`.claude-plugin/marketplace.json`, имя `swissknifeman` = зонтик) объявляет все
плагины репо: бакеты скиллов, `skm`, `generate-skill` и `maind`. Генерируется `skiller registry`.
Плагин `maind` — только команды `/maind:*` (MCP-инструменты хаба приходят per-project сервером
`maind` из `.mcp.json` проекта, не из плагина).

## Разработка

Тесты/валидация — по пакету:

```bash
bash packages/skiller/scripts/validate.sh
bash packages/maind/scripts/validate.sh
```

Подробности — в `CLAUDE.md` корня и каждого пакета. Коммиты — Conventional Commits на русском.
