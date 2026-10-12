# Ecosystem: three-pack philosophy

Three academic ecosystem packages - **swissknifeman**, **brain** and **maind** — are arranged according to
one principle: every **is self-sufficient** and works alone, but they communicate **optional**,
through paths in configs. Remove the path and the packages are autonomous again. This keeps the system predictable:
nothing breaks if there is no neighbor.

## Roles

| Package | Layer | What it does |
|:--|:--|:--|
| **swissknifeman** | capabilities | synchronizes **skills + hooks** to the project - «pumps up the agent» for the task |
| **brain** | knowledge/docks | Obsidian-vault + demon `docs-watcher`, keeps documentation in sync with repositories |
| **maind** | hub + command post | owns the shared **memory** and **graph**, rolls them out to projects, monitors and orchestrates others |

swissknifeman gives the project *skills*, maind — *shared memory and graph + coordination*, brain — *knowledge*.
They complement each other and each is valuable in its own right.

```mermaid
graph TB
  subgraph skm["swissknifeman — capabilities layer"]
    SK["skills (registry)"]
    HK["hooks: auto-approve, memory"]
  end
  subgraph br["brain — knowledge layer/docks"]
    VA["Obsidian vault"]
    DW["docs-watcher daemon"]
  end
  subgraph md["maind — hub + command post"]
    MEM["agent-memory daemon"]
    GR["connection graph"]
    CC["provision · monitor · orchestrate"]
  end
  proj["project"]
  skm -. "skills + hooks" .-> proj
  md -. "memory + graph" .-> proj
  br -. "docs-sync" .-> proj
  md -. "orchestrates" .-> skm
  md -. "orchestrates" .-> br
```

## Principle: connected, but work separately

Integration - **opt-in via the path in the config**, with mild degradation:

- **maind** without the memory daemon - the graph and project registry still work.
- **brain** without maind — takes projects from his discovery by control-files.
- **swissknifeman** is always autonomous - it has its own register of connected projects.

```mermaid
flowchart LR
  subgraph alone["everyone for themselves"]
    A1["maind: your registry.json"]
    A2["brain: yours discovery"]
    A3["swissknifeman: your registry"]
  end
  subgraph together["are linked through paths in the config (opt-in)"]
    T["registry.json ↔ brain maind_config_path ↔ project skills-lock"]
  end
  alone -. "add path" .-> together
  together -. "remove path" .-> alone
```

## Single hub + namespace's

Memory and graph - **alone for the entire ecosystem**, on the hub maind. Isolation - logical and
namespace'am: count - federation (graph per project + index), memory - buckets
(`project:<id>`/`ns:<name>`/`global`). Common within a group, isolated between groups. This and
yes «common brain» without separate daemons per project.

```mermaid
graph TD
  subgraph hub["maind hub"]
    D["agent-memory daemon · 4111/4112"]
    NS["memory buckets: project:&lt;id&gt; · ns:&lt;name&gt; · global"]
    G["data/graphs/*: graph per project + _index.db (federation)"]
  end
  flexcrm -->|MCP, bucket project:flexcrm + ns:axioma| hub
  brain -->|MCP, bucket project:brain| hub
  others["… other projects"] -->|MCP| hub
```

More about topology and internal layers - [Architecture](./architecture).

## Onboarding a new project

The ultimate goal is one team. Creating a project → swissknifeman adds the necessary skills and hooks
(automatically + you can select specific) → maind connects the project to the general brain (memory + graph).
Every step **standalone-safe**: there is no neighbor - the step is skipped with a warning, onboarding moves on.

```mermaid
sequenceDiagram
  actor Dev
  participant maind
  participant skm as swissknifeman
  participant proj as project
  participant brain
  Dev->>maind: maind onboard &lt;project&gt;
  maind->>maind: register in registry.json
  maind->>skm: integrate (skills + hooks)
  skm->>proj: .claude/skills + hooks + skills-lock.json
  maind->>proj: deploy — agent-memory MCP (scope project:id) [+ code graph/Serena]
  maind->>maind: derive graph (composer/doc/override/skills → project store + index)
  opt --with-brain
    maind->>brain: repository for docs-sync
  end
  maind-->>Dev: report (steps · deployed · graph)
```

## Config and data flow

maind — **reader everyone** key files and **writer** only `registry.json`, MCP-configs
project and **own** `.claude/settings.local.json` (hub trust in ecosystem projects,
see [Workspace](./guide/workspace)). Project skills described `skills-lock.json` (composes
swissknifeman + Laravel Boost, swissknifeman wins). brain holds his `<vault>/.projects.json`
for docs-watcher.

```mermaid
flowchart LR
  MJ["registry.json — project registry (writes maind)"]
  PJ["&lt;vault&gt;/.projects.json — docs-watcher (brain)"]
  SL["skills-lock.json — skill map (skiller lock)"]
  BJ["boost.json — Laravel Boost"]
  MC[".mcp.json / .cursor/mcp.json — servers (writes maind deploy)"]
  BJ -->|compose| SL
  SL -->|skills_sync| MJ
  MJ -->|import / export| PJ
  MJ -->|deploy| MC
```

## maind as a command post - 4 layers

```mermaid
flowchart TD
  P["1. Provision — maind deploy<br/>unroll memory+graph for projects"]
  M["2. Monitor — maind projects status --json<br/>what is configured · that is running · modes"]
  O["3. Orchestrate — maind run &lt;proj&gt; &lt;cap&gt;<br/>pull commands brain / swissknifeman"]
  G["4. GUI — panel above status --json"]
  P --> M --> O --> G
```

If layer 2 (`status`) hold **JSON-first**, then GUI (layer 4) — subtle add-on to the same
contract, and not separate correspondence. Each layer is a separate command maind; see [CLI](./guide/cli).

## Source of Truth

| What | Where does he live? | Who writes |
|:--|:--|:--|
| Project Registry | `registry.json` in the maind state directory (legacy: `config.json` at the root of the monorepo) | maind (`projects.write_registry` — sole writer) |
| Node settings | `[maind]` table of the layered config (`config.example.toml`) | a person (`swissknifeman config set`) |
| Trust Claude to projects | `<maind>/.claude/settings.local.json` | maind (`workspace sync` from the registry) |
| Shared memory | agent-memory demon (buckets `project:<id>`/`ns:<name>`/`global`) | projects are written to their `project:<id>`, cross-ref — in `ns:<group>` |
| Connection graph | `data/graphs/<id>.db` + `_index.db` (federation) | maind `derive` from composer/Brain/override/skills |
| Project skill map | `<project>/skills-lock.json` | `skiller lock` |
| Project documentation | vault ↔ repo | `brain sync` (docs-watcher) |

This page is the canonical source for ecosystem philosophy. swissknifeman and brain link here.
