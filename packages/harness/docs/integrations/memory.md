# memory MCP

## What is this

Official (Anthropic / Model Context Protocol) server: persistent **knowledge graph** —
agent stores entities, relationships, and observations between sessions.

- Repository: `modelcontextprotocol/servers` (`src/memory`)
- npm: `@modelcontextprotocol/server-memory`

## Installation

Preset (opt-in):

```bash
skiller integrate --mcp memory
```

Preset - `configs/claude-code/mcp/memory.json`:

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"]
}
```

## Limitations and alternative

::: tip At the ecosystem academici own memory
The constellation has its own memory layer (`maind` / `agentmemory` + skill
`system/shared-memory`, federation-mode memory in `integrate`). Basic `server-memory` —
simple local graph without cross-project federation; take it when you need something light
standalone-memory, not shared «brain».
:::
