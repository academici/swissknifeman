# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Монорепозиторий-зонтик экосистемы **academici**: один швейцарский нож над несколькими
> независимыми пакетами и плагинами Claude Code. Единая консоль, единый marketplace, общий core.

## Пакеты

| Пакет | Роль | CLI |
|:--|:--|:--|
| [`packages/swissknifeman`](packages/swissknifeman/) | реестр AI-скиллов — раздаёт навыки в проекты (connect/vendor) | `swissknifeman` / `academici skm` |
| [`packages/maind`](packages/maind/) | хаб памяти, графа и координации экосистемы (MCP-шина) | `maind` / `academici maind` |

Общий фундамент — [`core/academici_core`](core/) (stdlib-only: `Env`, вывод, slug).

## Установка

```bash
./install.sh                  # ставит academici + под-команды maind/swissknifeman
academici help                # единая точка входа
```

`install.sh` делегирует пакетную пост-настройку их собственным установщикам
(`packages/*/install.sh`). Под-бинарники `maind`/`swissknifeman` остаются самостоятельными.

## Консоль

```bash
academici maind <cmd>         # команды хаба (memory, graph, onboard, deploy, sync, …)
academici skm   <cmd>         # команды реестра (connect, vendor, integrate, registry, …)
academici doctor              # сводная диагностика обоих пакетов
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
