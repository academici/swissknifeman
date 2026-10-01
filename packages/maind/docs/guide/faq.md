# FAQ — frequently asked questions

Short, honest answers to questions that actually arise. Details - follow the links.

## Memory and MCP

**All code goes through common MCP-servers? How often does it sync?**
No. MCP **passive (pull)**: they do not monitor the code and do not synchronize anything themselves - tool
is called by the agent when it decides. The only thing that gets into memory is that the agent **explicit** wrote down (`store`).
«Synchronization» (`maind sync`) — this is rolling out configs/artifacts **by command**, not continuous
process. More details: [How it works](./how-it-works), [Memory](./memory).

**Does the project need additional. instructions so that the agent knows about the tools?**
Yes, and they roll out automatically: skill `ecosystem-mcp` in `.claude/skills/` (what the
tools and when to call) + `initial_prompt` in `.serena/project.yml` (targets symbol-navigation).
See [sync](./sync).

**Can I make my own memory for each project?**
Technically yes, but it would kill the point (projects will not see each other) and it will be more difficult. Therefore memory
**general**, and visibility is reduced scope: `project:<id>` (private) · `ns:<group>` · `global`.
See [Namespaces](./namespaces).

**Is the memory daemon always up?**
Yes, if you put systemd-service: `maind service install` + `loginctl enable-linger $USER`
(start at OS boot). See [systemd](./systemd).

**Memory viewer (`http://127.0.0.1:3113`) on the tab `#graph` writes «Graph query failed» — is it broken?**
No, it's **normal**. Tab `#graph` — this **knowledge-graph himself agentmemory**: entities
(people/projects/concepts), which **LLM retrieves from memory text**. This **fourth** meaning of the word
«graph» — NOT cross-project maind-graph and NOT code-graph Serena (see [«four graphs»](./how-it-works#visualization-where-to-see-with-the-eyes)).
The feature is disabled by default. Under the hood: the viewer proxies the request to the daemon, it responds **503**:

```json
// POST :4111/agentmemory/graph/query → 503
{ "enableHow": "Set GRAPH_EXTRACTION_ENABLED=true and restart. Requires an LLM provider key." }
```

viewer wraps 503 in «502 upstream error» → on the screen «Graph query failed».

- **To see inter-project connections with a picture** — this is not here: `maind graph export --cross` (Mermaid).
- **Entries/memory search** — other tabs `:3113` work without this feature.
- **Enable `#graph`** (optional) — needed LLM-provider key + `GRAPH_EXTRACTION_ENABLED=true`
  + daemon restart. Meaning appears only when the memory is really full (on seed-facts column is empty).

## Code graph (Serena)

**Is the code graph in the hub? How does the agent see him?**
No. Code graph - **separate MCP-server in the project itself** (engine [Serena](./code-graph), via
`uvx`). It is registered in `.mcp.json`; client picks it up **at session start**, and its tools
appear on the agent. The hub just recorded this line - in runtime maind is not involved.

**Is it necessary to install the code graph natively in the project?**
Serena is the native installation: when activated, it creates a folder `.serena/` (config + symbol cache).
The binary is not vendored - it is launched via `uvx` (is cached). Name `graphify` historical; engine -
Serena.

**How will the agent contact the graph when I give the task («see authorization»)?**
He will call symbol-tools Serena (`find_symbol`, `find_referencing_symbols`,
`get_symbols_overview`) — will find definitions and calls instead of reading entire files. This **pull**:
availability of tools and `initial_prompt` — are automatic, but the decision to call is made by the model.

**I added a server - why doesn't the agent see it?**
`.mcp.json` is read when **session start**. Restart the session in the project (first launch Serena
longer - raises LSP).

## Cross-project development (CRM + core)

**Opening IDE in CRM, packages are linked - will there be a single graph with the core?**
Yes - **workspace-mode** (is included automatically if the project has a directory `packages/`).
Then `.serena/project.yml` indexes `packages/*` as part of the project: one root → PHP-LSP
resolves links `app ↔ core`, agent sees that the file is going to core, and takes it from the graph. Edits in
`packages/<package>` go to **real package repository** (via symlink). Checked: from session
flexcrm symbols visible corex. See [Code graph → workspace](./code-graph#workspace-single-graph-with-local-packages mode).

**Takes/recursion due to symlinks vendor?**
Workspace-config cuts `vendor` and nested `**/vendor` (there is recursion testbench and duplicate symlinks),
a `packages/*` leaves. For application projects without local packages, the default config is ignored
and `packages`.

**Independent projects can be combined into one graph (not under the same tree)?**
No. Serena-multi-root with cross-links (`additional_workspace_folders`) for now only for TypeScript.
For PHP: connection «who depends on whom» gives [maind-topology graph](./federation), code repetitions -
[`maind fleet duplicates`](./fleet). See [restrictions](./design-notes).

## Cross-project optimization

**I have N similar projects with common packages - how to find common ones and bring them into the kernel?**
`maind fleet`: `manifest` (groups by common packages - where to look) → `duplicates` (jscpd — what
repeats) → `features` (memory - what was changed) → Serena (spot edit) → removal to the kernel. Ready
script - skill `cross-project-optimizer`. See [Fleet](./fleet).

**Is the scheme overcomplicated?**
Memory (general) and code graph (per-project) — both are justified by the purpose and are already like that. The difficulty is that
three different things are called «graph», and in the historical name `graphify`. See
[Solutions and limitations](./design-notes).
