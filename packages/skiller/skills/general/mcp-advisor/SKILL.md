---
name: mcp-advisor
bucket: general
version: 0.2.0
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
| **graph-retrieval MCP** (`code-review-graph` and its class) | pipx/uvx, separate process | **do not connect without your own co-change measurement** — see block below | multi-hop "what breaks if I change this" | the code-graph canon is **Serena** (LSP); evaluated and rejected 2026-07 on our numbers | process + permissions + maintaining an external project |

**Memory caveat.** In the academici ecosystem memory and graph go **through the `maind` server**
(`MODE=maind`, tools `maind_memory_*` / `maind_graph_*`), **not** the raw `memory` MCP nor direct
agentmemory. Do not propose generic `memory` — it duplicates/conflicts with the hub.

**GitHub: `gh` CLI vs `github` MCP.** For routine review/handoff, `gh` CLI is cheaper (minimal slice:
`gh pr diff`, `gh pr view --comments`) — see `oss-dev/gh-review`. The full `github` MCP — when you need the
platform's tool integration in the agent (bulk operations, Actions, secrets).

## Graph-retrieval MCP: measured verdict (not connected — on our numbers)

The class "code graph as a retrieval layer under review" was **evaluated and rejected 2026-07** on the
candidate `tirth8205/code-review-graph` (26k★, MIT) — rejected by a NUMBER on our codebase, not by impression:

- **Ops are excellent** — 1.66 s build (405 files), 0.24 s increment. Speed was not the problem.
- **`P_impact` = 0.039** against a `≥ 0.40` threshold declared BEFORE measuring: blast-radius precision vs
  co-change ground truth, 24 folds (each changed file of a commit as seed in turn) over three real commits
  of a Laravel project. 1 fold out of 24 cleared the threshold.
- **It fails on noise, not blindness:** recall 0.40–0.43 — the graph does see the links, but returns 110
  files for one seed, with the true ones at positions 77 and 102 ⇒ top-K truncation makes it WORSE.
- Public numbers are self-measured: the claimed F1 0.714 is computed against ground truth derived from the
  same graph ("circular by construction" — the author's own wording); co-change numbers were never published.

**Resulting rule:** never connect a graph-retrieval MCP on README and stars — only after YOUR OWN
co-change measurement on YOUR repo (threshold declared BEFORE measuring, ground truth from real commits,
not from the graph). A verdict on one candidate is not a verdict on the class.

**Reopen the question if** (any): (1) external, non-self-measured co-change precision ≥ 0.40 is published;
OR (2) a repo > 3000 files appears where Serena/grep structurally cannot answer "what breaks if I change
this"; OR (3) an independent benchmark of the class appears. Until then the code-graph canon is **Serena**
(LSP; the candidate's own author states LSP is more precise for symbol-precise access).

## Profile defaults (starting point, not ceiling)

Skiller profiles currently give: `context7` — to all code types; `+playwright` — to `node-frontend`. The
advisor **adds** per role/tasks: `github` — for oss/maintainer and packages; `fetch` — where fresh external
docs/API are needed; `sequential-thinking` — for complex tasks. Keep the base set minimal.

## Weeding resident MCP (auditing what's already connected)

Selection (above) is about adding. Symmetric ritual — about what's ALREADY sitting in the project's
`.mcp.json`:

1. **Audit:** `skiller budget --first-turn --target <path>` → the MCP line of the report (server list +
   tokens + tool-search mode + estimate class, `budget.py::_measure_mcp`, P2.3). Check each resident
   server against the map above: connected by a project signal (stack/role/tasks), or "connected earlier,
   signal no longer holds"?
2. **"1-2 servers per task" rule.** A typical session uses 1-2 MCP servers out of the connected set (the
   rest are a silent resident "tax" on every request). More than 4-5 servers on a small project without
   an explicit multi-domain stack is a signal for owner review, not automatic disconnection.
3. **Tool-search mode is now mode-aware in the measurer itself (P2.3), not just in prose.**
   `_measure_mcp` no longer always counts the EAGER ceiling: by default (tool search on,
   `ENABLE_TOOL_SEARCH` unset) it estimates the `deferred` model (tool names + server instructions — a
   lower bound) and prints the mode + source + estimate class (`mcp.mode`/`mcp.mode_source`/
   `mcp.estimate_class` in JSON). The EAGER model (full schemas, the old behavior) remains the `off`
   branch (`ENABLE_TOOL_SEARCH=false`) or `auto` (upper bound — the "within 10% of the window" assumption
   is not checked against a live `/context`). Don't claim weeding savings on the eager number outside
   those two branches — it's honest only there. Weeding still has value (a server is still a summary line
   + permissions surface + Node/uvx dep), but its ROI is lower than the eager ceiling alone implied.
4. **A heavy resident is not justified by its author's claim.** A server selling "×N context savings"
   (code graph, semantic search, repo packers) is checked by YOUR measurement on YOUR repo — see the
   "Graph-retrieval MCP" block above: for the candidate we measured, the ×82 claim stood against a
   "read the whole repository" baseline the author himself calls "an upper bound no real agent pays".
5. **Disconnect candidate** — a server for which none of the map's "Connect when" signals has held for
   7+ days straight (see `context-economy` §5) — propose disconnection to the project owner with a
   reason, don't disconnect silently.

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

<!-- ru-source-sha256: 9cc73ee4c23181feddec38e205b1f90eaa17d27ad58497a0faba92d00edeacdf -->
