# Integration Target Capabilities Reference

Hand-curated reference of native checkout surfaces, ownership boundaries, hook codecs, resident first-turn budget constants, and scope boundaries across the five `integrations` targets (`antigravity`, `claude_code`, `codex`, `cursor`, `grok`).

For day-to-day commands and operational workflows, see the [Client Integrations Operator Guide](../guides/integrations.md), [CLI reference](cli.md), [Configuration reference](config.md), [Error reference](errors.md), and [Event reference](events.md). Architectural separation from headless execution runtimes is defined in [ADR 0016](../adr/0016-integrations-vs-runtimes.md) and [ADR 0021](../adr/0021-bus-handlers-and-host-operations.md).

## Target Adapters and Verified Client Versions

The adapters expose their capability declarations through `default_target_registry()`.

| Target ID | Adapter / Renderer | `tested_client_version` | `verified_at` | Capability Manifest |
|---|---|---|---|---|
| `antigravity` | `AntigravityTarget` (`antigravity@1`) | `1.5.13` | `2026-11-20` | [Adapter declaration](../../src/skm/adapters/integrations/antigravity/target.py) |
| `claude_code` | `ClaudeCodeTarget` (`claude_code@1`) | `2.1.220` | `2026-08-02` | [`claude_code/capabilities.toml`](../../src/skm/adapters/integrations/claude_code/capabilities.toml) |
| `codex` | `CodexTarget` (`codex@1`) | `0.165.0` | `2026-10-26` | [`codex/capabilities.toml`](../../src/skm/adapters/integrations/codex/capabilities.toml) |
| `cursor` | `CursorTarget` (`cursor@1`) | `2026.09.15-d2fe57e` | `2026-10-26` | [`cursor/capabilities.toml`](../../src/skm/adapters/integrations/cursor/capabilities.toml) |
| `grok` | `GrokTarget` (`grok@1`) | `0.1.0` | `2026-10-26` | [`grok/capabilities.toml`](../../src/skm/adapters/integrations/grok/capabilities.toml) |

## Surface Support Matrix

| Surface | `antigravity` | `claude_code` | `codex` | `cursor` | `grok` | Notes |
|---||---|---|---|---|---|---|
| `instructions` | `native` | `native` | `native` | `native` | `native` | Managed blocks on Claude/Codex; standalone managed rule files on Cursor/Grok. |
| `skills` | `native` | `native` | `native` | `native` | `native` | `.claude/skills/<key>/SKILL.md` on Claude; shared `.agents/skills/<key>/SKILL.md` on Codex/Cursor/Grok. |
| `permissions` | `unsupported` | `native` | `native` | `native` | `native` | Never wider than effective `PermissionSet`; mandatory deny floor always included. |
| `hooks` | `unsupported` | `native` | `native` | `native` | `native` | Invokes `skm-hook <ClientEvent> --target <t> --surface <s> --project <id>`. |
| `mcp` | `unsupported` | `native` | `native` | `native` | `native` | Secret values remain `secret://...` references on disk; plaintext secrets are never materialized. |
| `agents` | `unsupported` | `native` | `native` | `native` | `unsupported` | Grok emits zero agent files and reports info diagnostic `CAPABILITY_UNAVAILABLE` (`surface = "agents"`). |

## Checkout Paths and Ownership Boundaries

Every projected path is governed by an explicit `ManagedBoundary` (`managed_file`, `managed_block`, `merged_json`, or `merged_toml`):

