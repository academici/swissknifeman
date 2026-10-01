# mAInd — Requirements Document

> **Status:** Draft v0.1 · June 2026 — **historical document of the original design.**
> **Repository:** `academici/maind`
> **Slogan:** The central intelligence layer of the academici ecosystem

> [!NOTE]
> This is the original spec document. The implementation diverged from it in some places: the graph engine is pure
> **stdlib + federation** (and not graphify like engine), graphify — separate MCP-layer above the code
> project. Current architecture and API see [`docs/architecture.md`](docs/architecture.md),
> [`docs/ecosystem.md`](docs/ecosystem.md) and `docs/guide/*` (and [`CLAUDE.md`](CLAUDE.md)).

---

## 1. Review

**mAInd** — the main hub of the entire ecosystem academici. This is not a utility or a help package - it is
living brain: stores long-term memory of agents, builds a graph of connections between entities, coordinates
is a swarm of agents and is a single source of truth about the topology of all projects.

The package combines three donor components and adds a new orchestration layer on top:

| Source | What goes into mAInd |
|:---|:---|
| `academici/swissknifeman` | Module `agent-memory` (`.agentmemory/`) in full |
| `safishamsi/graphify` | Graph engine: nodes, edges, traversal |
| `academici/brain` | `.projects.json` → becomes `config.json` (extended version) |

---

## 2. Positioning in the ecosystem

```
┌─────────────────────────────────────────────────────┐
│                    mAInd (this package)               │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │ agent-memory │  │   graphify   │  │  agents   │ │
│  │  (from SKM)    │  │  (connection graph│  │  runtime  │ │
│  └──────────────┘  └──────────────┘  └───────────┘ │
│               ↕ config.json ↕                       │
└─────────────────────────────────────────────────────┘
         ↑                    ↑
  swissknifeman             brain
  (skills / skills)     (documentation)
```

**mAInd** — top of the hierarchy. The remaining packages connect to it, and not to each other directly.

---

## 3. What is transferred from swissknifeman

### 3.1 Module agent-memory

Current location in swissknifeman: `.agentmemory/` — worker config `iii-*`.

B mAInd this module becomes the first class rather than a subdirectory.

**Moved in its entirety:**

- `.agentmemory/iii-config.yaml` → `config/memory/iii-config.yaml` (new path)
- Entire worker runtime: `iii-http`, `iii-state`, `iii-queue`, `iii-pubsub`, `iii-cron`,
  `iii-stream`, `iii-observability`
- `data/state_store.db` and `data/stream_store` — state stores
- All MCP-integration via `agentmemory` server (ports 4111/4112)

**What is expanded:**

- `iii-state` gets the second adapter: `graph` (via graphify) — to store relationships as
  first-class citizens next to KV-memory
- `iii-observability` switches to `service_name: maind` and full pipeline logs in stdout
- Added `iii-agents` worker - register of running agents with heartbeat

**What remains in swissknifeman:**

- Everything related to skills: `skills.json`, `buckets.json`, profiles, registry, vendor
- Installation logic/synchronization of skills in IDE-adapters

After transfer swissknifeman gets `agent-memory` as a dependency on mAInd, and not
keeps it in his possession:

```json
// swissknifeman/package.json — after transfer
{
  "dependencies": {
    "@academici/maind": "^1.0.0"
  }
}
```

---

## 4. What is added: Graphify

