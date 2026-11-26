# Sources and notes - memory

Self-contained hook folder «unified memory». Structure and ergonomics repeat
`hooks/auto-approve/` (switch + `env.ini` MODE + `config.json` + `modes/`
+ `lib/`), so that the modes are interchangeable and overridden by the config.

## Modes

- **file / federation** — own, on markdown-files. Fact schema compatible
  with native memory Claude Code (`name` / `description` / `metadata.type`),
  therefore `federation` reads his own `memory/` participants, and native
  `~/.claude/projects/<slug>/memory/`.
- **agentmemory** — proxy to third party **AgentMemory**
  (`@agentmemory/agentmemory`, npm), which is spinning like a demon on Brain
  (`cd ~/Vaults/Brain && npm run memory:start`, HTTP default `:4111`).
  Exact form HTTP-API depends on package version - path (`/memories`, `/search`,
  `/health`) and jq-sample in `modes/agentmemory.sh` are marked as requiring reconciliation
  with a real instance on the first run. Demon inaccessibility → honest
  message, no crash.

## What it DOESN'T do

The hook does not delete anything or overwrite anyone else's facts; `remember` only
adds. Installation via `apply-permissions.sh --global` updates the code/lib/modes,
but does NOT overwrite `env.ini`/`config.json` (there is your choice of mode and group composition).
