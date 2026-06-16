# Плагин Claude Code

maind поставляется и как **плагин Claude Code** — тонкое лицо над CLI. Ставишь плагин в любом
проекте → появляются slash-команды `/maind:*`, которыми хаб управляется прямо из чата, не выходя в
терминал. Плагин ничего не дублирует: команды вызывают тот же `maind` (см. [CLI](./cli)).

## Что внутри

| Артефакт | Назначение |
|:--|:--|
| `.claude-plugin/plugin.json` | манифест плагина (имя `maind`, путь к командам, ссылка на MCP) |
| `.claude-plugin/marketplace.json` | single-entry marketplace `maind` — делает репозиторий устанавливаемым |
| `commands/*.md` | slash-команды — обёртки над CLI |
| `.mcp.json` | hub-MCP сервер `maind-hub` (global scope) — инструменты хаба в сессии |

## Установка

Сначала — обычная установка CLI (команды плагина зовут `maind` из PATH):

```bash
cd maind && ./install.sh          # симлинк ~/.local/bin/maind
```

Затем в Claude Code:

```
/plugin marketplace add /путь/к/maind     # или github:academici/maind
/plugin install maind@maind
```

После перезагрузки появляются команды `/maind:*`. MCP-сервер `maind-hub` поднимается
автоматически (проверь `/mcp`).

## Команды

| Команда | Что делает | Обёртка над |
|:--|:--|:--|
| `/maind` | парадная дверь: список команд + маршрутизация | — |
| `/maind:onboard <проект>` | подключить проект: диалогом уточняет bundle/код-граф/brain → применяет | `maind onboard --yes` |
| `/maind:sync [--all]` | перераскатать управляемые артефакты на проекты | `maind sync` |
| `/maind:status` | статус хаба и проектов экосистемы | `maind status` · `projects list` |
| `/maind:health [--fix]` | здоровье связи текущего проекта с хабом | `maind health --cwd` |
| `/maind:doctor` | диагностика окружения узла | `maind doctor` |

## Как работает интерактивность

slash-команда запускает bash **не в TTY**, поэтому интерактивный визард с `input()` тут не
работает. «Выбор набора» (bundle, код-граф, brain) команда `/maind:onboard` ведёт **диалогом
агента**: спрашивает в чате → собирает выбор → зовёт CLI неинтерактивно с флагами
(`--bundle … --yes`). Мутирующие команды (`onboard`, `sync`) сперва показывают `--dry-run`, затем
применяют по подтверждению.

## hub-MCP сервер

`.mcp.json` бандлит сервер `maind-hub` (`maind mcp --scope global`) — даёт инструменты хаба
(`maind_projects_list`, `maind_projects_status`, `maind_agents_list`, обходы графа, global-память)
в любой сессии с включённым плагином. Имя `maind-hub` намеренно отличается от per-project сервера
`maind` (project scope), который `deploy` пишет в `.mcp.json` подключённых проектов — чтобы серверы
не коллизировали. См. [MCP-сервер](./mcp).

## Кросс-провайдерность

Богатый UX (slash-команды, hooks) — это формат Claude Code. Универсальный, кросс-провайдерный слой —
**MCP**: `maind mcp` работает с любым клиентом (Cursor через `.cursor/mcp.json` и т.д.). Скиллы —
провайдер-нейтральный `SKILL.md` (раскатываются swissknifeman). «Плагин» — это Claude-специфичная
упаковка поверх универсального MCP-ядра, а не отдельная реализация.
