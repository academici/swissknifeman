---
description: "Добавить MCP-серверы (context7, playwright, …) в .mcp.json проекта из пресетов харнеса, merge-only."
---
Добавь MCP-серверы в `.mcp.json` текущего проекта из пресетов харнеса.

1. Покажи доступные пресеты: `harness mcp --list`.
2. Уточни набор (например `context7,playwright`) и цель (`--target .`).
3. Предложи `--dry-run`, затем примени.

Запуск (через Bash):
```
harness mcp --target . --mcp context7[,playwright,…] [--dry-run]
```
Merge-only: чужие записи `mcpServers` не затираются, файл бэкапится в `*.bak`. Аргументы пользователя — «$ARGUMENTS».
