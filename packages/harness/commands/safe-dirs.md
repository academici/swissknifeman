---
description: "Manage allowlist'om trusted directories (safe-dirs): where auto-approve allows rm/rmdir."
---
Manage machine-owned allowlist'ohm `safe-dirs.json` (lives AT THE ROOT of the monorepo swissknifeman, gitignored; template - `safe-dirs.example.json`; search ladder with hook: `$SKM_SAFE_DIRS_CONFIG` → monorepo root → legacy `~/.swissknifeman/`) — inside its roots (recursively) auto-approve skips `rm`/`rmdir` past deny_hard (code below git — deletion is reversible). Beyond the Roots rm is blocked as before.

```
harness safe-dirs init                                    # create a config with defaults
harness safe-dirs list                                    # effective allowlist through the eyes of a hook
harness safe-dirs add <path> [--exclude] [--dry-run]      # add root (or withdrawal)
harness safe-dirs remove <path> [--exclude] [--dry-run]   # remove root (or withdrawal)
harness safe-dirs prune-ask [--global] [--target P] [--all-projects]
```

- Default `include_registered_projects=true` — paths of onboarded projects from the skiller registry (`<state>/skiller/projects.json`) are turned on automatically.
- `add` will refuse `/`, `$HOME` and ancestors `$HOME` (the same guard in the hook itself).
- `prune-ask` removes static ask-rules `Bash(rm -r *)`/`Bash(rm -rf *)` from settings — hook-allow does not penetrate them, without cleaning rm in safe-dirs will continue to prompt.
- Protection inside safe-dirs: the root itself is not deleted, `.git` protected (`protect_git`), globs are validated by static prefix (`allow_globs`).

Parse the intent from «$ARGUMENTS»; after the initial setup, tell me: `harness hooks --global` (update hook files) and restarting the session Claude Code.
