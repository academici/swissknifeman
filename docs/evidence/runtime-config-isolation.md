# Runtime Client Configuration Isolation Evidence (`P08.07.b`)

- **Date:** `2026-11-14`
- **Leaf:** `P08.07.b` — Проверка изоляции клиентских настроек реальных adapters
- **Normative References:** `runtimes §4.3.1`, `runtimes §15`, `adapters §5.11–§5.13`, Invariants `K16`, `K17`, `RT-11`, `S-20`, `S-21`, `S-55`
- **Test Suites:** `tests/contracts/runtimes/test_client_home.py`, `tests/security/test_config_isolation.py`, `tests/fixtures/runtimes/config-isolation/`

---

## 1. Four-Adapter Config Isolation & Capability Matrix

Every built-in runtime adapter declares its static `config_isolation` posture and `[[self_loads]]` inventory in `src/skm/adapters/runtimes/<runtime_id>/capabilities.toml` (validated against `urn:skm:runtimes:capabilities:v1`). Because `config_isolation` belongs to `ENFORCING_CAPABILITIES` (`runtimes §4.3`), `effective_capabilities(...)` **never** treats a static `adapted` or `native` claim—or an offline replay fixture—as host proof: without a fresh `VerificationRecord` matching the exact `VerificationContext`, effective status degrades to `unknown` (`unverified_enforcing`).

| Adapter (`runtime_id`) | Static `config_isolation` | Unverified Effective Status | Isolation Mechanism (`config_mode = "isolated"`) | Unattended Routing Posture |
|---|---|---|---|---|
| `claude_code` (`0.1.0`, target `2.1.266`) | `adapted` | `unknown` (`unverified_enforcing`) until live `VerificationContext` recorded | `HOME` & `CLAUDE_CONFIG_DIR` -> `0700` `client_home`; `TMPDIR` -> `<client_home>/tmp`; `--safe-mode`; `--setting-sources user`; `--settings <step_dir>/settings.json` (`disableAllHooks: true`, `enableAllProjectMcpServers: false`); `--strict-mcp-config`; mandatory `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` & `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` | Admitted when host `VerificationContext` matches (or `config_isolation` explicitly listed in `degraded_allow`) |
| `codex` (`0.1.0`, target `0.165.0`) | `adapted` | `unknown` (`unverified_enforcing`) until live `VerificationContext` recorded | `HOME` & `CODEX_HOME` -> `0700` `client_home`; `TMPDIR` -> `<client_home>/tmp`; strips `CODEX_HOME_USER` & `XDG_*`; writes clean `0600` `<client_home>/config.toml` with step MCP servers only | Admitted when host `VerificationContext` matches; unsuppressible `AGENTS.md` accounted in `runtime_self_loaded` |
| `grok` (`0.1.0`, target `0.1.0`) | `unsupported` | `unsupported` | None in upstream CLI (`~/.grok` and `<worktree>/.grok` discovery cannot be redirected or disabled by flags/env) | **Refused fail-closed** (`CAPABILITY_UNAVAILABLE`, `detail = "project_settings_not_suppressible"`) even under `config_mode = "inherit"` and `degraded_allow`, except under `policy_profile = "trusted-full-access"` with Landlock/container containment |
| `cursor` (`0.1.0`) | `unknown` | `unknown` | Headless execution & config isolation contract unverified in v1 | **Refused fail-closed** in routing and `CursorRuntime.start(...)` (`CAPABILITY_UNAVAILABLE` on `headless_execution`) |

---

## 2. Self-Load Suppression & Manifest Accounting (`runtimes §4.3.1`, `K16`)

1. **Untrusted Worktree Settings Suppression (`K16`):**
   - Across `claude_code` and `codex`, `explain_self_loads(effective_caps, config_mode)` marks `SelfLoadKind.PROJECT_SETTINGS` (`{workdir}/.claude/settings.json`, `settings.local.json`, `{workdir}/.codex/config.toml`) as `active = False, reason = "untrusted_suppressed"` in **both** `"isolated"` and `"inherit"` modes.
   - `claude_code` omits `project` and `local` from `--setting-sources` (`--setting-sources user`) on every profile except `trusted-full-access`.
   - `grok` declares `project_settings` (`{workdir}/.grok`) with `suppressed_by = "never"`, causing `_capability_gate` in `src/skm/modules/runtimes/domain/routing.py` to reject Grok for all non-`trusted-full-access` unattended steps regardless of `runtimes.config_isolation.required` or `degraded_allow`.
2. **Unsuppressible Repo Instructions & Deduplication (`RT-11`):**
   - `codex` reads `<worktree>/AGENTS.md` upwards from `cwd` even when `CODEX_HOME` is isolated (`suppressed_by = "never"`).
   - `explain_self_loads` marks Codex `project_instructions` as `active = True, reason = "cannot_suppress"`; `self_loaded_instruction_files(...)` returns `("AGENTS.md",)` so context assembly excludes duplicating `AGENTS.md` (`reason = "runtime_self_loaded"`), and `CodexRuntime.self_loaded_context(request)` reports `SelfLoadedSource(kind=PROJECT_INSTRUCTIONS, files=("AGENTS.md",), when="start", trust="untrusted")` (schema-valid under `urn:skm:context:command:finalize-manifest:v1`).
   - Verified isolated `claude_code` suppresses `CLAUDE.md` via `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` (`self_loaded_instruction_files(...) == ()`) and suppresses `.claude/skills/**` when `--safe-mode` is active (`ClaudeCodeRuntime.self_loaded_context(request) == ()`).

