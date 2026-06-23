# academici

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Монорепозиторий-зонтик экосистемы **academici**: один швейцарский нож над несколькими
> независимыми пакетами и плагинами Claude Code. Единая консоль, единый marketplace, общий core.

## Пакеты

| Пакет | Роль | CLI |
|:--|:--|:--|
| [`packages/skiller`](packages/skiller/) | реестр AI-скиллов — раздаёт навыки в проекты (connect/vendor) | `skiller` (алиас `swissknifeman`) |
| [`packages/harness`](packages/harness/) | настройка окружения Claude Code (permissions, MCP-серверы, хуки) | `harness` |
| [`packages/maind`](packages/maind/) | хаб памяти, графа и координации экосистемы (MCP-шина) | `maind` |

Общий фундамент — пакет [`core`](core/) (stdlib-only: `Env`, вывод, slug).

## Установка

```bash
./install.sh                  # ставит skiller, harness, maind + корневой роутер swissknifeman в PATH
```

`install.sh` делегирует пакетную пост-настройку их собственным установщикам
(`packages/*/install.sh`) и ставит симлинк `swissknifeman` → корневой роутер (router + setup-фасад).

> `.mcp.json` этого репо машинно-специфичен (абсолютные пути к `maind`) и не коммитится —
> шаблон [`.mcp.json.example`](.mcp.json.example), реальный файл генерит/обновляет `maind` (sync/deploy).

## CLI

```bash
swissknifeman <group> …       # корневой роутер: skills→skiller, env→harness, maind→maind; + setup, doctor
swissknifeman setup <project> # кросс-пакетный онбординг (скиллы+окружение+память+граф) → maind onboard
skiller <cmd>                 # реестр скиллов (connect, vendor, integrate, registry, …) — алиас swissknifeman
harness <cmd>                 # окружение Claude Code (permissions, mcp, hooks, doctor)
maind <cmd>                   # хаб (memory, graph, onboard, deploy, sync, health, …)
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
bash packages/harness/scripts/validate.sh
bash packages/maind/scripts/validate.sh
```

Подробности — в `CLAUDE.md` корня и каждого пакета (+ `CONTRIBUTING.md`). Коммиты — Conventional Commits на русском.
