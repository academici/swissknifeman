# mAInd

> Central node of the ecosystem academici: **agent memory · connection graph · registry of agents and projects · MCP-server**.

**mAInd** — this «brain» ecosystems. One common hub stores the agents' long-term memory,
builds a graph of connections between entities (projects, agents, memory, skills) and coordinates
registry of running agents. Other projects (`brain`, `swissknifeman`, …) are connected
to it as clients.

Core - **Python + bash** (like `swissknifeman` and `brain`): slim launcher `bin/maind`,
all logic in `lib/maind/*.py` on stdlib, tests for `unittest`. npm is only needed for
Node-memory daemon and documentation build.

---

## Topology: single hub + namespace's

```
                 ┌──────────────────── maind hub ─────────────────────┐
                 │  agent-memory daemon (Node, 4111/4112)             │
   maind start ─▶│   buckets: project:<id> · ns:<name> · global          │
                 │  data/graphs/*  (graph per project + _index.db, stdlib)│
                 │  ~/.maind/  agents.json · projects.json             │
                 │  maind mcp  (stdio JSON-RPC: 11 tools)              │
                 └───────▲────────────▲────────────▲──────────────────┘
            MCP/HTTP     │            │            │
                      brain     swissknifeman   erp-sdk …   (clients, isolation by namespace)
```

Through the hub they go **three independent binding mechanisms**, all work according to namespace'am:

- **agent-memory** (memory/context) — one Node-daemon; logical isolation, per bucket:
  `project:<id>` (private) · `ns:<name>` (group) · `global` (entire ecosystem). Within the group
  memory is shared, isolated between groups.
- **maind-graph** (topology between projects) — federation: graph per project (`data/graphs/<id>.db`)
  + thin `_index.db`. Built from the sources of truth (`derive`: composer/Brain/override/skills),
  not from a manual take. Inter-project edge - only inside the common one namespace.
- **code graph** (characters/files inside the project) — engine **Serena** (LSP, via `uvx`), per-project
  MCP-server; rolls out `deploy --with-code` (historically «graphify»; `--with-graphify` — alias).
- **Ports are not hardcoded** — from `.env` / `config.json` (default 4111/4112), so as not to
  conflict with another node.

---

## Installation

```bash
git clone <repo> maind && cd maind
./install.sh                       # symlink ~/.local/bin/maind + directory ~/.maind
maind doctor                       # environment check

# Memory (optional, needed Node):
npm install                        # puts @agentmemory/agentmemory
cp .env.example .env               # host ports
maind start --only memory
```

## Quick start

```bash
maind migrate from-brain ~/Vaults/Brain/.projects.json   # import projects + graph
maind start                         # increase memory + graph
maind status                        # node summary
maind graph query --from project:brain --depth 2
maind projects list
```

---

## CLI

| Command | Purpose |
|:--|:--|
| `maind start [--only memory\|graph]` | raise node workers |
| `maind status [--json]` | summary: memory, graph, agents, projects |
| `maind memory <start\|stop\|status>` | memory daemon lifecycle |
| `maind graph <query\|stats\|neighbors>` | traversal of the relationship graph |
| `maind agents <list\|register\|heartbeat\|kill>` | agent registry |
| `maind projects <list\|sync --from brain>` | project registry |
| `maind migrate <from-brain\|from-agentmemory>` | import from brain / agent-memory |
| `maind mcp` | run maind like MCP-server (stdio) |
| `maind doctor` | environment diagnostics |

---

## Config `config.json`

Main node config - `config.json` **at the root of the monorepo** (not in package maind; resolver
goes up to the directory with `packages/`). Legacy-name `.maind.json` is still being picked up.
Superset `.projects.json` from `brain`. If there is no config, maind reads legacy `.projects.json`
in mode read-only (with migration warning).
Full diagram - in [config.example.json](config.example.json). Key sections: `node`,
`memory`, `graph`, `agents`, `projects[]`, `integrations`, `mcp`, `observability`.

## Memory (scopes)

HTTP-demon contract (agentmemory 0.9.x, verified live): `GET /agentmemory/health` ·
`POST /agentmemory/remember {namespace, content, type}` ·
`POST /agentmemory/search {query, namespace}`. maind orchestrates the daemon
(`start/stop/status`) and speaks HTTP, collecting requests for project buckets
(`project:<id>` · `ns:<name>` · `global`).

## Graph

Engine is clean stdlib (BFS-neighbors, shortest path, subgraph, statistics), persistent in
node-link JSON. Layout - **federation**: graph per project (`data/graphs/<id>.db`) + thin
regenerable `_index.db`; is built from sources of truth (`derive`), is read through a single
facade `federation.graph_reader`. `graph.adapter`: `federation` (default) | `disabled`.

## MCP

`maind mcp` — stdio JSON-RPC server (11 tools): memory (`store`/`recall`/`forget`), graph
(`query`/`neighbors`/`path`/`project`), `memory_links`, `agents_list`, `projects_list`,
`projects_status`. Client connection (`.mcp.json`):

```json
{ "mcpServers": { "maind": { "command": "<repo>/bin/maind", "args": ["mcp"] } } }
```

## Plugin Claude Code

maind is placed and how **plugin Claude Code** — thin face above CLI. After `./install.sh`:

```
/plugin marketplace add /path/to/swissknifeman   # single marketplace monorepo
/plugin install maind@swissknifeman
```

Appear slash-commands `/maind:*` (`onboard`, `sync`, `status`, `health`, `doctor`) — wrappers over
the same CLI. Plugin **MCP-does not support the server**: hub tools gives per-project server `maind` from
`.mcp.json` project. More details - [docs/guide/plugin.md](docs/guide/plugin.md).

---

## Development

```bash
scripts/test.sh          # unittest (no third party dependencies and no live daemon)
scripts/validate.sh      # py_compile + bash -n + JSON + tests
npm run docs:dev         # documentation (VitePress)
```

Conventions: stdlib-only Python, context via `Env` (without modular globals), atomic
entry JSON, Russian-language messages. More details - [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Dmitry Vostrikov
