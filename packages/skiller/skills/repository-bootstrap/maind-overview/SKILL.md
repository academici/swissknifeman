---
name: maind-overview
bucket: repository-bootstrap
version: 0.1.0
description: "Brief overview of the mAInd hub - two linking mechanisms (code graph/Serena, agent-memory), the namespace model, and key commands. Use when working in maind or any ecosystem project to understand shared memory, the connection graph, and namespace isolation."
risk: read
persona: oss-dev
tags: [maind, ecosystem, memory, graph, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# mAInd — how it works (brief)

**mAInd** is the academici ecosystem's hub/bus. All information flow between projects (`brain`,
`swissknifeman`, `flexcrm`, `azguard`, …) passes through it. The hub links projects via **two
independent mechanisms** — different jobs, same goal of "linking projects":

| Mechanism | Links | How it lives |
|:--|:--|:--|
| **agent-memory** | memory/context (facts, change stream) | Node daemon on the hub; an MCP client is rolled out to projects |
| **code graph (Serena)** | code **inside** a project (symbols/references/implementations) | per-project MCP server `serena` (via `uvx`) |

Plus mAInd's own **graph** — topology **between** projects (who depends on whom, shared packages,
skills): federation (per-project graph + index), built by `derive` from sources of truth
(composer/Brain/`.maind.graph.json`/skills-lock), not a hand-maintained copy.

## Namespaces — isolation (shared rule across all three)

A project declares groups via `projects[].namespaces` in `config.json`. **Shared within a group,
isolated across groups.** `["*"]` — shared infrastructure (visible to everyone).

- **Graph**: a cross-project edge A↔B is built only if A and B share a namespace.
- **Memory**: buckets `project:<id>` (private) · `ns:<name>` (group) · `global` (whole ecosystem,
  wildcard). `recall`/MCP read `project:<id>` + `ns:<own groups>` + `global`.

**Session-start digest (SessionStart hook) — `project:<id>` only by default**
(`shared_max=0`, context-economy: another namespace's/global context does not flow into every
session unasked). Group-wide context is raised EXPLICITLY when the task is genuinely
cross-project — guideline and commands: [ecosystem-mcp] → "Cross-project task", doctrine —
[docs/guide/memory.md].

[ecosystem-mcp]: ../ecosystem-mcp/SKILL.md
[docs/guide/memory.md]: ../../../../../packages/maind/docs/guide/memory.md

## Key commands

```bash
# onboarding / provisioning
maind onboard <project>            # connect a project: skills + memory + graph + MCP
maind deploy <project>             # hub MCP servers into .mcp.json (agentmemory + maind [+ code graph])
maind sync --all                   # roll out managed artifacts (mcp/graph/memory/health-*)
# health / proof of life
maind health --cwd [--fix]         # project's link to the hub (non-blocking; --fix auto-repairs)
maind verify [--cwd]               # PROOF OF LIFE across 3 planes: is memory actually WRITTEN,
                                   #   graph coverage, is Serena up — distinguishes "up" from "alive"
maind doctor                       # node diagnostics (python/Node/agentmemory/config/daemon)
# graph / memory
maind graph --project <id>         # one project's graph;  --cross [--namespace NS];  derive — rebuild
maind memory <recall|remember|forget|status>   # direct memory access by scope
# registries / orchestration
maind status                       # node summary (memory/graph/agents/projects)
maind projects | agents | namespaces           # node registries (read-only listings)
maind workspace <project>          # Claude's trust for a project (.claude/settings.local.json)
maind run <…>                      # orchestration (subprocess to skiller etc.)
maind fleet <manifest|duplicates|similar|log>  # cross-project layer (jscpd/embeddings/feature log)
maind migrate <…>                  # state migrations
maind mcp [--scope project:<id>]   # run as an MCP server (stdio JSON-RPC, 11 tools)
```

`health` vs `verify`: health answers "is the link up/configured", verify — "is data actually
FLOWING through these channels" (memory seed vs last-write, graph coverage, live Serena).
Diagnosing "looks connected but doesn't work" — that's `verify`.

## Hub MCP tools (11; per-project server `maind` from `.mcp.json`)

`maind mcp --scope project:<id>` (how `deploy` rolls it out) is **isolated to its own project**:
other projects' memory/graph are unreachable (scope reduces to `recall_scopes`: private +
`ns:groups` + `global`; graph tools — only projects sharing a namespace). Hub mode
(`--scope global`) or `MAIND_MCP_ALLOW_CROSS_SCOPE=1` lift the isolation (admin).

| Group | Tools |
|:--|:--|
| memory (3) | `maind_memory_store` · `maind_memory_recall` · `maind_memory_forget` (by `scope`) |
| graph (4) | `maind_graph_query` · `maind_graph_neighbors` · `maind_graph_path` · `maind_graph_project` |
| mixed/registries (4) | `maind_memory_links` (links + ecosystem-link memory) · `maind_agents_list` · `maind_projects_list` · `maind_projects_status` |

## Where to look in the code

- `lib/maind/federation.py` — graph layout + `graph_reader` (unified read facade).
- `lib/maind/derive.py` — building the graph from sources of truth.
- `lib/maind/namespaces.py` — connection isolation + memory scope buckets.
- `lib/maind/seed.py` — per-namespace seed memory.
- `lib/maind/mcp.py` — MCP server (11 tools).
- Docs: `docs/ecosystem.md` (philosophy) → `docs/architecture.md` → `docs/guide/*`.
- Conventions — root `CLAUDE.md` (stdlib-only, explicit `Env`, atomic JSON, Russian messages).

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38):
canonical source is this `SKILL.md`; thin projections —
`.claude/skills/maind-overview/SKILL.md` and `.agents/skills/maind-overview/SKILL.md` (generated
by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is private/source-only:
never published as an ordinary unit/core/marketplace entry, never vendored/connected into a
consumer project.
