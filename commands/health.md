---
description: Healthcheck связи ТЕКУЩЕГО проекта с хабом mAInd; по подтверждению (или --fix) — авто-починка.
argument-hint: "[--fix]"
allowed-tools: Bash(maind:*)
---
## Здоровье связи (текущий каталог)
!`maind health --cwd --json`

Разбери результат: `status` (connected / partial / standalone), `memory_daemon`, наличие `agentmemory_mcp` / `maind_mcp` в проекте, список `hints`.

Если статус не `connected`:
- при `--fix` в «$ARGUMENTS» ИЛИ явном подтверждении пользователя — запусти `maind health --cwd --fix` (поднимет демон памяти при необходимости и допишет MCP-серверы хаба в проект), затем покажи обновлённый статус;
- иначе — просто перечисли подсказки `hints` и предложи запустить с `--fix`.
