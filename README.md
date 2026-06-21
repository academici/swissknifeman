# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Монорепозиторий-зонтик экосистемы **academici**: один швейцарский нож над несколькими
> независимыми пакетами и плагинами Claude Code. Единая консоль, единый marketplace, общий core.

## Пакеты

| Пакет | Роль | CLI |
|:--|:--|:--|
| [`packages/swissknifeman`](packages/swissknifeman/) | реестр AI-скиллов — раздаёт навыки в проекты (connect/vendor) | `swissknifeman` |
| [`packages/maind`](packages/maind/) | хаб памяти, графа и координации экосистемы (MCP-шина) | `maind` |

Общий фундамент — пакет [`core`](core/) (stdlib-only: `Env`, вывод, slug).

## Установка

```bash
./install.sh                  # ставит swissknifeman и maind в PATH (делегирует install.sh пакетов)
```

`install.sh` делегирует пакетную пост-настройку их собственным установщикам
(`packages/*/install.sh`). Два независимых CLI в PATH — единой консоли-обёртки нет.

## CLI

```bash
maind <cmd>                   # команды хаба (memory, graph, onboard, deploy, sync, …)
swissknifeman <cmd>           # команды реестра (connect, vendor, integrate, registry, …)
```

## Плагины Claude Code

Один marketplace (`.claude-plugin/marketplace.json`, имя `swissknifeman`) объявляет все плагины
репо: бакеты скиллов, `skm`, `generate-skill` и `maind`. Генерируется `swissknifeman registry`.

## Разработка

Тесты/валидация — по пакету:

```bash
bash packages/swissknifeman/scripts/validate.sh
bash packages/maind/scripts/validate.sh
```

Подробности — в `CLAUDE.md` корня и каждого пакета. Коммиты — Conventional Commits на русском.
