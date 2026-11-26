# Configs: Swiss army knife for agents

Skills are half the battle. For an agent to work immediately in a new project, we need more
and **configs**: permissions, settings, specifics IDE. Section `configs/` collects
ready-made configs in one place - according to the same principle as skills: one
source of truth, installation with one command.

## What already exists

| Config | Where is | What it does |
|---|---|---|
| [Presets permissions for Claude Code](./claude-permissions) | `configs/claude-code/` | ready `settings.json` with maximum allowed access: git, composer, artisan, npm, docker — by stacks |
| MCP-servers | `configs/claude-code/mcp/` | presets `.mcp.json`; `context7` puts `skiller integrate` default, curated subset (playwright, filesystem, fetch, …) — opt-in via `--mcp`. Catalog: [Integrations](../integrations/) |
| [Agent-packs](./agent-packs) | `configs/claude-code/agent-packs/` | versioned subagent packs/rules under the stack/role - provenance-header, overrides, drift-detect |
| [Statusline: context and notifications](./statusline) | `configs/claude-code/statusline/` | status line with actual context percentage + OS notification when threshold is crossed (opt-in, `harness hooks --statusline context`) |

## Script

We raised a new project - for example, on Laravel. Two teams, and the agent is completely
ready for use:

```bash
# 1. Skills: auto detect → architect, php, devops, quality, operator
skiller connect

# 2. Permissions: autodetection → base + laravel + node (+ docker, if available Dockerfile)
~/projects/packages/swissknifeman/packages/skiller/scripts/apply-permissions.sh --target .
```

After this Claude Code can run `php artisan`, `composer`, tests,
linters and git-commands without permission-prompts, and secrets (`.env`, keys,
`~/.ssh`) remain prohibited.

## What's planned

The section will grow as practice accumulates:

- **Agents** — pre-configured subagents (`.claude/agents/`) for standard roles;
- **Hooks** — `settings.json`-hooks: auto-formatting after edits, validation
  before commit;
- **More MCP-servers** — `context7` distributed by default, curated subset
  (playwright, filesystem, fetch, memory, sequential-thinking, github) — opt-in via
  `--mcp`; tools catalog - section [Integrations](../integrations/). Next - new ones
  tested configurations `.mcp.json`;
- **Cursor** — [Settings Cursor](../setup/cursor): `.cursor/cli.json`, `.cursor/permissions.json`, `.cursor/mcp.json`; profiles observe / workspace-contained / trusted-full-access.

The principle is the same as for skills: everything is tested in battle, everything is in one place,
is set with one command.
