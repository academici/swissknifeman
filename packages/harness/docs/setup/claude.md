# Setting up the environment Claude Code

How to set up the machine and projects once so that Claude Code worked
offline: no endless permission-prompts, but with a full audit of
what the agent actually does.

## Problem

During active development Claude Code asks for confirmation for almost every
terminal command. In practice it looks like this:

- in 100% cases is pressed «confirm», and the result is checked after the fact -
  prompts do not protect, but only interrupt the work;
- have to sit at the computer and wait for the next question instead of
  to give the agent a task and return to the finished result;
- point permissions «to a specific command» are not reused: same
  command with a different file or flag requires confirmation again.

Analysis ~5000 Bash-commands from real transcripts showed the scale of the problem:

| Command type | Share | Examples |
|---|---|---|
| Clean read-only | **72.7%** | grep, find, ls, cat, git diff/log/status |
| Repeatable dev-operations | ~21% | pest, composer, docker compose exec, git add/commit |
| Rest | ~6% | curl, rm, one-time commands |

That is, almost three quarters of prompts come from commands that do nothing
do not change - they can be safely resolved once and for all.

## Solution: three layers

### 1. Global baseline (`~/.claude/settings.json`)

Preset [`settings.global.json`](https://github.com/academici/swissknifeman/tree/main/configs/claude-code)
is installed once per machine and is valid in all projects:

- **allow** — all read-only (grep/find/ls/cat/head/tail/jq/awk…),
  read-only git (diff/log/status/show/branch), safe git
  (add/commit/checkout/stash), file operations (mkdir/cp/mv/touch),
  orchestration (`Workflow`/`Agent`/`TodoWrite` — so that multiphase workflow does not
  asked for confirmation after each stage; parsing - in
  [presets permissions](../configs/claude-permissions));
- **ask** — irreversible: `git push`, `git reset --hard`; (`rm` not controlled
  ask-rule, and auto-approve-hook: deny outside of trusted directories, allow
  inside - see `harness safe-dirs`);
- **deny** — always blocked: `sudo`, force-push, `git config --global`,
  `chmod 777`, reading secrets (`.env`, `*.pem`, `*.key`, `~/.ssh`, `~/.aws`).

### 2. Project Profile (`.claude/settings.local.json`)

Top baseline a stack preset is rolled into each project -
[see detailed analysis](../configs/claude-permissions). Auto detect by markers:
`artisan` → laravel, `composer.json` → php-package, `package.json` → node,
`Dockerfile` → docker. After this, tests, linters, composer and artisan
work without prompts, and destructive (`migrate:fresh`,
`docker system prune`) remains under confirmation.

### 3. Command log - «proxy» for audit

Since the agent is autonomous, we need a way to verify after the fact that it
did. Instead of an external proxy daemon, a native mechanism is used hooks:
PreToolUse-hook `log-bash-command.sh` writes **every** Bash-command in
`~/.claude/logs/bash-commands.jsonl` — time, project, team, description.
Hook only logs and never blocks execution.

```bash
# Last 20 commands
tail -20 ~/.claude/logs/bash-commands.jsonl | jq -r '"\(.ts) [\(.cwd)] \(.command)"'

# All commands for a specific project
jq -r 'select(.cwd | test("myproject")) | .command' ~/.claude/logs/bash-commands.jsonl

# Frequency analysis: which commands the agent executes most often
jq -r '.command' ~/.claude/logs/bash-commands.jsonl | awk '{print $1}' | sort | uniq -c | sort -rn | head
```

Key Principle: **deny stronger allow** — even wide prefixes will not be missed
`sudo`, force-push or reading secrets. Control shifts from «confirm
every step» on «prohibit dangerous + check log».

## Installation

```bash
cd ~/projects/packages/swissknifeman

# 1. Once per machine: global baseline + hook-logger
./scripts/apply-permissions.sh --global

# 2. In each project: stack preset (autodetection)
./scripts/apply-permissions.sh --target ~/projects/my-app

# Preview without recording / explicit set
./scripts/apply-permissions.sh --target . --dry-run
./scripts/apply-permissions.sh --target . --preset base,laravel,docker
```

The script is idempotent: the rules are merged with existing ones without duplicates, nothing
is not overwritten, a backup is created before recording `*.bak`. Yours `model`,
`mcpServers` and other settings in `~/.claude/settings.json` are not touched.

::: warning Restart required
Hooks and permissions are picked up at the start of the session - after `--global`
restart open sessions Claude Code (and window VSCode with extension).
:::

## If prompts still appear

1. **Repeated command** — add its prefix to the preset
   (`Bash(vendor/bin/pest *)` covers any arguments) and reinstall.
2. **Automatic selection** — skill `/fewer-permission-prompts` in Claude Code
   itself analyzes transcripts and offers allowlist.
3. **Variable commands** — wrap them in stable scripts
   (`composer ai:test`, `npm run ai:lint`): one rule per script instead
   dozens of unique commands.
