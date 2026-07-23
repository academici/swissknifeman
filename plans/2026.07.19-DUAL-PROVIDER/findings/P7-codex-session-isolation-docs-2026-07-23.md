# P7.2 — official Codex session-state isolation facts

**Verified:** 2026-07-23
**Source class:** current first-party Codex manual, refreshed through the repository
`openai-docs` helper into a task-local `/tmp` cache.
**Confidence:** high.

## Official facts

1. `CODEX_HOME` is the supported root for Codex state, including configuration,
   authentication, logs, sessions, skills and standalone package metadata.
2. `CODEX_SQLITE_HOME` is the supported root for SQLite-backed CLI/app-server state;
   it defaults to `CODEX_HOME`, while a configured `sqlite_home` takes precedence.
3. `codex exec --ephemeral` is the supported non-interactive mode when rollout/session
   files must not be persisted.
4. `codex exec --ignore-user-config` prevents loading the user `config.toml`; authentication
   still uses the selected Codex home unless it is supplied explicitly.
5. `CODEX_API_KEY` is supported only for one non-interactive `codex exec` invocation.
   `CODEX_ACCESS_TOKEN` is supported for trusted automation; either can avoid reading a
   persisted host `auth.json`.
6. `shell_environment_policy.exclude` is the supported way to prevent automation credentials
   from being forwarded to model-launched subprocesses.

Sources:

- <https://learn.chatgpt.com/docs/config-file/environment-variables>
- <https://learn.chatgpt.com/docs/non-interactive-mode>
- <https://learn.chatgpt.com/docs/config-file/config-advanced#shell-environment-policy>
- <https://learn.chatgpt.com/docs/enterprise/access-tokens>

## Installed CLI confirmation

The installed CLI was queried only with fresh task-temporary `HOME`, `CODEX_HOME` and
`CODEX_SQLITE_HOME`. `codex exec --help` exposes `--ephemeral`, `--ignore-user-config`,
`-C`, `-m` and `-s`; the top-level help exposes `-a/--ask-for-approval`. No agent, plugin
command or host-state operation was run by this syntax check.

## Evidence relationship

`findings/P7-self-host-probes-2026-07-19.md` proves that the D118 child plugin commands
stored their marketplace/plugin payload under the task-specific `CODEX_HOME`, while the
already-active parent Codex session continued changing its own host JSONL and SQLite/WAL
state. The official facts above support relocating the *executor process* as well as the
child plugin commands; they do not support excluding active-session paths from the
zero-delta gate.
