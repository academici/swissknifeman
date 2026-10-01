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

harness doctor                                 # diagnostics
```

Writing to projects - **merge-only**: existing rules/servers are saved, file
is backed up to `*.bak`.

## Presets

Source of truth - `configs/claude-code/`:

| What | Where |
|:--|:--|
| permissions by stacks | `settings.{base,laravel,php-package,node,python,docker}.json` |
| global baseline / bypass / strict | `settings.{global,yolo,product-boundary}.json` |
| MCP-servers | `mcp/{context7,playwright,filesystem,fetch,memory,github,sequential-thinking}.json` |
| hooks | `hooks/{auto-approve,memory,notify}/`, `hooks/log-bash-command.sh` |

Details on auto-approve and unified memory - `configs/claude-code/README.md`.

## Development

```bash
bash scripts/validate.sh     # py_compile + bash -n + JSON + frontmatter + tests
bash scripts/test.sh         # unittest
```

Agent Guide - [CLAUDE.md](CLAUDE.md).
