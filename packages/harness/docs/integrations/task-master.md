# Task Master AI

::: tip Help only (docs-only)
Preset for `integrate` not supplied: Task Master requires provider keys and creates
working files in the project. Connect manually and as needed.
:::

## What is this

Task Master (eyaltoledano) — AI-task manager: parsing PRD (project description/sprint) and
generates a structured backlog with dependencies and priorities. Works like CLI and how
MCP-server.

- Repository: <https://github.com/eyaltoledano/claude-task-master>
- npm: `task-master-ai`

## Installation

CLI:

```bash
npm install -g task-master-ai
task-master init
```

MCP (upon request) — in `.mcp.json` project:

```json
{
  "mcpServers": {
    "task-master-ai": {
      "command": "npx",
      "args": ["-y", "--package=task-master-ai", "task-master-ai"],
      "env": { "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}" }
    }
  }
}
```

::: warning Need a key and a budget token
At least one provider key is required (or OAuth Claude Code / Codex CLI). MCP-server
is loading ~36 tools (~21k tokens) — via `TASK_MASTER_TOOLS` (`core` / `standard` /
`all` or list) can be narrowed down.
:::

## Workflow

```bash
task-master parse-prd <prd>          # PRD → tasks
task-master list                     # list
task-master next                     # next task
task-master set-status --id=<id> --status=done
```

Models are configured by three roles (main / research / fallback) — indicate current models
Claude (for example, Sonnet 4.6 for parsing, Haiku 4.5 for cheap operations).

## Nuances

- Creates working files (`.taskmaster/`) — decide whether to commit or to `.gitignore`.
- Mates well with spec-driven approach: specification → PRD → tasks (see
  [Spec Kit](./spec-kit)).
- Redundant for small tasks; in projects academici basic tracking is already closed
  `general/task-brief-template` + GitHub Issues (`oss-dev/github-flow`).
