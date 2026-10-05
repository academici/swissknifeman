# Config `config.json`

Main node config - `config.json` **at the root of the monorepo** (not in package maind);
resolver climbs up to the directory with `packages/`. Legacy-name `.maind.json`
is still picked up for backwards compatibility. Superset `.projects.json`
from brain. Full example with comments -
[`config.example.json`](https://github.com/academici/maind/blob/main/config.example.json).
Validation - on stdlib (without jsonschema): unknown top key fatal (with hint via
difflib), unknown nested - warning.

## Sections

| Section | Purpose |
|:--|:--|
| `node` | node identification: `id`, `name`, `role` (`primary`/`secondary`/`mirror`) |
| `memory` | `http_port`, `stream_port`, `data_dir`, `url`, `config_path` |
| `graph` | `adapter` (`federation` default / `disabled`) — federation single layout |
| `code_graph` | code graph policy: `command`/`args`/`server_name`, `ignores`/`workspace_ignores`, `language_by_type`, `initial_prompt`/`workspace_prompt`, `pre_index` (see below) |
| `agents` | `registry_enabled`, `heartbeat_interval_ms`, `max_idle_ms`, `definitions[]` |
| `projects[]` | projects (see below) |
| `providers` | optional fleet defaults provider selection; exact contract below |
| `namespaces` | optional registry namespace-groups: `{ id: { name, description } }` |
| `integrations` | `swissknifeman`, `brain` (sync) |
| `mcp` | `servers[]` — external MCP-node servers; `emit_example` (default-on `.mcp.json.example`, opt-out `false`); `perplexity_web` — hub-managed rolling keyless-bridge perplexity-web (see below) |
| `observability` | `service_name`, `log_level`, `metrics_enabled`, `traces_enabled` |

## Project

```jsonc
{
  // compatible with brain (.projects.json)
  "id": "brain", "name": "Brain", "repo": "academici/brain",
  "local_path": "~/Vaults/Brain", "type": "obsidian-vault",
  // extensions maind
  "memory_scope": "project:brain",     // private project memory bucket
  "agents": ["vault-architect"], "skills": [], "tags": ["docs"],
  "namespaces": ["axioma"],            // graph link isolation groups+memory; ["*"] = general infrastructure
  "graph_store": "hub",                // hub (data/graphs/<id>.db) | local (<repo>/.maind/graph.db)
  "code": false,                       // enable code graph (legacy-alias graphify); engine from section code_graph
  "code_command": "uvx",               // opt. binary code-MCP (override default from code_graph)
  "code_args": ["..."],                // opt. arguments; {root} → project path
  "code_server_name": "serena",        // opt. server name in .mcp.json
  "code_workspace": false,             // opt. override auto mode «single graph with packages/*» (auto, if available packages/)
  "code_ignores": ["vendor"],          // opt. per-project ignore list (otherwise from code_graph)
  "status": "active"                   // active | archived | planning
}
```

### Additional provider-managed MCP-servers

A project may advertise additional servers owned by another package, in
`projects[].mcp.extra_servers`. `maind deploy` adds them to a single semantic inventory
along with their `maind`/memory/code servers, checks for duplicates ID before recording and then
transmits them provider-managed renderer. Values - native MCP-objects (`command`, `args`,
`env` etc.); them owner is responsible for the content and lifecycle.

```jsonc
"mcp": {
  "extra_servers": {
    "analytics-capture": {
      "command": "python3",
      "args": [".codex/hooks/analytics-capture.py"]
    }
  }
}
```

`extra_servers` cannot override IDs, already owned `maind`, memory, code graph
or enabled integrations: such a conflict stops deploy before change target-files.

Old names `graphify` / `graphify_command` / `graphify_args` / `graphify_server_name` /
`graphify_workspace` are accepted as **legacy-alias** (backwards compatible).

## Provider selection

Optional `providers.defaults` sets fleet-provider selection layer, and
`projects[].providers` — stronger layer for precise project ID. Each layer follows
alone provider-config v1 contract (`contract_version` and non-empty `selection`), compatible
with project-owned `.swissknife.json#/providers`. In the absence of all provider-layers result
remains legacy Claude Code-only and nothing is written to disk.

Exact order precedence: operation override → project `.swissknife.json` →
`projects[].providers` → `providers.defaults` → synthetic legacy. Provider selection
is validated and returns provenance/diagnostics; it does not include provider, does not generate
artifacts and does not change existing `config.json` on its own.

Required for compatibility with brain fields: `id`, `name`, `repo`, `local_path`, `type`.
The rest are extensions maind (brain ignores them when reading fallback).

### Three directory layers and fact owner

The project directory exists in **three views** with one sync direction
(`integrations.brain.sync_direction:"import"`):

| Layer | File | Owns the fact |
|:--|:--|:--|
| **Source** | frontmatter control-notes Brain (`<Name>.md`) | what projects are there, `repo:` (path to code), doc-folders, **`visibility`** (`docs_public`) |
| **Cache** | `<vault>/.projects.json` (is generated brain, gitignored) | machine projection frontmatter — do not edit with your hands |
| **Tooling registry** | this `config.json` | imports directory + adds maind-fields (`namespaces`/`type`/`graph`/`mcp`) |

Catalog fields (`name`, `local_path`, `vault_path`, `type`, `enabled`, `docs_folders`) come
in `config.json` **import** (`maind projects sync --from brain`) — change them at frontmatter Brain,
not here (sync will be erased; shift `visibility` existing project is accompanied by warn).
maind-only projects (which are not in Brain) own these fields themselves.

**`repo` ≠ `local_path`** (intentional bridge between circuits, not to be confused): in `config.json` `repo` —
GitHub-slug `owner/name`, path to code - `local_path`. B brain-diagram `.projects.json` `repo` = **path
to code** (slug'but not there); on import maind puts it in `local_path`, a `repo` leaves under slug.
`visibility` in `docs_folders` — **cache** from frontmatter Brain (maind doesn't read it for behavior).

## Section `code_graph` (code graph policy)

The entire code graph policy is **in the config, not in the code** (you edit here, not in the sources maind).
`merge_defaults` imposes defaults, so the block is optional; only ask what you change.

```jsonc
"code_graph": {
  "command": "uvx",                    // engine (default Serena via uvx)
  "args": ["...","--project","{root}"],// {root} → project path
  "server_name": "serena",             // server name in .mcp.json project
  "language_by_type": { "php-package": "php", "node-package": "typescript" },
  "ignores": ["vendor","node_modules","packages","..."],          // default mode
  "workspace_ignores": ["vendor","**/vendor","..."],              // single graph mode (packages not ignored)
  "pre_index": true                    // background warm-up-indexing when turned on
}
```

In the project `code_providers: ["claude-code", "cursor"]` limits codegraph specified
providers. `namespaces` refers to the graph, and `memory_namespaces` lists common memory
scope, that the project may request explicitly; they are not included in the regular recall.

Ignores `vendor`/`packages` etc. - **here**, and not hard-skinned. See [Code graph](./code-graph).

## Section `mcp.perplexity_web` (rolling keyless-bridge)

Keyless-bridge **perplexity-web** (separate Node-package, search Perplexity via browser profile)
is distributed to projects by the same `deploy`/`sync`, what `maind` and Serena — a single source of truth, not
manual hardcode entry in each `.mcp.json`. **opt-in, disabled-by-default**: without section the server does not
rolls out.

```jsonc
"mcp": {
  "perplexity_web": {
    "enabled": true,                     // global fan-out for all projects
    "pool": "default",                   // browser pooling model (see below)
    "bin": "/abs/path/to/perplexity-web-mcp/start.sh"  // path to executable start.sh
  }
}
```

**Pool** = demon + profile + browser window. Only `default` reuses the current login; any
another pool receives its profile and requires **separate login** in Perplexity. The demon is already driving to
`maxConcurrency` searches in parallel (tabs), therefore isolation is needed only for separate accounts:

| `pool` | Project pool | Logins |
|:--|:--|:--|
| `"default"` (or any literal) | common pool for everyone | one (current) |
| `"per-namespace"` | `ns-<first namespace>` | by group login |
| `"per-project"` | `<id project>` | by project login |

Per-project override: `projects[].perplexity_web` (`true`/`false` — force on/off) and
`projects[].perplexity_web_pool` (literal pool name). `bin` is set in the local
hub-config and rendered as a direct command: MCP-clients run it without shell and
do not disclose `${…}`. Therefore machine-specific path is not in tracked source code -
it remains in the locally generated MCP-configurations.

## Namespaces

`namespaces` the project isolates inter-project connections **both graph and memory**: edge A↔B is under construction,
only if A and B share at least one group; the project's memory facts are visible within it namespace
(`ns:<name>`) and isolated between groups. No field / `[]` → implicit `default`; `["*"]` →
common infrastructure, communicates with all groups. More details - [Namespaces](./namespaces).

## Defaults

`merge_defaults` adds required values (`memory.http_port=4111`,
`graph.adapter=federation`, `agents.heartbeat_interval_ms=30000`,
`observability.service_name=maind` …), so that the code never catches `KeyError`. Deprecated
`graph.adapter` (`memory`/`graphify`/`networkx`) is accepted with a warning and normalized
in `federation`.

::: warning Ports
`memory.http_port`/`stream_port` — only default; `.env` (`AGENTMEMORY_PORT`/
`AGENTMEMORY_STREAM_PORT`) overrides them. See [Memory](./memory).
:::

Next: [Memory →](./memory)
