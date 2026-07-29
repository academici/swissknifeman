# Finding 04 — runtime preflight 2026-07-24

## Green

- cwd: `/home/vostrikov/projects/packages/swissknifeman`
- `codex doctor --json`: overall `ok`, Codex 0.145.0,
  `gpt-5.6-sol`, approval `Never`, filesystem sandbox `unrestricted`,
  hooks/plugins/multi-agent enabled.
- `./packages/maind/bin/maind health --cwd --json`: connected,
  `memory_roundtrip=true`, `maind_mcp=true`, `code_mcp=true`.
- Project SessionStart command exists and parses as Bash.

## Not green

`./packages/harness/bin/harness hooks --provider codex --observer --trusted
--target <repo> --dry-run`:

- `harness.codex.lifecycle.hooks: ownership-conflict → refuse
  (unmanaged-target)`;
- `harness.codex.lifecycle.handler: missing → create`.

`./packages/harness/bin/harness doctor`:

- global Claude hook files installed;
- `run-report/_lib.py` stale.

Effective Codex sources одновременно содержат:

- global `~/.codex/hooks.json`: two `PreToolUse` Bash hooks и
  `SubagentStop` review gate;
- project `.codex/hooks.json`: `SessionStart`, который вызывает
  repo `.claude/maind-memory.sh`;
- trusted hashes per source в `~/.codex/config.toml`.

Current OpenAI hooks behavior запускает все matching hooks across sources;
higher-precedence config не заменяет lower hook list. Поэтому duplicate/
stale registration влияет на live behavior.

## Design consequence

P0.4 обязан после P0.3 Owner freeze:

1. определить owning source каждого effective hook;
2. восстановить managed target/handler;
3. проверить command existence/executable;
4. провести synthetic cold-start probe;
5. проверить retained live-session path или оставить compatibility shim до
   restart;
6. не объявлять green только по generator/hash.
