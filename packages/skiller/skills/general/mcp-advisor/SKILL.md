---
name: mcp-advisor
bucket: general
version: 0.1.0
description: "Pick MCP servers for a project at onboarding/sync: which to connect (context7/playwright/github/fetch/sequential-thinking + maind hub), why, when NOT to, and the cost in context/permissions/Node-deps. Activate when adding/onboarding/syncing a project, editing .mcp.json, or choosing MCP — emits a justified connection plan, not a dump of every server."
risk: read
persona: oss-dev
tags: [mcp, onboarding, tooling, context, claude-code]
requires: []
produces_for: [context-economy]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# MCP Advisor — justified MCP server selection per project

Profiles/onboarding wire MCP **statically** (almost everyone gets only `context7`, frontend also
`playwright`). This skill closes the gap: at project add/sync, **analyze signals and propose** the missing
servers (or explicitly say "not needed") — instead of connecting everything.

## When to activate

- Onboarding/adding a project: `maind onboard`, `skiller integrate`, the MCP setup step.
- Sync/resync; editing `.mcp.json`; the question "which MCP should this project connect".
- Stack/task shift (UI appeared → need a browser; GitHub work started → need gh/github).

## Principle: every server is not free

An MCP server is a **standing tax**, not a "free feature":
- its tool schema **loads into EVERY request** (context tokens), even when unused;
- it needs **permissions** (network/FS/token access) — a risk surface;
- many pull a **Node/uvx dependency** (`npx`/`uvx` install the package on first run).

Rule: connect on **proven need**, not "just in case". Unused 7+ days → disable (see `context-economy` §5).
Where a CLI suffices (`gh`, `git`), prefer the CLI over a server.

## Selection algorithm

1. **Collect project signals:** type/stack (laravel · node-frontend · python-backend · package · vault ·
   standalone), role (backend · frontend · maintainer/reviewer · author), task types (UI/E2E · GitHub work ·
   fresh external docs/API · complex multi-step planning · ecosystem memory/graph).
2. **Walk the map** below: per server — needed / not needed / decide, with a one-line reason.
3. **Emit an "MCP connection plan" memo:** three lists — **Recommend** (with reason), **Skip** (with reason),
   **Decide** (depends on the user). For recommended ones state the connect path: skiller profile (`mcp[]`)
   → delivered by `harness`, or a manual entry in the project's `.mcp.json`.
4. **Confirm with the user** before writing — connecting MCP changes the environment and permissions.

## Server map (menu = harness catalog + maind hub)

| Server | Transport | Connect when | Why | Not needed when | Cost |
|---|---|---|---|---|---|
| **context7** | http | almost any code project with a framework/libraries | live versioned library docs (vs stale training) | vault, pure infra without code | low (http, no local deps) |
| **playwright** | npx `@playwright/mcp --headless` | frontend with UI, E2E tests, page screenshots | browser control, layout checks | backend/CLI/library without UI | Node + browser download |
| **github** | http | active GitHub work: PR/issue/Actions/releases, maintainer/reviewer role | rich platform integration as tools | not on GitHub; routine review (`gh` CLI is enough — cheaper, see `gh-review`) | auth token + permissions |
| **fetch** | uvx `mcp-server-fetch` | need fresh web docs/external API not covered by context7 | load URLs/pages into context | context7 already covers the docs | uvx deps, network |
| **perplexity** | npx `@perplexity-ai/mcp-server` (+`PERPLEXITY_API_KEY`) | verify 'current facts/market/still-current/modern approach' beyond library docs; research | web search with synthesis and citations | context7 (docs) or a known URL (fetch) suffices; no key → keyless `perplexity-web` (daemon v1.3.0: parallel tabs, per-project isolation via `--pool=<project>`) | Node + API key |
| **sequential-thinking** | npx | complex multi-step planning/reasoning | structured "reasoning scratchpad" | routine/short tasks | Node + tokens per call |
| **filesystem** | npx | rare: multi-root / special FS access | extended file access | **usually redundant** — Claude Code has native FS access | Node |
| **memory (generic)** | npx `server-memory` | **in the academici ecosystem — do NOT use** | — | always: memory goes through the `maind` hub | conflicts with the memory canon |
| **maind (hub)** | per-project, from onboarding `.mcp.json` | onboarded ecosystem projects | memory (scope isolation) + link graph + projects/links | one-off external project without onboarding | already present after `maind onboard` |

**Memory caveat.** In the academici ecosystem memory and graph go **through the `maind` server**
(`MODE=maind`, tools `maind_memory_*` / `maind_graph_*`), **not** the raw `memory` MCP nor direct
agentmemory. Do not propose generic `memory` — it duplicates/conflicts with the hub.

**GitHub: `gh` CLI vs `github` MCP.** For routine review/handoff, `gh` CLI is cheaper (minimal slice:
`gh pr diff`, `gh pr view --comments`) — see `oss-dev/gh-review`. The full `github` MCP — when you need the
platform's tool integration in the agent (bulk operations, Actions, secrets).

## Profile defaults (starting point, not ceiling)

Skiller profiles currently give: `context7` — to all code types; `+playwright` — to `node-frontend`. The
advisor **adds** per role/tasks: `github` — for oss/maintainer and packages; `fetch` — where fresh external
docs/API are needed; `sequential-thinking` — for complex tasks. Keep the base set minimal.

## Quality checklist

- [ ] Signals collected: stack, role, task types — the recommendation is justified by them, not "all by default".
- [ ] Each recommended server has a reason; each rejected one has a rejection reason.
- [ ] Cost considered: schema in every request + permissions + Node/uvx dep; nothing connected "just in case".
- [ ] Memory/graph go through `maind`; generic `memory` MCP not proposed.
- [ ] For routine GitHub review, `gh` CLI proposed over the heavy `github` MCP when not needed.
- [ ] User confirmation before writing to `.mcp.json`.

## Related skills

- `context-economy` (general) — the reverse side: audit/trim what is already connected (unused MCP →
  disable; schema loads every request). This skill is about **selection**, that one about **reduction**.
- `oss-dev/gh-review` — `gh`-driven review: when GitHub ops are cheaper via CLI than via `github` MCP.
- `ai/ai-agents` — when the task is not "connect a ready MCP" but **designing your own** MCP server.
- `security/security` — review MCP tool configs for injection/exfiltration before connecting.
- `architect/figma-mcp-core` — a domain special case (Figma Dev Mode MCP), outside general selection.
- `verify-claims` (general) — complementary: this skill is about *what to connect* to a project, that one about *when and how to fetch/verify a fact* via the connected engines (context7/perplexity/web).

<!-- ru-source-sha256: 648d8c8e5996400d33fe904340851348e4ac1822c394292ce8437048a613bf01 -->