| Target | Surface | Checkout Path | Ownership | Owned Boundary / Keys |
|---|---|---|---|---|
| `antigravity` | `instructions` | `.agents/AGENTS.md` | `managed_block` | `instructions.core`, `instructions.project` |
| `antigravity` | bundle rules | `.agents/rules/<name>.md` | `managed_file` | Whole file with a native rule trigger |
| `antigravity` | `skills` | `.agents/skills/<key>/SKILL.md` (+ `references/*`) | `managed_file` | Shared skill bytes |
| `claude_code` | `instructions` | `CLAUDE.md` | `managed_block` | `instructions.core`, `instructions.project` (+ `bundle.<key>` blocks) |
| `claude_code` | `skills` | `.claude/skills/<key>/SKILL.md` (+ `references/*`) | `managed_file` | Whole file (`skill.toml` is never projected) |
| `claude_code` | `permissions` | `.claude/settings.json` | `merged_json` | `permissions.allow`, `permissions.ask`, `permissions.deny` (`replace`) |
| `claude_code` | `permissions` | `.claude/settings.local.json` | `merged_json` | `permissions.defaultMode` (`replace`: `default` / `acceptEdits` / `bypassPermissions`) |
| `claude_code` | `hooks` | `.claude/settings.json` | `merged_json` | `hooks` (`list_union_tagged` for entries starting with `skm-hook `) |
| `claude_code` | `mcp` | `.mcp.json` | `merged_json` | `mcpServers.<name>` (`replace` per configured server) |
| `claude_code` | `agents` | `.claude/agents/<prefix>-<role>.md` | `managed_file` | Whole file; bundle assets also allow `.claude/{rules,workflows}/*` |
| `codex` | `instructions` | `AGENTS.md` | `managed_block` | `instructions.core`, `instructions.project` (+ `bundle.<key>` blocks) |
| `codex` | `skills` | `.agents/skills/<key>/SKILL.md` (+ `references/*`) | `managed_file` | Shared across Antigravity, Codex, Cursor, and Grok (byte-identical) |
| `codex` | `permissions` | `.codex/config.toml` | `merged_toml` | Top-level `approval_policy`, `sandbox_mode` (`replace`) |
| `codex` | `hooks` | `.codex/hooks.json` | `merged_json` | `hooks` (`list_union_tagged`) |
| `codex` | `mcp` | `.codex/config.toml` | `merged_toml` | Tables `[mcp_servers.<name>]` (`replace`) |
| `codex` | `agents` | `.codex/agents/<prefix>-<role>.toml` | `managed_file` | Whole file; bundle assets also allow `.codex/{rules,workflows}/*` |
| `cursor` | `instructions` | `.cursor/rules/skm-instructions.mdc` | `managed_file` | MDC frontmatter (`alwaysApply: true`) + core/project instructions |
| `cursor` | `skills` | `.agents/skills/<key>/SKILL.md` (+ `references/*`) | `managed_file` | Shared across Antigravity, Codex, Cursor, and Grok (byte-identical) |
| `cursor` | `permissions` | `.cursor/cli.json` | `merged_json` | `permissions.allow`, `permissions.deny` (`replace`; never writes project `approvalMode`/`sandbox`) |
| `cursor` | `permissions` | `.cursor/permissions.json` | `managed_file` | IDE profile allowlists/denylists |
| `cursor` | `hooks` | `.cursor/hooks.json` | `merged_json` | `version` (`replace`), `hooks` (`list_union_tagged`) |
| `cursor` | `mcp` | `.cursor/mcp.json` | `merged_json` | `mcpServers.<name>` (`replace`) |
| `cursor` | `agents` | `.cursor/agents/<prefix>-<role>.md` | `managed_file` | Whole file; bundle assets also allow `.cursor/{rules,workflows}/*` |
| `grok` | `instructions` | `.grok/rules/skm-instructions.md` | `managed_file` | Whole Markdown rule file |
| `grok` | `skills` | `.agents/skills/<key>/SKILL.md` (+ `references/*`) | `managed_file` | Shared across Antigravity, Codex, Cursor, and Grok (byte-identical) |
| `grok` | `permissions` | `.grok/config.toml` | `merged_toml` | Table `[permission]` (`deny` floor; CLI permission mode stays a launch flag) |
| `grok` | `hooks` | `.grok/hooks/skm.json` | `managed_file` | Dedicated SKM hook file alongside unmanaged `.grok/hooks/*.json` |
| `grok` | `mcp` | `.grok/config.toml` | `merged_toml` | Tables `[mcp_servers.<name>]` (`replace`) |
| `grok` | `agents` | — | — | Unsupported in v2.0 (`CAPABILITY_UNAVAILABLE`); bundle assets allow `.grok/{rules,workflows}/*` |

### Shared `.agents/skills/` Invariant and Foreign Content Preservation

- **Shared skills directory**: Antigravity, Codex, Cursor, and Grok project identical bytes, digests, and `managed_file` boundaries under `.agents/skills/*`. Projecting multiple targets in one checkout succeeds when their rendered skill bytes match and fails closed with `INTEGRATION_PATH_COLLISION` on any conflicting boundary or content. Removing one target preserves shared `.agents/skills/*` files while any sibling projection still owns them.
- **Foreign prose, JSON, and TOML**:
  - `managed_block` preserves all text and line endings outside `<!-- skm:begin id=... -->` / `<!-- skm:end id=... -->` byte-for-byte.
  - `merged_json` preserves foreign keys (including explicit `false` values such as `"includeCoAuthoredBy": false`) and keeps user hook entries in order ahead of `skm-hook` entries. JSON with comments (JSONC) is reported as `boundary_invalid` (`INTEGRATION_BOUNDARY_INVALID`) rather than overwritten.
  - `merged_toml` replaces only owned top-level keys and owned `[table]` sections while preserving foreign comments and foreign tables byte-for-byte.
