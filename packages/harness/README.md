# harness

**Setting up the environment Claude Code** for ecosystem projects academici: presets
permissions, modes auto-approve/bypass, MCP-servers and hooks (memory/notify/log).
One of the umbrella packages [`swissknifeman`](../../README.md) (nearby - `skiller`
for skills and `maind` for memory/column).

Previously, this functionality lived inside `skiller`; is placed in a separate package because
it doesn’t relate to skill management - it’s about harnes Claude Code.

## Installation

```bash
./install.sh                 # symlink harness in ~/.local/bin (package stateless)
# or from the monorepo root: ./install.sh  (puts skiller · maind · harness)
```

## Usage

```bash
# permissions: stack autodetect (base + laravel/php/node/python/docker)
harness permissions --target .                 # or --preset base,laravel
harness permissions --list                     # available presets
harness permissions --target . --dry-run

# MCP-servers → .mcp.json (merge-only)
harness mcp --list
harness mcp --target . --mcp context7,playwright

# hooks
harness hooks --global                         # hook files in ~/.claude/hooks (times per car)
harness hooks --target . --auto-approve strict # enable auto-approve for the project
harness hooks --target . --memory core:federation

harness hooks sync|show --target .             # modes: [harness.hooks] -> .swissknifeman/hooks.env
harness doctor [--json]                        # diagnostics (check-result/v1)
```

Writing to projects - **merge-only**: existing rules/servers are saved, the replaced file is kept through
`aicore.state.backup`.

## Configuration and state

Hook modes are keys of `[harness.hooks.<hook>]` in the project's `.swissknifeman/config.toml` (with `providers.<id>` overrides);
`harness hooks sync` generates the committed `.swissknifeman/hooks.env` that the installed hooks read first (then the legacy
`<provider>/<hook>.env.ini`, then their default). `policy_profile` is `[harness] policy_profile`. The `safe-dirs.json` allowlist is
`<config>/harness/safe-dirs.json`. The locks `.swissknifeman/provider-artifacts.lock.json` and `.claude/agent-pack.lock.json` stay in the
project. Legacy places are read with one warning until `swissknifeman upgrade`.

## Partners and JSON commands

harness imports only itself and `aicore`; other modules are reached through their commands found by `aicore.util.partners`
(the legacy `run` driver looks for planner with `PLANNER_ROOT`, `PLANNER_PLAN_PY` or `PATH`). maind reaches harness through
`harness mcp catalog --json`, `profiles resolve --json`, `hooks codex-lifecycle fragment|validate --json` and
`instructions scopes --json`; without harness maind skips its provider steps with `PARTNER_UNAVAILABLE`. The instruction catalog
(`configs/common/instructions/catalog.json`) holds the scope targets as data. See [docs/index.md](docs/index.md).

## Presets

Source of truth - `configs/claude-code/`:

| What | Where |
|:--|:--|
| permissions by stacks | `settings.{base,laravel,php-package,node,python,docker}.json` |
| global baseline / bypass / strict | `settings.{global,yolo,product-boundary}.json` |
| MCP-servers | `mcp/{context7,playwright,filesystem,fetch,memory,github,sequential-thinking}.json` |
| hooks | `hooks/{auto-approve,memory,notify}/`, `hooks/log-bash-command.sh` |

Details on auto-approve and unified memory - `configs/claude-code/README.md`.

## Skills

The plugin ships the skill `agent-packs` (agent packs and their sub-agent workflows). It lives in
`packages/harness/skills/` and is released with the module.
A project gets them through the `system` bucket of `skiller`: `skiller connect` enables the plugin `harness` and
`skiller sync` copies the skills into the project; the plugin can also be installed on its own.

## Development

```bash
bash scripts/validate.sh     # py_compile + bash -n + JSON + frontmatter + tests
bash scripts/test.sh         # unittest
```

Agent Guide - [CLAUDE.md](CLAUDE.md).
