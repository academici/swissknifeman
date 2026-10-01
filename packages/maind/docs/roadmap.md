# Roadmap

Honest state: what works, what's left to do «perfect» cross-project development, and that
depends on external things. Not promises - direction.

## What already works

- **Shared memory** (agent-memory) + namespace-insulation (`project`/`ns`/`global`), demon under
  **systemd** (autorun + restart + linger).
- **Topology graph** between projects (federation, `derive` from composer/docks/skills).
- **Code graph** — per-project MCP **Serena** (language-agnostic, via `uvx`), config-driven
  (`code:true`), default `.serena/project.yml` with correct ignores.
- **Workspace-mode** (auto upon availability `packages/`): single graph «project + local packages»,
  edits go to real package repositories. Tested on flexcrm+corex.
- **Cross-project layer** `maind fleet`: manifest (groups by common packages), duplicates (jscpd),
  feature-log; skill `cross-project-optimizer`.
- **Provisioning** `maind sync` + `onboard` + healthcheck + skills (`ecosystem-mcp`).
- **Unified terminology of three planes** (agent-memory / maind-graph / code graph): name `graphify`
  cut out from prose and documents, all that remains is how legacy-alias in the config/flags (back-compat).

## The Ideal of Cross-Project Development - What's Left

Target script: opening IDE in CRM, kernel and packages linked and **are visible as a connected graph**,
the agent immediately knows that the file goes to the kernel, and takes it from the graph.

**Where are we now:** workspace-mode gives this for PHP like **one merged graph** (app + packages
under one root, LSP resolves links into the kernel). This closes the essence of the request.

**Honest point:** «each package has its own separate graph, but connected to the others» (N
independent graphs with cross-references) — for PHP **not yet available**: Serena-feature
`additional_workspace_folders` supports cross-references only for TypeScript. We get around this
by merging into one root (works), but it's not N-federate-graphs. Depends on upstream
(Serena/LSP) or custom multi-root binding - **external dependency, not closed in maind**.

## What maind can close itself (close)

- **Auto feature-log**: hook, soft fixing «what has changed» to shared memory - to
  the optimizer saw the history without manual `maind fleet log`.
- **jscpd by monorepo**: smart default ignore (now `--ignore` for the monorepo package is set
  manually; do automatically by project type).
- **Pre-index Serena when enabled** (`serena project index`) — so that the first call in the session does not
  was waiting for indexing.
- **Semantic similarity** for fleet (function embeddings/classes) — over literal duplicates
  jscpd: find «similar in meaning, not verbatim».

## External / operation

- **Brain-instructions** in the repository brain (rolling during installation) — separate task outside maind.
- **Broken project configs** (e.g. invalid `.cursor/mcp.json` y agelto) maind not knowingly
  touches - they fix it on the project side, then `maind sync`.
- Onboarding other applications to the registry (`maind onboard`) — as needed.

## Memory / graph (dotted)

- Semantic recall with ranking/summarization (via `ANTHROPIC_API_KEY`).
- Auto-linking of new facts into a graph (`memory`-node + `belongs_to`).
- `graph path --from --to` in CLI (now - only MCP-tool); export subgraph to HTML/SVG.

## Multi-hub

- `node.role: secondary | mirror` — several hubs with graph sync/memory; export back to brain.
