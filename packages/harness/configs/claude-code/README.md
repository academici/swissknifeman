# Presets permissions for Claude Code

Ready-made permission sets for `.claude/settings.local.json` — for a new project
worked immediately without endless permission-prompts.

| Preset | What it allows |
|---|---|
| `base` | git (push — with confirmation), gh, file operations, curl/wget, jq/rg/sed; deny for secrets (`.env`, keys, `~/.ssh`) and `sudo` |
| `laravel` | `php artisan`, composer, pest/phpunit/pint/phpstan/rector, sail, npm/vite; destructive migrations - with confirmation; deny to token noise (`storage/logs`, `node_modules`, `*.lock`, caches) — `vendor/` **not** blocked: there Boost-guidelines (`vendor/laravel/boost/.ai/`) |
| `php-package` | composer, pest/phpunit/pint/phpstan/rector/infection — without artisan |
| `node` | node/npm/npx/pnpm/yarn, tsc, vitest, eslint, prettier; publish — with confirmation; deny to token noise (`node_modules`, `dist`, `build`, `coverage`, `*.lock`, minified bundles) |
| `python` | python/pip/pytest, uv, poetry, ruff/black/mypy |
| `docker` | docker + docker compose; deleting containers/volumes/prune — with confirmation |
| `yolo` | `bypassPermissions` — only for containers and VM, see warning in doc |
| `global` | baseline for `~/.claude/settings.json`: read-only commands (grep/find/ls/cat, git diff/log/status), safe git (add/commit/checkout/stash), deny on sudo/force-push/secrets + **hook-command logger** (active) + **notify** — OS notifications for confirmation request/statements (active) + installing files **auto-approve** (is included by design, see below) (via `--global`) |

## Quick start

```bash
# base + stack auto-detect based on project markers (artisan, package.json, pyproject.toml, ...)
./scripts/apply-permissions.sh --target ~/projects/my-laravel-app

# explicit set
./scripts/apply-permissions.sh --target . --preset base,laravel,docker

# preview without recording
./scripts/apply-permissions.sh --target . --dry-run

# global baseline + hook-logger in ~/.claude (once per machine)
./scripts/apply-permissions.sh --global
```

The script combines `allow`/`ask`/`deny` with existing goal rules
(does not overwrite anything, removes duplicates) and makes a backup `settings.local.json.bak`.

## Command log («proxy»)

Preset `global` registers PreToolUse-hook ([hooks/log-bash-command.sh](hooks/log-bash-command.sh)):
each Bash-command Claude Code is written in `~/.claude/logs/bash-commands.jsonl` —
at any time you can check what the agent actually did. Hook only logs,
never blocks. Picked up at the start of the session - after installation
restart Claude Code.

```bash
# last 20 commands
tail -20 ~/.claude/logs/bash-commands.jsonl | jq -r '"\(.ts) [\(.cwd)] \(.command)"'

# project-specific commands
jq -r 'select(.cwd | test("myproject")) | .command' ~/.claude/logs/bash-commands.jsonl
```

## MCP-servers (`mcp/`)

