# Code graph (code-MCP in the project)

Graph **code inside the project** (symbols, files, links, implementations) — separate, **universal**
layer: per-project MCP-server. The default is **[Serena](https://github.com/oraios/serena)** —
language-agnostic (via LSP, works for PHP/TS/Python/Go/Rust/… the same), is launched via
`uvx`, without installation in each project. This gives the agent precise code navigation (find definition,
all calls, interface implementations, file symbol overview) — and saves tokens against reading files
in its entirety.

::: tip Field name and engine
Enabled by the project field `code: true` (old `graphify: true` — **legacy-alias**, works).
Finished tool «graphify» does not exist; **default engine - Serena**. All policies
(command, ignores, prompts) — in section `code_graph` config, not in code (see [Config](./config)).
:::

Three layers of the ecosystem - different tasks:

| Mechanism | What connects | How it's delivered |
|:--|:--|:--|
| **agent-memory** | memory/context (facts, solutions) | daemon on the hub + MCP-client in project |
| **maind-graph** | topology **between** projects (dependencies) | federation on the hub ([Federation](./federation)) |
| **code-MCP (Serena)** | **code inside** project (characters/links/implementations) | MCP-server in the project (uvx Serena) |

## Enable (config-driven)

Project field `code: true` in the registry — and `maind sync`/`onboard` roll out the code-MCP:

```json
{ "id": "flexcrm", "code": true }
```

```bash
maind sync --project flexcrm --only mcp     # will add the code-MCP in .mcp.json (if the command is in PATH)
maind onboard flexcrm --with-code       # onboarding directly with a code graph (flag will be saved in the config)
```

Write to `.mcp.json` project (default — Serena):

```json
{ "mcpServers": {
    "serena": { "command": "uvx", "args": [
      "--from", "git+https://github.com/oraios/serena@949a27ef1e5fda1a6e7b561e777bcece345c6ffd", "serena", "start-mcp-server",
      "--context", "ide-assistant", "--project", "/path/to/flexcrm",
      "--enable-web-dashboard", "false" ] } } }
```

Required `uvx` (from [uv](https://docs.astral.sh/uv/)) in PATH. No command → correct omission
(`skipped-not-installed`), other servers are written, sync does not crash.

## Default `.serena/project.yml` (provision)

When `code:true` (engine Serena) provider **`code-graph`** puts the starting one into the project
`.serena/project.yml`: language by project type + standard ignores + `initial_prompt` (native
targets the agent at symbol-tools). It is written **only if the file does not exist yet** — after the first
activation file owns Serena, maind her edits are not clobbered.

```bash
maind sync --project flexcrm --only mcp,code-graph
```

### Why are they ignored? `vendor` and `packages`

Default ignores (`code_graph.ignores` in the config - you edit there, not in the code): `vendor`,
`node_modules`, `packages`, `storage`, `bootstrap/cache`, `public/build`, `dist`, `.git`. This
**consciously**, especially in a monorepo with symlinks:

- third party dependencies (`vendor/laravel/…`) — huge and read-only, there is no need to index;
- **first-party packages linked within the project** (Composer path-repos: `vendor/<vendor>/<pkg>`
  and `packages/<pkg>` often point to the SAME source) — indexing them here would mean
  **duplicate characters** (one packet 2–3 times) and **recursive symlinks** (for example testbench loops
  `vendor → laravel/vendor → …`), on which the scan hangs.

**Default model:** each first-party package - **your project with your own code graph**
(`code:true` on it); dependent project graph only its code. Communication «who is using whom» —
in [maind-topology graph](./federation). There is no need to change the link - it is for Composer/runtime.

## Workspace-mode: single graph with local packages

If you **actively developing core packages along with the project** (corex/azguard — hundreds of files,
significant part of the code), needed **single graph**: project + its local packages are like one picture, with
edits directly to the package sources.

Turns on **automatically**, if the project has a directory `packages/` (monorepo with its
source OR consumer with sub-linked packages). Can be set explicitly/disable:

```json
{ "id": "flexcrm", "code": true, "code_workspace": true }   // true | false (override auto)
```

Then maind generates `.serena/project.yml`, which **does not ignore `packages`** (source
sub-linked packages physically under the project tree → one root = single graph; PHP-LSP
resolves links `app ↔ packages`), but it cuts `vendor` and **nested** `**/vendor` (duplicate symlinks +
recursion testbench). Edits in `packages/<package>/…` go to **real package repository** via
symlink. `initial_prompt` targets the agent: having found an improvement in the package, suggest and, according
confirmation, edit there.

Checked: from session flexcrm `get_symbols_overview` returns class symbols from corex
(`CoreX\Auth\CoreAuthServiceProvider`) — package is visible as part of the graph.

::: tip When what mode
**Default** (`code_workspace` not specified) — project graphs only its code; packets are graphed as
their projects. **Workspace** — for «monorepostyle» developments, where packages are sublinked under
project and you edit them together. The restriction remains for independent projects (not under one
tree): it is impossible to combine them into one graph - `additional_workspace_folders` Serena only for now
for TypeScript.
:::

## Engine override (any code-intelligence MCP)

The engine is specified per project - for example, a stack-specific server instead Serena:

```json
{ "id": "flexcrm", "code": true,
  "code_server_name": "laravel-boost",
  "code_command": "php",
  "code_args": ["artisan", "boost:mcp"] }
```

Fields: `code_command` (binary, checked in PATH), `code_args` (args; placeholder
`{root}` → project path), `code_server_name` (server name in `.mcp.json`). Defaults - in section
`code_graph` config (see [Config](./config)), can be set globally or per project.

## Indexing: once during provisioning, then on the fly

The meaning of the code graph is **token saving**: agent asks for a specific character (`find_symbol`,
`get_symbols_overview`, `find_referencing_symbols`) instead of reading entire files. Indexing
Serena — **not scheduled batch job**. `pre_index` (`code_graph.pre_index`, default `true`)
background warms up `.serena/cache/` EXACTLY ONCE - when first created `.serena/project.yml`
(`codegraph.py:_maybe_pre_index`, is called from `apply_serena_config`, which itself does not touch
file if it already exists - Serena still owns it). Repeatedly `pre_index` **never** not
starts automatically, even on regular `maind sync`.

Next Serena updates the index **incrementally on the fly** via LSP as calls are made in the current
sessions (official upstream doctrine: «Run `serena project index` once; Serena automatically
updates the index as files change» — [oraios/serena, 040_workflow.md](https://github.com/oraios/serena/blob/main/docs/02-usage/040_workflow.md)).
From here there are two conclusions:

- **Old mtime `.serena/cache/` — is not a bug.** It shows the date of first warm-up, not
  «rotten index»: character queries always read the actual file from disk via LSP.
  The only effect of an outdated cache is on cold (first request in a new session after
  large volume of changes) might be a little slower; correctness does not suffer. Manual
  reheating (`serena project index <path>`) only makes sense (a) if it's real
  palpable, or (b) after massive refactoring/renames.
- **Zero calls Serena for a fleet of sessions is a real problem,** but different: it means the agent is not
  knows about the graph and reads files directly (Read/Grep) — token saving doesn't work, ALTHOUGH
  infrastructure is up. The reason is almost always the same - the skill distributing this discipline
  `ecosystem-mcp` (provider `ecosystem-skill`, see [Sync](./sync)) or not rolled out
  (`absent`), or rolled out BEFORE the rule was added to it «first graph/characters, then
  broad search» (`stale` — template in maind has since been updated). Diagnostics: count
  `mcp__<code_server>__*` calls to `<project>/.claude/runs/*.json` (`tools.by_name`, writes
  run-report-package hook harness) — 0 when the code graph is raised means exactly this, not a problem
  indexing. Fleet-check and fix - section «How to find out what sync is generally needed (drift-gate)»
  on page [Sync →](./sync) (`maind doctor --skill-drift`).

## When to use

- **agent-memory** — «things to remember»: decisions, agreements, context of changes.
- **code-MCP (Serena)** — «how the code works»: symbol navigation/links/implementations in the repository.
- **maind-graph** — «who depends on whom»: packet topology/docks between projects.

Next: [CLI →](./cli)
