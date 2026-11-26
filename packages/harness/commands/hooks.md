---
description: "Enable hooks Claude Code (auto-approve/memory) by project or install hook files globally."
---
Harness hook setup.

Global installation of hook files (once on the car - puts `auto-approve/`, `memory/`, `notify/`, `log-bash-command` in `~/.claude/hooks/`):
```
harness hooks --global [--dry-run]
```

By project (enable modes - hook files must already be installed globally):
```
harness hooks --target . [--auto-approve strict|permissive|bypass|off] [--memory core:federation] [--statusline context|off] [--file settings.json] [--dry-run]
```
- `--auto-approve` writes `.claude/auto-approve.env.ini` and registers a hook on Bash/ExitPlanMode (merge-only).
- `--memory BRAIN:MODE` attaches the project to the brain: `.swissknife.json:memory_brain` + `.claude/memory.env.ini`.
- `--statusline context` puts the key `statusLine` in `.claude/settings.local.json` — string with context percentage + OS notification when threshold is crossed (`off` removes, but only our key).

Parse the intent from «$ARGUMENTS»; for bypass-mode warn that it removes confirmations (for containers only/VM).