- **Permission profiles**: `integrations.permission_profile` resolves `observe`, `workspace_contained` (default), or `trusted_full_access`. `trusted_full_access` requires host setting `integrations.trusted_full_access.allowed = true`; otherwise resolution narrows to `workspace_contained` with warning diagnostic `INTEGRATION_TRUSTED_REFUSED`. No legacy auto-detection exists.

## Native Hook Surfaces, Event Kinds, and Wire Codecs

Built-in `HookSurfaceId` bindings per target:

| Hook Surface | Class | `claude_code` | `codex` | `cursor` | `grok` |
|---|---|---|---|---|---|
| `lifecycle.git_guardrails` | `enforcement` | `PreToolUse` (`Bash`) | `PreToolUse` (`^Bash$`) | `beforeShellExecution` (`\bgit\b`) | `PreToolUse` (`^Bash$`) |
| `security.safe_dirs` | `enforcement` | `PreToolUse` (`Bash`) | `PreToolUse` (`^Bash$`) | `beforeShellExecution` | `PreToolUse` (`^Bash$`) |
| `lifecycle.plan_guard` | `enforcement` | `PreToolUse` (`Edit\|Write\|MultiEdit`) | `PreToolUse` (`^apply_patch$`) | `preToolUse` (`^(Write\|Delete)$`) | `PreToolUse` (`^apply_patch$`) |
| `lifecycle.pack_guard` | `enforcement` | `PreToolUse` (`Edit\|Write\|MultiEdit\|NotebookEdit`) | `PreToolUse` (`^apply_patch$`) | `preToolUse` (`^(Write\|Delete\|Task\|MCP:.*)$`) | `PreToolUse` (`^apply_patch$`) |
| `lifecycle.changelog_gate` | `enforcement` | `PreToolUse` (`Bash`) | `PreToolUse` (`^Bash$`) | `beforeShellExecution` (`git.*commit`) | `PreToolUse` (`^Bash$`) |
| `lifecycle.review_gate` | `workflow` (`strict` commit = enforcement) | `PreToolUse` (`Bash`), `SubagentStop` | `PreToolUse` (`^Bash$`), `SubagentStop` | `beforeShellExecution` (`git.*commit`), `subagentStop` (`loop_limit=3`) | `PreToolUse` (`^Bash$`), `SubagentStop` |
| `lifecycle.command_log` | `observation` | `PreToolUse` (`Bash`) | `PreToolUse` (`^Bash$`) | `afterShellExecution` | `PreToolUse` (`^Bash$`) |
| `context.session_start` | `workflow` | `SessionStart` | `SessionStart` (`startup\|resume\|clear\|compact`) | `sessionStart` | `SessionStart` (`startup\|resume\|clear\|compact`) |
| `lifecycle.run_report` | `observation` | `SessionEnd` | `SessionEnd` | `sessionEnd` | `SessionEnd` |

Supported `HookEventKind` mappings for host `custom.subscriptions`:

| Normalized `HookEventKind` | `claude_code` | `codex` | `cursor` | `grok` |
|---|---|---|---|---|
| `session_start` | `SessionStart` | `SessionStart` (`startup\|resume\|clear\|compact`) | `sessionStart` | `SessionStart` (`startup\|resume\|clear\|compact`) |
| `session_end` | `SessionEnd` | `SessionEnd` | `sessionEnd` | `SessionEnd` |
| `user_prompt` | `UserPromptSubmit` | `UserPromptSubmit` | unsupported | `UserPromptSubmit` |
| `pre_shell` | `PreToolUse` (`Bash`) | `PreToolUse` (`^Bash$`) | `beforeShellExecution` | `PreToolUse` (`^Bash$`) |
| `post_shell` | unsupported | unsupported | `afterShellExecution` | unsupported |
| `pre_tool` | `PreToolUse` (`Edit\|Write\|MultiEdit\|NotebookEdit`) | `PreToolUse` (`^apply_patch$`) | `preToolUse` (`^(Write\|Delete\|Task\|MCP:.*)$`) | `PreToolUse` (`^apply_patch$`) |
| `post_tool` | `PostToolUse` | `PostToolUse` | unsupported | `PostToolUse` |
| `permission_request` | unsupported | `PermissionRequest` | unsupported | unsupported |
| `subagent_stop` | `SubagentStop` | `SubagentStop` | `subagentStop` (`loop_limit=3`) | `SubagentStop` |
| `stop` | unsupported | `Stop` | `stop` (`loop_limit=3`) | unsupported |

