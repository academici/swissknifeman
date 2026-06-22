# memory MCP

## Что это

Официальный (Anthropic / Model Context Protocol) сервер: персистентный **knowledge graph** —
агент сохраняет сущности, связи и наблюдения между сессиями.

- Репозиторий: `modelcontextprotocol/servers` (`src/memory`)
- npm: `@modelcontextprotocol/server-memory`

## Установка

Пресетом (opt-in):

```bash
skiller integrate --mcp memory
```

Пресет — `configs/claude-code/mcp/memory.json`:

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"]
}
```

## Ограничения и альтернатива

::: tip У экосистемы academici своя память
В констелляции есть собственный слой памяти (`maind` / `agentmemory` + скилл
`system/shared-memory`, federation-режим memory в `integrate`). Базовый `server-memory` —
простой локальный граф без межпроектной федерации; бери его, когда нужна именно лёгкая
standalone-память, а не общий «мозг».
:::
