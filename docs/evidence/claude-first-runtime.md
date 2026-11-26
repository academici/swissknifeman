# Claude Code First-Class Runtime Adapter Evidence (`P08.03`)

- **Date:** `2026-11-11`
- **Leaf:** `P08.03` — Claude Code adapter с изоляцией конфигов
- **Adapter:** `src/skm/adapters/runtimes/claude_code/` (`runtime_id = "claude_code"`, `adapter_version = "0.1.0"`)
- **Tested CLI Inventory Target:** `claude 2.1.266` (`resources/packs/core/runtimes/models.toml`)

---

## 1. Architecture & Module Boundaries

The `claude_code` runtime adapter implements `skm.modules.runtimes.ports.AgentRuntime` over the shared `_cli_session` supervisor (`CliSession`, `TranscriptWriter`, `StreamTail`, `SignalCollector`, `TrustedProcessRunner`) without ambient environment reads or global mutable singletons:

| Module | Responsibility |
|---|---|
| `detect.py` | Binary resolution via injected `PATH`, `claude --version` (10s timeout) and `claude --help` (20s timeout with 1 retry on timeout), required flag check, and instance-scoped 6-tuple probe cache `(binary_realpath, binary_sha256, version, os_kernel, adapter_version, launch_config_digest)`. |
| `permissions.py` | Renders `--tools`, `--disallowedTools`, `--permission-mode acceptEdits`, `--allowedTools`, `--add-dir`, private `0600` `<step_dir>/settings.json` (with provider sandbox enabled and hooks disabled), private `0600` `<step_dir>/mcp.json` (`${SKM_TOKEN}` env expansion, zero plaintext secrets on disk), and secret-free `ToolDenial` hints. |
| `launch.py` | Prepares `0700` isolated `client_home` (`projects`, `todos`, `statsig`, `debug`, `tmp`), copies `~/.claude/.credentials.json` as `0600` only when `runtimes.credentials.copy["claude_code"] = true` (failing closed with `RUNTIME_AUTH_EXPIRED` when absent), enforces K16 `--setting-sources`, strips host XDG/config paths, sets mandatory env vars, and prefixes `skm.adapters.sandbox.landlock_exec` when `isolation_profile == "landlock"`. |
| `stream_parser.py` | Stateful `StreamParser` over `--output-format stream-json`: maps `system/init`, `assistant` (`text`, `tool_use`, `thinking` suppressed to transcript only), `user` (`tool_result`), `system/permission_denied`, `system/api_retry`, `rate_limit_event`, and `result`. |
| `usage.py` | Normalizes `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens` with `cost_usd_micros = None`, deduplicates assistant turn usage by `message.id` (`status = estimated` on crash/abort), and tracks `SubagentUsage(used=<Task seen>, disclosed=False)`. |
| `runtime.py` | Implements `ClaudeCodeRuntime` (`capabilities`, `detect`, `self_loaded_context`, `start`, `events`, `cancel`, `result`) and maintains instance-scoped `auth_state` (`unknown` -> `ok` / `expired`). |
| `bootstrap/runtimes.py` | Registers `"claude_code"` and `"claude-code"` in `RUNTIME_FACTORIES`. |

---

## 2. Config Isolation & Security Invariants (K16, K17, S-55)

1. **Untrusted Worktree Suppression (K16):**
   - Every unattended step passes `--setting-sources user` (never `project` or `local`), suppressing `<worktree>/.claude/settings.json` and `<worktree>/.claude/settings.local.json` hooks and permission allow-rules.
   - `user,project` is emitted exclusively when `policy_profile == "trusted-full-access"`.
   - Step permissions and provider sandbox configuration are written atomically to `<step_dir>/settings.json` (`0600`, outside `request.workdir`) and bound via `--settings <step_dir>/settings.json`.
   - `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` and `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` are unconditionally enforced in child `env` (cannot be overridden by `request.extra_env`).
