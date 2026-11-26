---
description: "Pour in permissions-presets Claude Code in .claude/settings*.json current project (autodetect stack)."
---
Apply permissions-hardware presets for the current project.

1. Specify target: current directory (`--target .`) or other path.
2. By default, the stack is detected automatically (base + laravel/php-package/node/python/docker). Explicit set - `--preset base,laravel`.
3. Show available presets when asked: `harness permissions --list`.
4. Suggest first `--dry-run`, then write it down.

Launch (via Bash):
```
harness permissions --target . [--preset a,b] [--file settings.json|settings.local.json] [--dry-run]
```
Merge-only: existing rules are saved, the file is backed up to `*.bak`. User Arguments - «$ARGUMENTS».
