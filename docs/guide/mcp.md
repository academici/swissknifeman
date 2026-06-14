# MCP-сервер

maind сам является **MCP-сервером** для внешних агентов (Claude, Cursor, …). Транспорт —
**stdio JSON-RPC 2.0** с LSP-style `Content-Length` framing, чистый stdlib (без MCP SDK).

## Запуск и подключение

```bash
maind mcp        # читает JSON-RPC из stdin, пишет в stdout
```

`.mcp.json` потребляющего проекта:

```json
{
  "mcpServers": {
    "maind": { "command": "/path/to/maind/bin/maind", "args": ["mcp"] }
  }
}
```

## Tools

| Tool | Аргументы | Делегирует |
|:--|:--|:--|
| `maind_memory_store` | `scope, key?, value` | `memory.store` |
| `maind_memory_recall` | `scope, query` | `memory.recall` |
| `maind_graph_query` | `from, depth?, edge_types?` | `graph.query` |
| `maind_graph_neighbors` | `node, depth?, direction?` | `graph.neighbors` |
| `maind_agents_list` | — | `agents.listing` |
| `maind_projects_list` | — | `projects.listing` |

Память-инструменты требуют живого демона: если он не запущен, ответ помечается
`isError: true` с подсказкой `maind start --only memory`.

## Методы JSON-RPC

`initialize` (→ `serverInfo.name = maind`, `capabilities.tools`) · `notifications/initialized`
(без ответа) · `tools/list` · `tools/call` · `ping`. Неизвестный метод/инструмент →
ошибка `-32601`.

Дальше: [Конфиг .maind.json →](/guide/config)
