---
name: ecosystem-mcp
bucket: repository-bootstrap
version: 0.1.0
description: "What MCP tools are available here (agent-memory = shared memory/context, serena = code graph), when to call them, which ecosystem projects this one links to, and how to fix a broken link. Use in any ecosystem project to raise past-decision context, navigate code, or diagnose missing memory/graph."
risk: read
persona: oss-dev
tags: [ecosystem, mcp, maind, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# academici ecosystem — this project's MCP tools

This project (`swissknifeman`) is a node of the **academici** ecosystem, connected to the
**mAInd** hub. Two independent linking mechanisms flow through the hub; both are rolled out here
as MCP servers (see `.mcp.json`). For swissknifeman as a self-host repo, this file's canonical
source is `packages/skiller/skills/repository-bootstrap/ecosystem-mcp/SKILL.md`
(edit there, regenerate `skiller registry`, P1.2/D31); the onboarding template
`packages/maind/templates/skills/ecosystem-mcp/SKILL.md` is the same content for OTHER ecosystem
projects (`maind onboard`/`maind sync`) — do not conflate the two sources.

## Tools and when to call them

| MCP server | What it is | When to call |
|:--|:--|:--|
| **agentmemory** | Shared ecosystem memory/context (facts, change stream). mAInd daemon, this project's scope — `project:swissknifeman` | At the **start of a task** — raise context of past project/ecosystem decisions (recall). On **committing** a significant decision/fact — write it (store) so it enters shared history |
| **serena** (code graph) | Graph of code **inside** the project: symbols, references, implementations, file overview (Serena engine) | For **code navigation** — `find_symbol`, `find_referencing_symbols`, `get_symbols_overview` instead of reading whole files (saves tokens). Available if `.mcp.json` has a code server (usually `serena`); if not, navigate with ordinary search. Don't confuse with the cross-project maind graph |
| **maind** | The hub itself (topology **between** projects, connection status) | When you need this project's links to other ecosystem nodes or a status summary |

Memory is **shared within a namespace** and isolated across namespaces — anything written here is
visible to linked projects in the same group. Don't duplicate into memory what's already in
code/git.

**Session-start digest — this project only.** `maind memory digest` (SessionStart hook)
defaults to showing **only this project's private memory** (`shared_max=0` — context-economy:
another namespace's/global context does not flow into every session unasked). Group/ecosystem
context is NOT mixed in — raise it explicitly (below) when the task is genuinely cross-project.

## Cross-project task (2+ projects)

A task spans several ecosystem projects (e.g. "analyze X and Y and improve what's shared between
them") — raise cross-project context explicitly, three steps:

1. **Links** — which projects are even connected: `maind graph --project swissknifeman` (CLI) or
   `maind_graph_path`/`maind_graph_neighbors` (MCP) — path/neighbors between graph nodes.
2. **Group context** — raise the namespace's shared memory explicitly (not in the default
   digest): `maind memory recall --scope ns:<name>` (CLI) or `maind_memory_recall` with that
   scope (MCP).
3. **Output is written to the shared scope**, not the project's private one — otherwise the next
   project in the group won't see it: `maind memory remember --scope ns:<name> "<fact>"` (CLI,
   `--scope` is a direct bucket address — not the same as `--project --share`, which serves a
   different purpose: private + group at once) or `maind_memory_store` with `scope: "ns:<name>"`
   (MCP).

## Rule: graph/symbols first, then broad search

Before a broad `grep`/reading many files — ask for structure first, it's cheaper in tokens:

- **code navigation** → serena: `get_symbols_overview` (file overview), `find_symbol` (body by
  name), `find_referencing_symbols` (who references it) — instead of reading whole files;
- **cross-project links** → `maind graph query`/`neighbors` — node neighbors instead of grepping
  manifests.

**Caveat:** the maind graph is rebuilt MANUALLY (no watcher) — it can go stale. If the result
looks incomplete/stale → `maind sync --only graph`, then retry; or fall back to ordinary search.
The serena code graph (LSP) is live — this caveat doesn't apply to it.

## Project links

- **memory scope:** `project:swissknifeman`; ecosystem-wide facts — scope `global`.
- **namespaces:** `axioma` (shared within the group, isolated across groups).
- **linked to:** —.
- see current links: `maind graph --project swissknifeman`.

If something breaks in a linked project, remember the link exists: changes here may affect
namespace neighbors, and the user should be warned.

## If the link is broken

The tools above only work with an active hub connection. If memory/graph MCP calls don't respond
or memory is empty:

1. Check: `maind health --cwd` (this project's link) or `maind verify` (is memory/graph actually
   being written across the ecosystem, or is it up "in name only"). Memory by eye — viewer at
   `http://127.0.0.1:3113`.
2. On `partial` / `standalone` status — fix it: `maind health --cwd --fix` (brings up the memory
   daemon and appends hub MCP servers).
3. **Tell the user**: until status is `connected`, this session's changes will **not** enter
   shared memory and graph — an unrecoverable gap will appear in ecosystem history.

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
canonical source is this `SKILL.md`; thin projections —
`.claude/skills/ecosystem-mcp/SKILL.md` and `.agents/skills/ecosystem-mcp/SKILL.md` (generated by
`skiller registry`, never hand-edited). Bucket `repository-bootstrap` is private/source-only:
never published as an ordinary unit/core/marketplace entry, never vendored/connected into a
consumer project.