Unsupported host subscription event kinds are omitted from client hook files and surfaced by `skm doctor` via `hooks.event_unsupported`.

### Native Hook Input / Output Wire Protocol

- **Input normalization**: `claude_code` and `codex` send snake_case JSON (`hook_event_name`, `session_id`, `cwd`, `tool_name`, `tool_input`); `cursor` uses camelCase event names (`beforeShellExecution`, `preToolUse`) with snake_case envelope keys (`conversation_id`, `command` or `tool_input`); `grok` uses camelCase payload fields (`hookEventName`, `sessionId`, `toolName`, `toolInput`). Payloads exceeding `1 MiB` or missing mandatory fields fail with `HOOK_PAYLOAD_INVALID` (`deny` for enforcement, `none` for workflow/observation).
- **Decision rendering** (SKM never escalates client permissions):
  - `claude_code`: `deny` and `ask` exit `0` with `hookSpecificOutput.permissionDecision` (`"deny"` or `"ask"`); `context` exits `0` with `hookSpecificOutput.additionalContext`; `allow`/`none` exit `0` with empty stdout.
  - `codex` and `grok`: `deny` writes the reason to stderr and exits `2`; `ask` is unsupported natively and degrades fail-closed to `deny` (exit `2` with `(confirmation required)`); `context` writes `hookSpecificOutput.additionalContext` JSON on stdout with exit `0`; `allow`/`none` exit `0` with empty stdout.
  - `cursor`: `deny` and `ask` exit `0` with `{"permission": "deny"|"ask", "user_message": ..., "agent_message": ...}`; `context` exits `0` with `{"permission": "allow", "agent_message": ...}`; `none`/`allow` emit `{"permission": "allow"}` on gating events (`beforeShellExecution`, `preToolUse`) and empty stdout otherwise.
- **Outage / deadline fail-safe**: When the policy cache is absent/expired and PostgreSQL is unreachable or exceeds `integrations.hook.timeout_ms` (default `2000 ms`), enforcement surfaces (and `lifecycle.review_gate` on `git commit` in `strict` mode) fail closed with `HOOK_BACKEND_UNAVAILABLE`, while workflow and observation surfaces return `none`.

## Cold-Start Baseline and First-Turn Budget Constants

Measured cold-process startup for `.venv/bin/skm-hook` on a warm policy cache (20 fresh processes per target; strict budget **p95 <= 150 ms**; full methodology in [Native hook startup](../measurements/hook-startup.md)):

| Target | Cold `skm-hook` p50 (ms) | Cold `skm-hook` p95 (ms) | Skill Listing Budget Cap | Skill Listing Window Share |
|---|---:|---:|---|---|
| `claude_code` | `128.578` | `143.715` | `1536` chars/entry (`1000000` token window) | `1%` (`0.01`) |
| `codex` | `112.531` | `139.567` | `8000` chars fallback | `2%` (`0.02`) |
| `cursor` | `110.567` | `137.657` | `8000` chars fallback | `2%` (`0.02`) |
| `grok` | `112.342` | `133.514` | `8000` chars fallback | `2%` (`0.02`) |

First-turn budget (`skm budget --target <t>`) evaluates five resident sources (`skills`, `agents`, `instructions`, `hooks`, `mcp`) against `integrations.budget.first_turn.target` (`16000`) and `integrations.budget.first_turn.warn` (`23000`). Missing projected files, unobserved plugin home directories (`include_plugins = true`), or unmeasurable custom `SessionStart` hooks (`run_hooks = false`) yield `tokens = null` (`unknown`) and `verdict = "incomplete"` (`total = null`) without executing hooks or fabricating `0` tokens.

## Telemetry and Planning Scope Boundaries (`ench6`)

- **Session telemetry (`IntegrationTarget.summarize_session`)**: All five target adapters return `None` from `summarize_session(payload, fs)`. Unsupported or unimplemented telemetry never fabricates an empty `"succeeded"` session; `urn:skm:learning:activity-summary:v1` requires explicit `"outcome": "unknown"` and nullable counters when metrics are unavailable. The Claude Code JSONL transcript parser and `learning.record_activity` spool bridge belong to leaf `P13.03.c` and are not claimed ready by `P10.Z`.
- **No implicit plan database writes**: Projecting, auditing, or inspecting a checkout that contains Markdown plan documents or legacy workspace files never writes rows to `skm_planning.*`. Semantic plan creation and legacy import remain explicit `planning`-owned commands.
