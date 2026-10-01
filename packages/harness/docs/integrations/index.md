# Integrations

swissknifeman distributes skills and configs. This section is a directory **external
tools**, which connect to Claude Code next: MCP-servers (is given to the agent
new tools) and non-MCP utilities (processes on top of agent).

The catalog solves two problems: it provides a verified description of each tool (what is this,
why, pitfalls) and for a curated set MCP — ready preset, which
is set with one command.

## How to install

- **Preset via `integrate`** (recommended for curated set). Verified
  server configs are in `configs/claude-code/mcp/<name>.json`; `integrate` pours them in
  in `<project>/.mcp.json` merge-only (other people's servers are intact, backup `*.bak`):

  ```bash
  skiller integrate --mcp playwright,filesystem
  ```

  `context7` is included in dev-default and set without flag (in everything except obsidian-vault).
  Other presets - **opt-in** via `--mcp`.
- **Manual** — copy the example config from the tool page to `.mcp.json` project.

::: tip The hub does not configure itself
swissknifeman **distributes** presets to consumer projects, rather than editing your own
`.mcp.json`. Root `.mcp.json` registry holds machine-specific servers - it is not
touching.
:::

## MCP-servers

| Tool | Preset | Purpose |
|---|---|---|
| [Context7](./context7) | `context7` (dev-default) | current library documentation in context |
| [Playwright MCP](./playwright-mcp) | `playwright` | browser automation, E2E |
| [filesystem](./filesystem) | `filesystem` | access files in specified directories |
| [fetch](./fetch) | `fetch` | HTTP-requests → markdown |
| [memory](./memory) | `memory` | knowledge graph between sessions |
| [sequential-thinking](./sequential-thinking) | `sequential-thinking` | step-by-step reasoning |
| [GitHub MCP](./github) | `github` (remote) | Issues / PR / repositories |
| [Task Master AI](./task-master) | — (docs-only) | manage tasks from PRD |

## Non-MCP tools

| Tool | Type | Purpose |
|---|---|---|
| [GitHub Spec Kit](./spec-kit) | CLI + templates | spec-driven development |
| [Claude Code Router](./claude-code-router) | proxy | routing between models - ⚠️ doubtful |

## Contents of the curated set

Presets `playwright`, `filesystem`, `fetch`, `memory`, `sequential-thinking`, `github` —
**opt-in**: are not installed by default, only by `--mcp`. Default in development environments
only goes `context7`. Full list of presets - `configs/claude-code/mcp/`, see also
[overview of configs](../configs/).
