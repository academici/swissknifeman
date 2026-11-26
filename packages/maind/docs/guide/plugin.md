# Plugin Claude Code

maind supplied and how **plugin Claude Code** — thin face above CLI. You install the plugin in any
project → appear slash-commands `/maind:*`, which the hub is controlled directly from the chat, without leaving
terminal. The plugin does not duplicate anything: the commands call the same `maind` (see [CLI](./cli)).

Plugin - **commands only/skills, without their own MCP-server**. MCP-hub tools to project
come in a separate channel - per-project server `maind` from `.mcp.json` project (writes it
`deploy`/`onboard`). So there is exactly one `maind`-string (project-lens), and not two.

## What's inside

| Artifact | Purpose |
|:--|:--|
| `.claude-plugin/plugin.json` | plugin manifest (name `maind`, path to commands) |
| `commands/*.md` | slash-commands - wrappers over CLI |

> Marketplace — single `swissknifeman` at the root of the monorepo (generates `skiller registry`,
> adding maind sibling-package). Own marketplace y maind no.

## Installation

First - normal installation CLI (plugin commands name `maind` from PATH):

```bash
cd maind && ./install.sh          # symlink ~/.local/bin/maind
```

Then in Claude Code:

```
/plugin marketplace add /path/to/swissknifeman   # single marketplace monorepo
/plugin install maind@swissknifeman
```

After reboot, commands appear `/maind:*`. MCP-the plugin does not raise servers -
hub tools gives per-project server `maind` from `.mcp.json` project (check `/mcp`).

## Commands

| Command | What it does | Wrapper over |
|:--|:--|:--|
| `/maind` | front door: command list + routing | — |
| `/maind:onboard <project>` | connect the project: clarifies with dialogue bundle/code graph/brain → applies | `maind onboard --yes` |
| `/maind:sync [--all]` | roll out managed artifacts into projects | `maind sync` |
| `/maind:status` | status of the hub and ecosystem projects | `maind status` · `projects list` |
| `/maind:health [--fix]` | health of the connection between the current project and the hub | `maind health --cwd` |
| `/maind:doctor` | node environment diagnostics | `maind doctor` |

## How interactivity works

slash-command runs bash **not in TTY**, therefore an interactive wizard with `input()` not here
works. «Set selection» (bundle, code-graph, brain) command `/maind:onboard` leads **dialogue
agent**: asks in chat → collects selection → calling CLI non-interactive with flags
(`--bundle … --yes`). Mutating commands (`onboard`, `sync`) show first `--dry-run`, then
apply upon confirmation.

## MCP-hub tools (without a separate plugin server)

Previously, the plugin bundled its own server `maind-hub` (`--scope global`), and he stopped by **every**
session over per-project server `maind` — two identical `maind`-lines in `/mcp`, different scope,
slight miss «write to global instead project». Now the plugin **MCP-does not support the server**.

Hub Tools (`maind_projects_list`, `maind_projects_status`, `maind_agents_list`, graph traversals,
memory) gives **per-project server `maind`** from `.mcp.json` project (`maind mcp --scope project:<id>`,
writes `deploy`/`onboard`). Count, `projects_*`, `links` — **scope-independent**: one project-server
sees the entire ecosystem. `scope` affects only the default memory bucket. A project-pinned server does
**not** write to `global` (every project reads it, so one injected fact would reach them all): the owner
writes an ecosystem fact with `maind memory remember --scope global ...`. See [MCP-server](./mcp).

## Cross-provider

Rich UX (slash-commands, hooks) — is the format Claude Code. Universal, cross-provider layer -
**MCP**: `maind mcp` works with any client (Cursor via `.cursor/mcp.json` etc.). Skills -
provider-neutral `SKILL.md` (roll out swissknifeman). «Plugin» — this Claude-specific
packaging over universal MCP-kernels, not a separate implementation.
