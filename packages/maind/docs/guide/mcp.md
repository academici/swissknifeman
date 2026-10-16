# MCP-server

maind itself is **MCP-server** for external agents (Claude Code, Cursor, …). Transport -
**stdio JSON-RPC 2.0, newline-delimited JSON** (one message = one line + `\n`, without
`Content-Length`). Clean stdlib, without MCP SDK; protocol - in stdout, logs/errors - in stderr.

## Startup and connection

```bash
maind mcp [--scope project:<id>]   # stdio: NDJSON from stdin → answers in stdout
```

`.mcp.json` consuming project `maind deploy` enters it himself - with scope project:

```json
{
  "mcpServers": {
    "maind": { "command": "${MAIND_BIN:-maind}", "args": ["mcp", "--scope", "project:flexcrm"] }
  }
}
```

`command` — **direction** `${MAIND_BIN:-maind}`: Claude Code exposes it from the process environment
(default `maind` by PATH — `~/.local/bin` from `install.sh`), without machine-specific path; obvious
binary - `export MAIND_BIN=/abs/maind` (CI / non-standard installation).

::: tip Autoscope
`--scope` (or env `MAIND_SCOPE`) sets scope **default** for memory-tools: agent
project writes/reads memory automatically in its `project:<id>`, without transmitting scope and not
missing the namespace. Without a flag - `global`.
:::

## Tools

| Tool | Arguments | Delegates |
|:--|:--|:--|
| `maind_memory_store` | `scope?, key?, value` | `memory.store` |
| `maind_memory_recall` | `scope?, query` | `memory.recall` |
| `maind_memory_forget` | `scope?, key` | `memory.forget` (best-effort) |
| `maind_graph_query` | `from, depth?, edge_types?` | `graph.query` |
| `maind_graph_neighbors` | `node, depth?, direction?` | `graph.neighbors` |
| `maind_graph_path` | `from, to` | `graph.path` (shortest path) |
| `maind_graph_project` | `project` | `Federation.project_view` (graph of one project) |
| `maind_memory_links` | `project, depth?, namespace?` | connection graph + ecosystem-link memory |
| `maind_agents_list` | — | `agents.listing` |
| `maind_projects_list` | — | `projects.listing` |
| `maind_projects_status` | `project?` | `probe` (hub status + projects) |

Total **11 tools** (memory · graph · ecosystem-links · registries). `scope?` —
optional (default scope node, see auto-scope). `maind_memory_links` gives up memory
project from all relevant buckets (`project:<id>` + `ns:<groups>` + `global`) — inside
namespace memory shared, isolated between groups (parity with graph, see [Memory](./memory)).
Memory tools require a living demon; no required argument, daemon not available, or
tool error → response is marked `isError: true`, **the server does not crash**.

## Methods JSON-RPC

`initialize` (→ `serverInfo.name = maind`; **the requested `protocolVersion` if supported (`2025-06-18`, `2024-11-05`), otherwise the newest supported one**) ·
`notifications/initialized` (no response) · `tools/list` · `tools/call` · `ping`. `maind mcp tools [--json]` prints the `tools_digest` and the tool list. Unknown
method/tool → error `-32601`; internal error → `-32603` (cycle continues).

## Why your own server and not FastMCP

maind — **stdlib-only, Python 3.9+, portable** (like swissknifeman/brain). FastMCP pulls ~25
pip-dependencies (`pydantic`/`uvicorn`/`httpx`/`authlib`/…) and Python ≥3.10 — disproportionate for
11 stdio-tools and breaks zero-dep package identity. Your server is hardened **conformance-test
to real spawn** (full NDJSON-handshake), so the bug class is like framing'and will not happen again.
We'll reconsider the decision if necessary **HTTP-transport, authorization or many tools** —
then the framework is justified.

Next: [Healthcheck →](./health)
