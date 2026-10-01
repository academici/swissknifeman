# Connection graph

A graph is **topology between projects**: who depends on whom, who provides what, what
skills are used. Engine is clean **stdlib** (BFS/shortest path, no third-party dependencies),
persistent in node-link JSON. Layout - **federation**: graph per project (`data/graphs/<id>.db`) plus
thin regenerated index `_index.db` (see [Federation](./federation)).

> This graph (maind-graph) links **topology between projects**; memory (`agent-memory`) links
> **context/facts**. These are independent hub mechanisms, they work according to [namespace'am](./namespaces). Graph
> *code inside the project* (characters/files) — is a separate plane, [code graph (Serena)](./code-graph).

## Types of nodes and edges

| Node (`<type>:<key>`) | | Rib | |
|:--|:--|:--|:--|
| `project` | ecosystem project | `depends_on` | cross-project dependency (from composer) |
| `package` | composer/npm-package | `requires` | project requires package |
| `skill` | skill from swissknifeman | `provided_by` | package/skill provided by the project/tool |
| `tool` | swissknifeman / boost / brain | `uses` | project uses skill / doc-connection |
| `doc` · `agent` · `memory` · `entity` | other domains | `relates_to` · `belongs_to` · `knows` | override / other |

The nodes are named `<type>:<key>` (for example `project:brain`) — conflict-free domain merging,
type is inferred from id.

## Where do connections come from? (derive, without manual take)

`maind graph derive` builds project stores from **sources of truth**, marking the edges with a plan
(`code|doc|meta|runtime`) and source (`via`) — `derive.py`:

| Plan (`via`) | Source | Ribs |
|:--|:--|:--|
| `code` | `composer.json`/`package.json` (+ path-repos) | `project ─requires→ package`, `package ─provided_by→ project`, cross `project ─depends_on→ project` |
| `doc` | Brain frontmatter `uses:/used_by:` (**read only**) | `project ─uses→ project` |
| `override` | `<repo>/.maind.graph.json` | declared `relates_to`/… (runtime/API) |
| `skills` | `skills-lock.json` | `project ─uses→ skill ─provided_by→ tool` |

The truth remains in composer/Brain/lock — `_index.db` is just a regenerated cache. Project config fields
(`dependencies`/`agents`) graph **do not materialize**: to declare a relationship that is not in the code,
use `.maind.graph.json` (plan `override`).

## API (`graph.py` — primitive)

```python
g.neighbors("project:maind", depth=1, direction="in")   # who depends on maind
g.path("project:flexcrm", "project:azguard")            # shortest path (BFS)
g.subgraph(["project:brain", "project:maind"])          # induced subgraph
g.stats()                                               # nodes/edges/components/degree
```

You need to read the federated graph via `federation.graph_reader(env, config)` (single facade),
rather than opening the store directly.

## CLI

```bash
maind graph derive --all                 # collect graphs of all projects from sources
maind graph rebuild                      # rebuild only _index.db
maind graph stats                        # federation summary
maind graph query --from project:flexcrm --depth 2 [--edge-types depends_on]
maind graph neighbors --node project:maind --direction in
maind graph --project flexcrm            # graph of one project
maind graph --cross [--namespace axioma] # cross-project layer (opt. one group)
maind graph export --project flexcrm     # → Mermaid (one project)
maind graph export --cross               # → Mermaid (entire cross-project layer)
```

## Visualization (Mermaid)

Inter-project maind-column no webUI (unlike memory - there is a viewer :3113). The most reliable
way to see it with a picture - export to **Mermaid**: is rendered directly into GitHub/VitePress/any
md-viewer, without runtime and daemons (nothing «get lost»).

```bash
maind graph export --cross > docs/graph.md   # paste into the dock - it will be drawn as a diagram
maind graph export --project corex            # one project, copy-paste (wrapped in ```mermaid)
```

Output - finished block ` ```mermaid … ``` ` (node form: project — rectangle, package —
rounded). `--raw` removes the wrapper (to insert into your layout).

## Example: what will you see

Collect the project graph and view its subgraph (real output for `corex`):

```console
$ maind graph derive --project corex
  corex              nodes 12, edges 14 (code 10, doc 5, override 0)

$ maind graph view --project corex
project graph corex: 12 nodes, 14 edges
  package:corex/core               package    core
  package:corex/crm                package    crm
  project:flexcrm                  project
  project:azguard                  project
  …
  package:corex/core           —provided_by→ project:corex             [code]
  project:corex                —requires→ package:axioma-studio/azguard-core  [code]

$ maind graph stats
Graph: 15 nodes, 22 edges, 1 component(s), max degree 14
  nodes:  package=9, project=6
  edges: provided_by=9, requires=7, uses=6
```

## Same requests from the agent (MCP)

In a project session, these connections are available as MCP-server tools `maind` — the agent calls them himself:

| Tool | Arguments | Replies to |
|:--|:--|:--|
| `maind_graph_project` | `{ "project": "corex" }` | project subgraph + outgoing cross-edges |
| `maind_graph_neighbors` | `{ "node": "project:corex", "depth": 1, "direction": "in" }` | who depends on corex |
| `maind_graph_query` | `{ "from": "project:flexcrm", "depth": 2, "edge_types": "depends_on" }` | traversal from node by edge type |
| `maind_graph_path` | `{ "from": "project:flexcrm", "to": "project:azguard" }` | shortest path between projects |

This **pull**: tools are passive, the call is initiated by the model (skill `ecosystem-mcp` tells you when).
Memory - separate tools of the same session: `maind_memory_recall` / `maind_memory_store` / `maind_memory_links`.

## Adapter

`graph.adapter` in the config: `federation` (default, single layout) or `disabled`
(graph commands not available). Obsolete `memory`/`graphify`/`networkx` are accepted with a warning
and are normalized to `federation`.

Next: [Federation →](./federation)