---

## 3. Isolated `client_home` Lifecycle, Credentials & Host Auth Confinement (`K17`, `S-55`)

- **Directory Layout & Mode (`0700`):** `state_dir/client-homes/<attempt_id>/<runtime_id>` and adapter-specific `writable_home_dirs` (`projects`, `todos`, `statsig`, `debug`, `tmp` for `claude_code`; `sessions`, `cache`, `tmp` for `codex`) are created and chmod-tightened to `0700`, matching `capabilities.toml` declarations.
- **Boundary & Symlink Guards (`S-55`):**
  - `validate_request` refuses `config_mode == "isolated"` without `client_home`, refuses `client_home` lexically inside `workdir` (`client_home_inside_worktree`), and refuses any `PermissionGrant` (`fs_read` / `fs_write`) outside `workdir` (`grant_outside_worktree`) — `client_home` is never exposed as an agent tool grant.
  - `prepare_isolated_client_home` rejects symlinked `client_home`, symlink-escaped parent paths resolving inside `workdir`, symlinked target credentials, and symlinked source `auth.json` (`RUNTIME_INVALID_REQUEST`).
- **Selective `0600` Credential Mounts & Fail-Closed Auth:**
  - When `copy_credentials = true`, only `.credentials.json` (`claude_code`) or `auth.json` (`codex`, supporting `CODEX_HOME_USER`) is atomically copied as `0600`. Personal `settings.json`, `CLAUDE.md`, `config.toml`, `plugins`, and `skills` are never copied.
  - When `copy_credentials = false` or credentials are missing (and no allowlisted `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` or `OPENAI_API_KEY` / `CODEX_API_KEY` is present), the adapter fails closed before spawning with `ErrorCode.RUNTIME_AUTH_EXPIRED` and transitions `auth_state` to `AuthState.EXPIRED` without falling back to host `~/.claude` or `~/.codex`.
- **Attempt Resume & Discard Cleanup:** Multi-step persistent sessions within one `attempt_id` share `client-homes/<attempt_id>/<runtime_id>`, separate attempts receive disjoint directories, and discarding an attempt cleanly removes its `client_home` without touching other attempts or host `user_home`.
- **Secret Hygiene (`K17`) & Landlock Host Auth Protection:** `SKM_TOKEN` is never written to `client_home`, `settings.json`, `mcp.json` (`"${SKM_TOKEN}"`), `config.toml` (`env_vars = ["SKM_TOKEN"]`), `argv`, `repr(request)`, `request_to_json(request)`, or `TranscriptWriter` artifacts. Under Linux Landlock (`ABI >= 3`), wrapped `claude_code`, `codex`, and `grok` processes receive `--no-default-rw` with explicit `--rw` only on `workdir` and `client_home`/`step_tmp`, blocking writes (`EACCES`) to host `~/.claude/.credentials.json`, `~/.codex/auth.json`, and `~/.grok/config.toml`.

---

## 4. Transparent Developer Profile (`executor-transparent`) & Policy Ceiling

- `resources/packs/core/agent-profiles/executor.toml` sets `context.inherit_user_global = false`; `executor-transparent.toml` sets `context.inherit_user_global = true` under `policy_profile = "workspace-contained"`.
- `config_mode_for(profile_inherit, scope_inherit=...)` enforces dual opt-in (`runtimes §4.3.1` rule 1): when `executor-transparent` runs in a scope with default `context.inherit_user_global = false`, it narrows to `"isolated"` and emits `Diagnostic(code="INHERIT_USER_GLOBAL_NARROWED", severity=Severity.WARNING)`.
- When both profile and scope opt in (`"inherit"`), `explain_self_loads` visibly records `user_config` and `plugins` as `active = True, reason = "inherited"`, while `project_settings` remains `untrusted_suppressed` and `compose_effective` preserves every policy ceiling bound (blocking writes outside worktree, `.git/hooks`, unlisted network access, and `git push`).

---

## 5. Offline Canary Suite vs Opt-In Live Probe Protocol (`VerificationContext`)

| Verification Layer | Execution Mode | What It Proves | Capability Promotion |
|---|---|---|---|
| Poisoned Canary Contract & Security Suites (`test_client_home.py`, `test_config_isolation.py`) | Mandatory offline (`make check` / pytest default) | `0700`/`0600` layout, S-55 & symlink rejections, K16 canary hook non-execution on hermetic CLI emulators, Grok/Cursor fail-closed routing, `executor-transparent` narrowing & ceiling, Landlock read-only host auth, `VerificationContext` invalidation (memory & PostgreSQL) | **None** — offline replay never promotes `ENFORCING_CAPABILITIES` from `unknown` |
| Opt-In Live CLI Probe (`@pytest.mark.evals` in `test_config_isolation.py` & `test_claude_live_probe.py`) | Explicit operator opt-in (`SKM_EVALS=1`) | Probes real installed `claude` / `codex` binaries, computes immutable `VerificationContext` (`host_id`, `binary_sha256`, `os`, `kernel`, `adapter_version`, `isolation_profile`, `launch_config_digest`), and verifies live isolated session behavior | Promotes `config_isolation` only for the exact `VerificationContext`; any binary SHA, kernel, profile, host, or launch-digest change invalidates back to `unknown` |

Operators execute the live probe in a disposable environment via:

```bash
SKM_EVALS=1 uv run --frozen pytest -m evals -q tests/security/test_config_isolation.py
```
