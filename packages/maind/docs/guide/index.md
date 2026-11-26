# What is mAInd

**mAInd** — central node («brain») ecosystems academici. This is not an auxiliary
utility: one common hub stores long-term memory of agents, builds a graph of connections between
entities and maintains a register of running agents and projects. Other packages (`brain`,
`swissknifeman`, …) connect to it as clients, not to each other.

## What's inside

| Layer | Module | Role |
|:--|:--|:--|
| Memory | `memory.py` | orchestration Node-demon agent-memory + HTTP-wrapper with scope'ami |
| Graph | `graph.py` | property-connection graph (stdlib), persistent in node-link JSON |
| Agents | `agents.py` | registry of running agents with heartbeat |
| Projects | `projects.py` | project registry (superset brain `.projects.json`) |
| MCP | `mcp.py` | maind like MCP-server for external agents |

## Principles

- **Single hub + scopes.** One memory daemon and one graph per hub; isolation of projects - by
  `namespace`/scope, rather than individual instances. See [Architecture](../architecture).
- **Python + bash.** Core on stdlib (like `swissknifeman` / `brain`); npm — only for
  memory and documentation daemon.
- **Ports from env/config.** No hardcodes - so that the hub does not conflict with another node.

## Where did it come from?

mAInd combines three sources and adds an orchestration layer:

- **agent-memory** (`iii-*` workers) — from the ecosystem; lived in Brain, is now canonical in maind.
- **connection graph idea** (historically - external engine «graphify») — we have implemented on stdlib
  (federation); graph **code** inside the project - a separate optional layer (Serena), see [code graph](./code-graph).
- **`.projects.json`** from brain — becomes `config.json` (extended version, at the root of the monorepo).

Next: [Installation →](./installation)
