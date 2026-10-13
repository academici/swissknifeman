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
                 │  <state>/maind/  registry.json · agents.json        │
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
./install.sh                       # symlink ~/.local/bin/maind
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
| `maind mcp [tools [--json]]` | run maind like MCP-server (stdio); `tools` prints the tool list and `tools_digest` |
| `maind topology <show\|init> [--json]` | machine map of the hub nodes (`<state>/maind/topology.json`) |
| `maind health [--plan-repair\|--apply-repair]` | check a project's connection; repair is read-only or applied |
| `maind doctor [--json]` | environment diagnostics; `--json` is a list of `check-result/v1` |

---

## Config: settings and registry

The node config has two parts with different writers:

- **Settings** (what a person edits: `node`, `memory`, `graph`, `code_graph`, `agents` timings,
  `integrations`, `mcp` policy, `observability`) — the `[maind]` table of the layered config (the
  machine `config.toml`, the project's `.swissknifeman/config.toml`, `SKM_MAIND_*` variables).
  Schema `configs/config.schema.json`; every key with its default is in
  [config.example.toml](config.example.toml).
- **Registry** (what maind writes: `projects[]`, `namespaces`, `agents.definitions`, `mcp.servers`,
  `providers`, `role_packs`) — `<state>/maind/registry.json`, written only by maind. Template:
  [configs/registry.example.json](configs/registry.example.json). Superset `.projects.json` from `brain`.

Until `swissknifeman upgrade` moves the values, the legacy node file (`config.json` at the root of
the monorepo, or `.maind.json`) is read with one `MAIND_LEGACY_CONFIG` warning: its settings while no
`[maind]` table is set, its registry while there is no `registry.json` (maind then writes the
registry back into that file). If there is no config at all, maind reads legacy `.projects.json` in
mode read-only (with migration warning).

## Partners

maind imports only itself and `aicore`. It reaches `harness`, `analyst`, `skiller` and `brain` through their public
commands with JSON output, found by `aicore.util.partners` (`SKM_<NAME>_BIN`, then `SKM_<NAME>_ROOT/bin/<name>`, then `PATH`;
the old `MAIND_*_BIN` variables work with one warning). A missing partner prints `PARTNER_UNAVAILABLE: <partner> not found
(set SKM_<P>_ROOT or put <partner> on PATH)` and the step degrades: provider steps are skipped without harness, `maind
analyze` marks the run report unavailable without analyst. Details: [docs/ecosystem.md](docs/ecosystem.md).

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

`maind mcp` — stdio JSON-RPC server (11 tools; protocol versions `2025-06-18` and `2024-11-05`, the requested one when supported, otherwise the newest): memory (`store`/`recall`/`forget`), graph
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

## Skills

The plugin ships the skills `cross-project-coordinator`, `local-topology`, `shared-memory` and
`swissknifeman-locator`, and the agent `code-coordinator` (`maind:code-coordinator`). They live in
`packages/maind/skills/` and are released with the module.
A project gets them through the `system` bucket of `skiller`: `skiller connect` enables the plugin `maind` and
`skiller sync` copies the skills into the project; the plugin can also be installed on its own.

## Development

```bash
scripts/test.sh          # unittest (no third party dependencies and no live daemon)
scripts/validate.sh      # py_compile + bash -n + JSON + tests
bash scripts/test-integration.sh   # from the hub root: tests with partners wired
npm run docs:dev         # documentation (VitePress)
```

Conventions: stdlib-only Python, context via `Env` (without modular globals), atomic
entry JSON, Russian-language messages. More details - [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Dmitry Vostrikov