**Repository:** [safishamsi/graphify](https://github.com/safishamsi/graphify)

Graphify is built in as a graph engine for storing and traversing connections between ecosystem entities:
projects, agents, memory, skills.

**Integration:**

- Each entity in `agent-memory` gets the graph identifier (node)
- Relationships between entities (project → uses → skill, agent → wrote → memory) — edges
- API mAInd provides unified interface: `memory.get()` + `graph.neighbors()` in one call
- Graphify becomes the second backend for `iii-state` along with KV-file

**Types of entities in the graph:**

| Node type | Description |
|:---|:---|
| `project` | Ecosystem Project (from `config.json`) |
| `agent` | Launched agent with session ID |
| `memory` | Agent long-term memory unit |
| `skill` | Skill from swissknifeman |
| `entity` | Arbitrary named entity (user, document, fact) |

**Edge types:**

| Edge type | Description |
|:---|:---|
| `uses` | Project/agent uses skill |
| `knows` | Agent has access to a memory unit |
| `relates_to` | Communication between two memories |
| `belongs_to` | Memory/agent belongs to the project |
| `depends_on` | Cross-project dependency |

---

## 5. Configuration: `config.json`

`config.json` (in the root of the monorepo, not in the package maind) — main node config. Is
**superset** `.projects.json` from `brain`. Legacy-name `.maind.json` is picked up for
backward compatible.

### 5.1 Relation to `.projects.json`

`.projects.json` from `brain` does not disappear - it remains **fallback-config** for reverse
compatibility. Priority logic:

```
config.json   (primary — at the root of the monorepo, if any)
    ↓ fallback
.maind.json   (legacy-name of the same config - backward compatibility)
    ↓ fallback
.projects.json  (legacy — read only, only fields compatible with brain)
```

CLI mAInd reads first at startup `config.json` (then legacy `.maind.json`), and if it
no - picks up `.projects.json` with migration warning.

### 5.2 Schema `config.json`

```jsonc
{
  // ── Meta ──────────────────────────────────────────────────────────
  "_version": "1",
  "_comment": "Main node config mAInd. Superset .projects.json",

  // ── Node identification ────────────────────────────────────────────
  "node": {
    "id": "brain",                      // unique slug node
    "name": "Academici Brain",          // human readable name
    "role": "primary",                  // primary | secondary | mirror
    "description": "Central knowledge and agent hub"
  },

  // ── Memory ────────────────────────────────────────────────────────
  "memory": {
    "enabled": true,
    "config_path": "config/memory/iii-config.yaml",
    "http_port": 4111,
    "stream_port": 4112,
    "data_dir": "./data"
  },

  // ── Graph ──────────────────────────────────────────────────────────
  "graph": {
    "enabled": true,
    "adapter": "graphify",              // graphify | memory | disabled
    "persist": true,
    "persist_path": "./data/graph.db"
  },

  // ── Agents ────────────────────────────────────────────────────────
  "agents": {
    "registry_enabled": true,
    "heartbeat_interval_ms": 30000,
    "max_idle_ms": 300000,
    "definitions": [
      // Descriptors of agents running on this node
      {
        "id": "vault-architect",
        "description": "Senior architect for brain vault",
        "skills": ["architect", "oss-dev"],
        "memory_scope": "project:brain",
        "autostart": false
      }
    ]
  },

  // ── Projects (superset .projects.json) ─────────────────────────
  "projects": [
    {
      // Fields compatible with .projects.json (legacy)
      "id": "brain",
      "name": "Brain",
      "repo": "academici/brain",
      "local_path": "~/projects/brain",
      "type": "obsidian-vault",

      // Extensions mAInd
      "memory_scope": "project:brain",  // private project memory bucket
      "agents": ["vault-architect"],    // associated agents
      "tags": ["primary", "docs"],
      "namespaces": ["axioma"],         // graph link isolation groups+memory; ["*"] — general infrastructure
      "status": "active"                // active | archived | planning
    },
    {
      "id": "swissknifeman",
      "name": "SwissKnifeMan",
      "repo": "academici/swissknifeman",
      "local_path": "~/projects/packages/swissknifeman",
      "type": "node-package",

      "memory_scope": "project:swissknifeman",
      "agents": [],
      "tags": ["package", "skills"],
      "namespaces": ["*"],
      "status": "active"
    }
  ],

  // ── Integrations ────────────────────────────────────────────────────
  "integrations": {
    "swissknifeman": {
      "enabled": true,
      "skills_sync": true              // automatically improve new skills
    },
    "brain": {
      "enabled": true,
      "projects_sync": true,           // sync from .projects.json at startup
      "sync_direction": "import"       // import | export | bidirectional
    }
  },

  // ── MCP-servers ───────────────────────────────────────────────────
  "mcp": {
    "servers": [
      {
        "name": "agentmemory",
        "transport": "http",
        "url": "http://127.0.0.1:4111/mcp",
        "enabled": true
      },
      {
        "name": "graphify",
        "transport": "http",
        "url": "http://127.0.0.1:4113/mcp",
        "enabled": true
      }
    ]
  },

  // ── Observability ─────────────────────────────────────────────────
  "observability": {
    "service_name": "maind",
    "log_level": "info",
    "metrics_enabled": true,
    "traces_enabled": false
  }
}
```

### 5.3 Fields compatible with `.projects.json`

The following fields are required for compatibility with `brain` CLI (`brain sync`):

| Field | Type | Description |
|:---|:---|:---|
| `projects[].id` | string | Unique slug project |
| `projects[].name` | string | Human readable name |
| `projects[].repo` | string | GitHub slug `owner/repo` |
| `projects[].local_path` | string | Local path |
| `projects[].type` | string | Project type |

All other fields are extensions mAInd and ignored `brain` when reading fallback.

---

## 6. Package architecture

### 6.1 Repository structure

```
academici/maind/
├── config.example.json       ← example config (as .swissknife.example.json in SKM)
├── config/
│   └── memory/
│       └── iii-config.yaml   ← moved from SKM/.agentmemory/
├── lib/
│   └── maind/
│       ├── __init__.py
│       ├── cli.py            ← CLI: maind start | status | agents | graph
│       ├── config.py         ← parsing config.json + fallback .projects.json
│       ├── memory.py         ← interface to agent-memory workers
│       ├── graph.py          ← interface to graphify
│       ├── agents.py         ← agent registry, heartbeat, lifecycle
│       ├── projects.py       ← project registry, sync with brain
│       └── mcp.py            ← MCP server for external agents
├── bin/
│   └── maind                 ← entry point CLI
├── data/                     ← gitignored, runtime data
│   ├── state_store.db
│   ├── stream_store/
│   └── graph.db
├── tests/
├── docs/
├── install.sh
├── package.json
└── README.md
```

### 6.2 Components

**Memory Layer** (`lib/maind/memory.py`)
Wrapper over `iii-*` workers. Provides API:
- `memory.store(scope, key, value, ttl?)` — save fact
- `memory.recall(scope, query)` — semantic memory search
- `memory.forget(scope, key)` — delete fact
- `memory.export(scope)` — dump of entire scope memory

**Graph Layer** (`lib/maind/graph.py`)
Wrapper over graphify. API:
- `graph.node(type, id, meta?)` — create/update node
- `graph.edge(from, type, to, meta?)` — create/update edge
- `graph.neighbors(id, edge_type?, depth?)` — neighbor traversal
- `graph.path(from, to)` — shortest path between nodes
- `graph.subgraph(ids[])` — subgraph over a set of nodes

**Agent Registry** (`lib/maind/agents.py`)
- Agent registration at startup: `agents.register(id, meta)`
- Heartbeat loop: update `last_seen` every N seconds
- `agents.list(status?)` — active/all agents
- `agents.kill(id)` — forced stop
- `agents.scope(id)` — isolated memory + graph scope agent

**Projects Registry** (`lib/maind/projects.py`)
- Loading `config.json` with fallback on `.projects.json`
- `projects.list(status?)` — all projects
- `projects.get(id)` — project by id
- `projects.sync_from_brain(path)` — import from `.projects.json`
- `projects.export_to_brain(path)` — export compatible subset

**MCP Server** (`lib/maind/mcp.py`)
mAInd itself is MCP-server for external agents (Claude, Cursor, etc.).
Exhibits tools:
- `maind_memory_store`, `maind_memory_recall`
- `maind_graph_query`, `maind_graph_neighbors`
- `maind_agents_list`, `maind_projects_list`

---

## 7. CLI

```bash
# Start of all workers
maind start

# Run only memory workers
maind start --only memory

# Run graph only
maind start --only graph

# Worker status
maind status

# List of agents
maind agents list
maind agents kill <id>

# Graph
maind graph query --from project:brain --depth 2
maind graph stats

# Projects
maind projects list
maind projects sync --from brain --path ~/projects/brain

# Migration
maind migrate from-brain .projects.json    # import legacy config
maind migrate from-skm .agentmemory/       # import module from SKM
```

---

## 8. Implementation phases

### Phase 1 — Foundation (Memory + Config)

- [ ] Create repository `academici/maind`
- [ ] Move `.agentmemory/` → `config/memory/iii-config.yaml`
- [ ] Implement `config.py` with support `config.json` + fallback `.projects.json`
- [ ] Implement `memory.py` (wrapper over iii-*)
- [ ] CLI: `maind start`, `maind status`
- [ ] `config.example.json` with full schematic
- [ ] `install.sh` (analogue brain/swissknifeman)
- [ ] Update swissknifeman: remove `.agentmemory/`, add dependency on maind

### Phase 2 — Graph Layer

- [ ] Integrate graphify as a dependency
- [ ] Implement `graph.py` — all methods API
- [ ] Expand `iii-state` for dual-backend (KV + graph)
- [ ] Automatic registration of projects from `config.json` like nodes
- [ ] CLI: `maind graph query`, `maind graph stats`

### Phase 3 — Agent Runtime

- [ ] Implement `agents.py` — registry + heartbeat
- [ ] Isolated memory and graph scopes for each agent
- [ ] Add `iii-agents` worker in `iii-config.yaml`
- [ ] CLI: `maind agents list`, `maind agents kill`
- [ ] Integration with `brain` agents (AGENTS.md)

### Phase 4 — MCP + Integrations

- [ ] MCP-server: tools for memory/graph/agents/projects
- [ ] `.mcp.json` with entry `maind` server
- [ ] Sync with `brain` via `projects.sync_from_brain()`
- [ ] Sync skills via swissknifeman API
- [ ] Update `brain/CLAUDE.md` — add mAInd to card MCP-servers

---

## 9. Dependencies

| Package | Version | Role |
|:---|:---|:---|
| `graphify` (safishamsi) | latest | Graph engine |
| `agent-memory` (iii-*) | from SKM | Memory workers |
| `@anthropic/sdk` | latest | MCP protocol |
| `yaml` | ^2 | Parsing iii-config.yaml |
| `zod` / `jsonschema` | latest | Validation config.json |

---

## 10. Alternative names

The following names were considered before final selection `mAInd`:

### Synapse
**Synapse** — point of signal transmission between neurons. Ideally describes the role of a package as
intermediary between agents: it is through the synapse that one agent «knows» about something else. Minus - it sounds
as a connecting layer rather than as a central brain. More suitable for middleware or event-bus.

### Loom
**Loom** — weaves threads of connection between agents and memory into a single fabric.
A strong figurative metaphor for a graph engine. Short, sonorous, non-standard for AI-packages.
Disadvantage - not obvious AI-context: without explanation it sounds like weaving/crafts tool.

### Axon
**Axon** — long process of a neuron through which a signal passes from one neuron to another.
Technically accurate (packet passes information between agents), short, memorable.
Minus - Axon already taken: popular Java-framework for event-driven microservices.

### Apex
**Summit, highest point** — direct metaphor «of the main package» ecosystems.
Universally readable in any language, easy to pronounce. Marketing strong.
Disadvantage - very widely used (APEX Oracle, Apex Legends etc.), hard to google.

### Aipex
**AI + Apex** — hybrid word. Instantly understandable AI-context + meaning «top of hierarchy».
Sounds like a startup product name. Minus - the writing is not obvious (aipex vs aipix vs AIpex),
is more difficult to perceive by ear.

### Lumex
**Lumen + Memory eXchange** — light of knowledge and exchange of memory. Sounds like a medtech brand or
optics. Unusual for AI-world - stands out. Minus - the metaphor is indirect, the essence of the package is not
reads without explanation. Good as a product name/SaaS, is weaker as a package name.

---

> **Final choice: `mAInd`** — is the only name that simultaneously: (1) instantly
> reads as «mind/brain», (2) contains **AI** as a visual marker, (3) is pronounced like
> an ordinary English word, (4) no conflicts with existing packages in npm/PyPI,
> (5) fits seamlessly into the ecosystem next to `brain`, `swissknifeman`.