2. **Isolated Client Home & Credentials:**
   - Under `config_mode = "isolated"`, `HOME` and `CLAUDE_CONFIG_DIR` point to `request.client_home` (`0700`, verified outside `workdir`), and `TMPDIR` points to `<client_home>/tmp`.
   - Host `~/.claude/.credentials.json` is copied to `<client_home>/.credentials.json` (`0600`) only when `copy_credentials = true`. Personal `~/.claude` is never used as a fallback; missing credentials fail closed before process spawn with `ErrorCode.RUNTIME_AUTH_EXPIRED`.
   - `--bare` is strictly prohibited (breaks Claude Code OAuth). `--dangerously-skip-permissions` is prohibited except under `policy_profile == "trusted-full-access"` with explicit host `allow_skip_permissions = true` and a non-`none` isolation profile.
3. **Secret Hygiene (K17):**
   - Assignment prompts travel exclusively over `stdin` (`-p` with stdin payload), never `argv`.
   - `SKM_TOKEN` is registered with `TranscriptWriter` before spawn, passed only in child `env`, referenced in `mcp.json` via `${SKM_TOKEN}`, and redacted from `stream.jsonl`, `stream.stderr`, `TextDelta`, and `ToolRequested.args_preview`.

---

## 3. Lifecycle, Stream-JSON & Usage Verification Matrix

| Invariant / Requirement | Offline Verification (`test_claude_argv.py`) | Live Probe Gate (`test_claude_live_probe.py`) |
|---|---|---|
| Immutable binary identity, `--version` / `--help` timeout retry & 6-tuple cache | Verified (synthetic binary + mutation/timeout cases) | Probe #1 (`test_live_probe_binary_identity_and_launch_signature`) |
| Isolated client home auth & refusal without host `~/.claude` bleed | Verified (`0700` home, `0600` cred copy, missing -> `RUNTIME_AUTH_EXPIRED`) | Probe #2 (`test_live_probe_isolated_auth_and_missing_credentials`) |
| PARITY-03 / K15: native `result` required; exit 0 without `result` -> `RUNTIME_STREAM_INCOMPLETE` | Verified (`stream_basic.jsonl` vs `stream_exit0_no_result.jsonl`) | Probe #3 (`test_live_probe_native_terminal_vs_exit0_without_result`) |
| Tool interception, `--disallowedTools` & secret-free `ToolDenial` hints | Verified (`stream_permission_denied.jsonl` + arg redaction) | Probe #4 (`test_live_probe_tool_interception_and_denial_hints`) |
| Escalated cancellation (`SIGINT` -> `SIGTERM` -> `SIGKILL`) & marker cleanup | Verified (hanging mock CLI + `CliSession` containment) | Probe #5 (`test_live_probe_cancel_escalation_and_containment_cleanup`) |
| Session resume (`--resume <session_ref>`) inside isolated `client_home` | Verified (`stream_resume.jsonl` + persistent argv check) | Probe #6 (`test_live_probe_session_resume_in_isolated_home`) |
| K16 canary hook suppression in `<worktree>/.claude/settings.json` | Verified (`--setting-sources user` + mock CLI canary check) | Probe #7 (`test_live_probe_worktree_settings_hook_canary_suppressed`) |
| Subagent `Task` usage tracking (`SubagentUsage.disclosed = False` until proven) | Verified (`stream_subagent_task.jsonl` + partial `message.id` crash sum) | Probe #8 (`test_live_probe_subagent_usage_disclosure_fact`) |

---

## 4. Capability Status & Live Probe Gate Protocol

- Static declarations in `src/skm/adapters/runtimes/claude_code/capabilities.toml` mark functional capabilities (`headless_execution`, `stream_events`, `session_resume`, `tool_interception`, `usage_reporting`, `native_subagents`, `mcp_support`, `effort_control`, `model_selection`) as `native` and `structured_result` as `adapted` at `tested_runtime_version = "2.1.266"`.
- In accordance with `runtimes §4.3`, the 5 enforcing capabilities (`config_isolation`, `sandbox_native`, `permission_flags`, `workspace_binding`, `reliable_cancellation`) remain `unknown` (`unverified_enforcing`) in `effective_capabilities(...)` until a host-matched `VerificationRecord` with exact `VerificationContext` (`host_id`, `binary_sha256`, `os`, `kernel`, `adapter_version`, `isolation_profile`, `launch_config_digest`) is recorded by the opt-in live probe.
- Default CI and `make check` runs **never** execute the real `claude` CLI binary. Operators execute the live verification gate in a disposable environment via:

```bash
SKM_EVALS=1 uv run --frozen pytest -m evals -q tests/integration/runtimes/test_claude_live_probe.py
```
