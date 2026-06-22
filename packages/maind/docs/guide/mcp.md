# MCP-сервер

maind сам является **MCP-сервером** для внешних агентов (Claude Code, Cursor, …). Транспорт —
**stdio JSON-RPC 2.0, newline-delimited JSON** (одно сообщение = одна строка + `\n`, без
`Content-Length`). Чистый stdlib, без MCP SDK; протокол — в stdout, логи/ошибки — в stderr.

## Запуск и подключение

```bash
maind mcp [--scope project:<id>]   # stdio: NDJSON из stdin → ответы в stdout
```

`.mcp.json` потребляющего проекта `maind deploy` вписывает сам — со scope проекта:

```json
{
  "mcpServers": {
    "maind": { "command": "/path/to/maind/bin/maind", "args": ["mcp", "--scope", "project:flexcrm"] }
  }
}
```

::: tip Авто-scope
`--scope` (или env `MAIND_SCOPE`) задаёт scope **по умолчанию** для memory-инструментов: агент
проекта пишет/читает память автоматически в своём `project:<id>`, не передавая scope и не
промахиваясь мимо неймспейса. Без флага — `global`.
:::

## Tools

| Tool | Аргументы | Делегирует |
|:--|:--|:--|
| `maind_memory_store` | `scope?, key?, value` | `memory.store` |
| `maind_memory_recall` | `scope?, query` | `memory.recall` |
| `maind_memory_forget` | `scope?, key` | `memory.forget` (best-effort) |
| `maind_graph_query` | `from, depth?, edge_types?` | `graph.query` |
| `maind_graph_neighbors` | `node, depth?, direction?` | `graph.neighbors` |
| `maind_graph_path` | `from, to` | `graph.path` (кратчайший путь) |
| `maind_graph_project` | `project` | `Federation.project_view` (граф одного проекта) |
| `maind_memory_links` | `project, depth?, namespace?` | граф-связи + ecosystem-link память |
| `maind_agents_list` | — | `agents.listing` |
| `maind_projects_list` | — | `projects.listing` |
| `maind_projects_status` | `project?` | `probe` (состояние хаба + проектов) |

Итого **11 инструментов** (memory · graph · ecosystem-links · реестры). `scope?` —
необязательно (по умолчанию scope узла, см. авто-scope). `maind_memory_links` отдаёт память
проекта из всех релевантных бакетов (`project:<id>` + `ns:<группы>` + `global`) — внутри
namespace память общая, между группами изолирована (паритет с графом, см. [Память](./memory)).
Память-инструменты требуют живого демона; нет обязательного аргумента, демон недоступен или
ошибка инструмента → ответ помечается `isError: true`, **сервер при этом не падает**.

## Методы JSON-RPC

`initialize` (→ `serverInfo.name = maind`; **эхо-ит `protocolVersion` клиента**) ·
`notifications/initialized` (без ответа) · `tools/list` · `tools/call` · `ping`. Неизвестный
метод/инструмент → ошибка `-32601`; внутренняя ошибка → `-32603` (цикл продолжается).

## Почему свой сервер, а не FastMCP

maind — **stdlib-only, Python 3.9+, переносимый** (как swissknifeman/brain). FastMCP тянет ~25
pip-зависимостей (`pydantic`/`uvicorn`/`httpx`/`authlib`/…) и Python ≥3.10 — непропорционально для
11 stdio-инструментов и ломает zero-dep идентичность пакета. Свой сервер закалён **conformance-тестом
на реальный spawn** (полный NDJSON-хендшейк), так что класс багов вроде framing'а не повторится.
Пересмотрим решение, если понадобится **HTTP-транспорт, авторизация или много инструментов** —
тогда фреймворк оправдан.

Дальше: [Healthcheck →](./health)