Presets `.mcp.json` for working scenarios - a bare server config object in
`mcp/<name>.json` (key in `mcpServers` = file name). `skiller integrate`
pours the selected presets into `<project>/.mcp.json` merge-only (other people's servers are intact,
backup `*.bak`, `--dry-run`). Description of each tool - in
[integration directory](https://academici.github.io/swissknifeman/integrations/).

| Server | Config | When |
|---|---|---|
| `context7` | `mcp/context7.json` (remote HTTP `mcp.context7.com/mcp`) | dev-default: development environments (everything except obsidian-vault); `recommended`/`full` — default |
| `playwright` | `mcp/playwright.json` (npx `@playwright/mcp`, headless) | opt-in: browser automation / E2E |
| `filesystem` | `mcp/filesystem.json` (npx `@modelcontextprotocol/server-filesystem`) | opt-in: access to the file system in specified directories |
| `fetch` | `mcp/fetch.json` (uvx `mcp-server-fetch`, **Python/uv**) | opt-in: HTTP → markdown |
| `memory` | `mcp/memory.json` (npx `@modelcontextprotocol/server-memory`) | opt-in: knowledge graph between sessions |
| `sequential-thinking` | `mcp/sequential-thinking.json` (npx) | opt-in: step-by-step reasoning |
| `github` | `mcp/github.json` (remote `api.githubcopilot.com/mcp/`) | opt-in: Issues/PR/repositories |

Curated subset (everything except `context7`) — **opt-in**, is not set by default:

```bash
skiller integrate --mcp playwright,filesystem
```

Add server: put preset in `mcp/`; so that it is distributed by default in
dev-projects - add name to `DEV_MCP` (`lib/skiller/integrate.py`).

## OS notifications (notify)

Preset `global` registers Notification-hook
([hooks/notify/notify.sh](hooks/notify/notify.sh)): as soon as Claude Code
is waiting for a person - **tool permission request**, **plan approval**
(ExitPlanMode) or a simple prompt longer ~60 sec - OS notification pops up
with the request text and project name. It is convenient when the agent works in the background and
no need to keep the terminal in focus. Hook only notifies, never blocks.

Cross-platform, backend selected by OS (if there is none, it leaves quietly):

| OS | Backend |
|---|---|
| Linux | `notify-send` (libnotify) |
| macOS | `terminal-notifier` → `osascript` |
| WSL / Windows | PowerShell toast → `MessageBox` → `msg.exe` |

Picked up at the start of the session - after `--global` restart Claude Code.

## Auto-approval of commands (hooks)

Prefix allow-rules (`Bash(grep *)`) not matched **compound commands** —
with `cd ... &&`, loops `for`, pipes, substitutions `$(...)`. Such commands
are unique each time and depend on permission-prompt, no matter how many patterns you add.
Solution - PreToolUse-hooks that parse **all** line and make a decision.

### One switch, mode in `env.ini`

Everything in a self-contained folder [`hooks/auto-approve/`](hooks/auto-approve/) — her whole
publishes swissknifeman, and you select the mode in the file. Root
[`auto-approve.sh`](hooks/auto-approve/auto-approve.sh) — **switch**: reads
mode from [`env.ini`](hooks/auto-approve/env.ini) and calls one of
[`modes/`](hooks/auto-approve/modes/). Sources - [`CREDITS.md`](hooks/auto-approve/CREDITS.md).

```
hooks/auto-approve/
  auto-approve.sh   # switch (is registered on Bash + ExitPlanMode)
  env.ini           # MODE=strict|permissive|bypass|off  ← mode selection
  config.json       # designs (allow/deny/subcommands)
  lib/{common,analyze}.sh
  modes/{strict,permissive,bypass}.sh
```

One file is registered for both matchers; shift `MODE` in `env.ini` → **restart
Claude Code**. Modes - range of autonomy:

| `MODE` | Commands (Bash) | Plan (ExitPlanMode) |
|---|---|---|
| `strict` | allowlist-first: read-only → allow, mutations → prompt, disaster → deny | prompt |
| `permissive` | denylist-first: everything except denilista → allow, mutations → prompt, disaster → deny | prompt |
| `bypass` | everything but catastrophic (`deny_hard`) → allow | **auto-confirm** |
| `off` | normal permission-flow | normal |

**Denilistas (general, from `config.json`):**
- `deny_hard` (catastrophic: `sudo`/`rm`/`mkfs`/fork-bomb/`\| sh`/writing to disk) →
  **active `deny`** in all modes.
- `deny_block_approve` (mutation: `mv`/`cp`/write to file/`git push`·`commit`/`docker run`/
  `npm install`/`sed -i`) → **prompt** (in `strict`/`permissive`).
- `strict` additionally requires that the head of each segment be from `allow`
  (read-only coreutils, read-subcommands `git`/`gh`/`docker`, `jq`/`awk`/`sed`,
  inline `python3 -c`/`node -e`).

Config and mode have a per-project file, `<project>/.claude/auto-approve.config.json` and
`auto-approve.env.ini` (or `AUTO_APPROVE_MODE` in `.swissknifeman/hooks.env`), but a project can
only **narrow** the machine settings: the mode can only go down (`bypass` → `permissive` → `strict`
→ `off`), `allow`-lists intersect with the machine ones, `deny_*` lists are united. A repository
therefore cannot switch a global hook to `bypass`. To let a trusted machine take the project files
as they are, set `ALLOW_PROJECT_CONFIG=1` in `~/.claude/hooks/auto-approve/env.ini`.

Parsing: `lib/shellscan.py` reads the command quote-aware: literal text in quotes is blanked, but
the body of `$(...)` and of backticks stays visible even inside double quotes. If `shfmt` is
installed its AST check is added (can only tighten); without it, `strict` asks for any command
with a substitution (`$(`, backtick, `<(`, `>(`) and without `python3` it asks for everything.
`deny_hard`/`deny_block_approve` also scan the unmasked text when a shell or interpreter
(`bash -c`, `python3 -c`, `eval`, `xargs`, …) carries a quoted body. Allowed read commands are
checked for flags that write or run code (`find -exec/-delete`, `sort -o`, `yq -i`, `env CMD`,
`git branch -D`, `git diff --output`, `gh api -f/-F/-X POST`, …) and `VAR=x cmd` prefixes are
limited to locale/terminal variables.

### Decision log

Each pass of the hook is written to `~/.claude/logs/auto-approve-decisions.jsonl`
(`ts`, `hook`, `cwd`, `decision`, `command`, `reason`) — shows what commands it calls
agent, and you can add the config:
```bash
# that ran into a prompt (decision=ask) — candidates for allow/deny
jq -r 'select(.decision=="ask") | .command' ~/.claude/logs/auto-approve-decisions.jsonl | sort | uniq -c | sort -rn | head
# solution distribution
jq -r .decision ~/.claude/logs/auto-approve-decisions.jsonl | sort | uniq -c
```

### Inclusion by project

Global (`global`) **only files are installed** `~/.claude/hooks/auto-approve/`
and the log-logger itself is activated auto-approve **is NOT registered globally** (none
auto-approval in random directories). You enable the hook specifically in the desired project,
`<project>/.claude/settings.json`:
```jsonc
{ "hooks": { "PreToolUse": [
  { "matcher": "Bash",        "hooks": [{ "type": "command", "command": "~/.claude/hooks/auto-approve/auto-approve.sh" }] },
  { "matcher": "ExitPlanMode","hooks": [{ "type": "command", "command": "~/.claude/hooks/auto-approve/auto-approve.sh" }] }
] } }
```
Project mode - `<project>/.claude/auto-approve.env.ini` (otherwise the default is taken from
`~/.claude/hooks/auto-approve/env.ini`):
```ini
MODE=strict
```
After connecting/mode change - restart Claude Code.

> ⚠️ **Risk trade-offs.** `permissive` will approve an unfamiliar command outside of denilista;
> `bypass` will approve any command other than a catastrophic one and will confirm the plan himself - only
> trusted projects/containers. `python3 -c`/`node -e` are trusted only with `trust_inline_interpreters`. For complete «bypass all commands after the plan» in `bypass`-mode
> add to project settings `"permissions": { "defaultMode": "bypassPermissions" }`.

Detailed analysis of the syntax of rules and logic of presets - in
[documentation](../../docs/configs/claude-permissions.md).

## Unified memory (memory)

Silo problem: what is learned in one project is not remembered in a related one.
Self-contained folder [`hooks/memory/`](hooks/memory/) gives **general «brain»** —
but not to everyone, but **only to members of the same group** (`brain`). Structure and
ergonomics - like auto-approve: switch [`memory.sh`](hooks/memory/memory.sh),
mode in [`env.ini`](hooks/memory/env.ini), groups and members in
[`config.json`](hooks/memory/config.json), backends in [`modes/`](hooks/memory/modes/).

```
hooks/memory/
  memory.sh        # remember | recall | members | status | sync
  env.ini          # MODE=file|federation|agentmemory|off  ← backend selection
  config.json      # default_brain + brains{ <name>: { members, store, agentmemory } }
  lib/{common,store}.sh
  modes/{file,federation,agentmemory,off}.sh
```

| `MODE` | Storage | Search | Demon |
|---|---|---|---|
| `file` | one common store per group (markdown) | grep + ranking | no |
| `federation` | theirs `memory/` members + native memory Claude Code + general store | grep for all + ranking | no |
| `agentmemory` | third party AgentMemory (demon on Brain) | semantic | yes |
| `off` | — | — | — |

The modes are interchangeable - you switch `MODE` and compare on the same group.

**Membership.** `members` groups - names of topology nodes (`brain`/`swissknifeman`)
or keys/project paths (resolve via `<state>/maind/topology.json` +
`<state>/skiller/projects.json`; legacy `~/.swissknifeman/` copies while they are the only ones). The participant sees the brain only if it is in `members`.

```bash
# at the beginning of the task - ask the general brain
~/.claude/hooks/memory/memory.sh recall "retry backoff"
# capture cross-project-useful fact
~/.claude/hooks/memory/memory.sh remember --type project "retry-logic is duplicated in botkit and azguard"
~/.claude/hooks/memory/memory.sh status      # mode, group, participants, number of facts
```

**Per-project override** (like auto-approve): `<project>/.claude/memory.env.ini`
(MODE) and `<project>/.claude/memory.config.json` (group/members); plus
`memory_brain` in `<project>/.swissknife.json`. Installing files -
`./scripts/apply-permissions.sh --global` (code/lib/modes are updated, `env.ini`/
`config.json` are not overwritten). Tie Agent - skill `system/shared-memory`.
