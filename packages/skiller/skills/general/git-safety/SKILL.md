---
name: git-safety
bucket: general
version: 0.1.0
lifecycle: init
description: "Guard against destructive git commands via a Claude Code PreToolUse hook: blocks push/reset --hard/clean -f/branch -D/checkout ./rebase --onto BEFORE execution. Activate on project init (esp. production/embedded) or when asked to add git guardrails / forbid dangerous git."
risk: write
persona: oss-dev
tags: [git, safety, hooks, guardrails, init]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
disable-model-invocation: false
sha256: ""
---

# Git Safety (guardrails)

Sets PreToolUse-hook that blocks dangerous git-commands **to** execution. In our ecosystem
the hook script itself belongs to the package **harness** (source of truth hooks), and this skill is the entry point:
explains and helps enable.

## When to activate

Once per project (`lifecycle: init`) — on onboarding, especially for production and embedded-projects
(POS, fiscal devices), where `git reset --hard`/`git push` on the device branch = trip to the hardware.
Or by explicit request «add git-guardrails / ban dangerous git».

## What is blocked

`git push` (on `--force`/`--force-with-lease`), `git reset --hard`, `git clean -f`/`-fd`,
`git branch -D`, `git checkout .`/`git restore .`, `git rebase --onto`.

## How to enable

1. Install hook files globally (once per machine): `harness hooks --global` — puts
   `~/.claude/hooks/git-guardrails/block-dangerous-git.sh`.
2. Register PreToolUse-hook (merge-only) in `.claude/settings.json` project
   (or `~/.claude/settings.json` global):

   ```json
   {
     "hooks": {
       "PreToolUse": [
         { "matcher": "Bash", "hooks": [
           { "type": "command", "command": "~/.claude/hooks/git-guardrails/block-dangerous-git.sh" }
         ] }
       ]
     }
   }
   ```

   If settings already exists - merge into an existing array `hooks.PreToolUse`, without grinding the rest.
3. Check: `echo '{"tool_input":{"command":"git push origin main"}}' | ~/.claude/hooks/git-guardrails/block-dangerous-git.sh` → exit 2 + BLOCKED.

> Customization of the list of patterns - editing the script (source: `packages/harness/configs/claude-code/hooks/git-guardrails/`).
> Follow-up: flag `harness hooks --git-guardrails on` for auto-registration in settings.

## Related skills

- `general/git-commit-rules` — commit format (what is allowed), git-safety — which is prohibited.
- `oss-dev/github-flow` — general git-thread on top of which they work guardrails.
