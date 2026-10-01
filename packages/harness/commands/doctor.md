---
description: "Environment diagnostics harness: presets permissions/MCP, script, hook files; settings audit Claude Code (--settings)."
---
Run diagnostics of the hardware environment and briefly explain the result.

```
harness doctor
```
Checks: presence `configs/claude-code/` (presets settings/MCP), `scripts/apply-permissions.sh`, and whether hook files are installed globally in `~/.claude/hooks/` (`notify`/`auto-approve`/`memory`). If there are no hooks, suggest `harness hooks --global`.

## Settings audit Claude Code (`--settings`)

```
harness doctor --settings [--target P] [--json] [--profile NAME]
```
Separate thread (settings-doctor): reads all settings layers Claude Code target project (`user → project → local → managed`), builds an efficient configuration with provenance and reports conflicts according to the taxonomy of checks. Doesn't write to disk (read-only).

- `--target P` — audit project (default current directory);
- `--profile NAME` — check with explicit policy-profile, overriding the declaration `.swissknife.json:policy_profile`;
- `--json` — the only output in stdout: machine document (`{"target","profile","counts","findings","exit"}`) for CI/fleet-scan;
- **exit-code**: `0` — clean (no finds or only notes), `1` — there are warnings, `2` — there are errors. `--json` does not change the code.

Facade of the same audit from the skill registry - `skiller doctor --settings [--target P]` (delegates here via subprocess).
