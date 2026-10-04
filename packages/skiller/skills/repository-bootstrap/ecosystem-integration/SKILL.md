---
name: ecosystem-integration
bucket: repository-bootstrap
version: 0.1.0
description: "How to connect (onboard) a new project to the academici ecosystem via the mAInd hub - shared memory + graph + MCP tools + skills. Use to onboard a project, add it to mAInd, roll out memory/graph, or fix/update an already-connected project."
risk: draft
persona: oss-dev
tags: [ecosystem, maind, onboarding, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Connecting a project to the academici ecosystem

Hub **mAInd** links projects via two mechanisms (shared memory + topology graph) and rolls out
MCP servers, an orientation skill, and a healthcheck to every project. All done with `maind`
commands. Run them from the maind hub directory (or the absolute path `bin/maind`).

## Decision tree (before onboarding)

Full scenario tree (10 layers, conditional branches) — canonical doc
["Decision tree: project setup"](../../../../../packages/maind/docs/guide/onboarding-decision-tree.md).
Briefly, before running: **type** (detect → profile; unrecognized → don't do "everything", pick
explicitly) → **memory** (maind/native/off) → **namespaces** (shared + personal) → **skills
channel** (connect/vendor — ASK) → **buckets** (optimal for the stack, not maximal) →
**environment/graph**. Main rule: pick the optimal set; unclear → ask the user.

## Connect a new project

```bash
maind onboard <path|id> [--with-code] [--with-brain] [--yes]
```

Chain (every step is standalone-safe — a missing neighbor doesn't fail onboarding):

1. **register** — add the project to `config.json` (namespace defaults to empty → set it
   manually, see below).
2. **skills** — `skiller integrate` (skills + hooks), unless `--skip-skills`. ⚠️ swissknifeman
   installs skills over **two channels** — `connect` (bucket plugins, not in-repo) and `vendor`
   (physical transfer of specific skills into the repo via `.swissknifeman/config.json` +
   `skiller sync`). **Ask the user which channel** before installing (the `integrate` wizard
   also asks). Operational details and Boost-as-MCP — [project-tooling-runbook].
3. **deploy** — scoped hub MCP into the project's `.mcp.json`: `maind` [+ code
   graph]. ⚠️ `.mcp.json` carries **absolute local paths** (`bin/maind`, the Serena project path)
   → must not be committed as-is. Hygiene (indirection via `.env`, or gitignore + a synced
   `.example`) — [project-tooling-runbook] §"Machine-specific config hygiene".
4. **graph** — `derive` the topology graph from composer/docs + rebuild the index.
5. **memory** — enable scoped access without automatic seed writes; topology stays in config/graph.
6. **ecosystem-skill** — roll out the [ecosystem-mcp] skill into the project (orientation for
   its agent).

[project-tooling-runbook]: ../project-tooling-runbook/SKILL.md
[ecosystem-mcp]: ../ecosystem-mcp/SKILL.md

## Namespace (important)

Connections and shared memory are isolated by namespace. A freshly created record lands in
`default` and **will not link** to the group. Set the group in the project's `config.json`:

```json
{ "id": "myproject", "namespaces": ["axioma"], ... }
```

`["*"]` — shared infrastructure (visible to every group). After editing, rebuild the graph:
`maind sync --namespace axioma --only graph`.

## Update / fix an already-connected project

```bash
maind sync --project <id> --mode auto      # roll out all artifacts (mcp/graph/memory/health*/skill)
maind sync --project <id> --only mcp       # MCP servers only
maind sync --all                            # all enabled projects
```

## Verify the result

```bash
maind health --project <id>     # connected | partial | standalone (+ hints)
maind health --cwd --fix        # from the project dir: bring up memory + append MCP
maind graph --project <id>      # project graph and neighbors
```

`partial` usually means "memory daemon not running" → `maind start --only memory` (or register
the service: `maind service install`).

The systemd daemon starts on login; to come up **on OS boot** (SSH server) — enable linger once:
`loginctl enable-linger $USER` (check: `loginctl show-user $USER -p Linger` → `yes`). See
[systemd guide](../../../../../packages/maind/docs/guide/systemd.md).

## Drift gate — mandatory before calling onboarding/integration done

Managed skills (skiller vendor channel + maind's `ecosystem-mcp`/`ecosystem-setup`) improve over
time in the registry/templates, but already-onboarded projects don't get that for free — rollout
is one-shot. Without a final check, partial `--only` syncs quietly accumulate drift (incident:
agelto's `ecosystem-mcp` didn't know about Serena for 2 weeks — the agent read files directly
instead of using the graph).

```bash
skiller doctor --vendor-drift     # which vendor projects fell behind the skiller registry (add/update/remove)
maind doctor --skill-drift        # which projects fell behind the ecosystem-mcp/ecosystem-setup templates
```

Both are read-only and, by default (no flags), print one summary line in ordinary `doctor`. A
project from the report → `skiller sync` (from its directory) and/or `maind sync --project <id>
--only ecosystem-skill,setup-skill`. Run this after any point (`--only`) onboarding/integration,
not only after a full `maind onboard`.

## Code graph (in-project code graph) — universal

A separate per-project CODE graph MCP (symbols/references/implementations). Default engine is
**Serena** (language-agnostic, via `uvx`), works for any stack. Enabled by intent:

```json
{ "id": "myproject", "code": true, ... }
```

`maind sync --project myproject --only mcp` appends the `serena` server to `.mcp.json` (needs
`uvx` on PATH; missing → correct `skipped-not-installed` skip, everything else still works). The
engine can be overridden per project (`code_command` / `code_args` with `{root}` /
`code_server_name`) — e.g. a stack-specific server. More —
[code graph](../../../../../packages/maind/docs/guide/code-graph.md).

## Memo

- Memory is **project-only by default** in MCP, CLI and digest. Shared scope needs an explicit
  cross-project request and allowed `memory_namespaces`, separate from graph `namespaces`.
  **The session-start digest does not share context by default**
  (`shared_max=0`, D10) — only `project:<id>`; group-wide context is raised EXPLICITLY via
  `recall --scope ns:<name>` when the task is genuinely cross-project (guideline — skill
  [ecosystem-mcp] → "Cross-project task", doctrine —
  [docs/guide/memory.md](../../../../../packages/maind/docs/guide/memory.md)).
- MCP is passive: the project's own agent calls `recall`/`store`/graph tools — no automatic
  "interception".
- Store only temporary useful context (default 48 hours, maximum 72 hours, 800 characters).
  Keep plan decisions, progress and history in repository files. Empty memory is normal.
- Source of truth for artifacts is the templates in maind (`templates/`), don't edit project
  copies.

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38):
canonical source is this `SKILL.md`; thin projections —
`.claude/skills/ecosystem-integration/SKILL.md` and `.agents/skills/ecosystem-integration/SKILL.md`
(generated by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is
private/source-only: never published as an ordinary unit/core/marketplace entry, never
vendored/connected into a consumer project.
