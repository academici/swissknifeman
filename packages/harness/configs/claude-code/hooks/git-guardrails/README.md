# git-guardrails — dangerous blocking hook git-commands

PreToolUse-hook Claude Code, which intercepts and blocks destructive git-commands **to**
execution (at level `Bash`-tool). Particularly important for production and embedded-projects, where
random `git reset --hard`/`git push` on the device branch may require physical access
to the hardware for recovery.

## What is blocked

`git push` (including `--force`/`--force-with-lease`), `git reset --hard|--keep|--merge`, `git clean`
with any `f` flag (not with `-n`), `git branch -D` and `--delete --force`, `git checkout .`/`-f`,
`git restore .` (not `--staged` alone), `git stash drop|clear`, `git reflog expire|delete`,
`git update-ref -d`, `git rebase --onto`, `git filter-branch`.

The check is on argv, not on text: `git_guard.py` (next to the script, stdlib Python) skips git's global
options (`-C dir`, `-c k=v`, `--git-dir=…`), wrappers (`env`, `sudo`, `xargs`, …), looks into `bash -c`,
`eval`, `$(…)`, backticks and `find -exec`, and resolves `-c alias.x=…`. The literal patterns in
`block-dangerous-git.sh` remain a safety net (they alone work when `python3` or `git_guard.py` is
missing), so **copy both files**. Codex, Cursor and Grok use the same `git_guard.py` through
`harness.lifecycle_git_guardrails_core`.

## Provenance

Derived from [mattpocock/skills](https://github.com/mattpocock/skills) →
`misc/git-guardrails-claude-code/scripts/block-dangerous-git.sh` (MIT, © Matt Pocock). Expanded
patterns `force-with-lease` and `rebase --onto`, message translated into Russian. In our architecture
hooks belong to the package **harness** (skiller delegates the environment here) — so the script lives here,
and not as a skill.

## How to enable

The hook file is installed globally along with the others (`harness hooks --global` → `~/.claude/hooks/`).
Then register PreToolUse-hook in settings project (`.claude/settings.json`) or globally
(`~/.claude/settings.json`), merge-only:

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

Skill wrapper with step-by-step instructions - `general/git-safety` (registry skiller).

## Verification

```bash
echo '{"tool_input":{"command":"git push origin main"}}' | ./block-dangerous-git.sh
# → exit 2 + message BLOCKED in stderr
```

## TODO (follow-up)

Start a flag `harness hooks --git-guardrails on|off` (according to the example `--auto-approve`), who himself
registers PreToolUse-hook in settings project - so as not to edit settings.json hands.
