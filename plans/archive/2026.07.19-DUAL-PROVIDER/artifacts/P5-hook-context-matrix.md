# P5 hook/context activation matrix

**Item:** P5.3
**Contract:** `provider-harness-contract` v1.0.0 (D85)
**Evidence:** Codex manual `Hooks`, refreshed 2026-07-21 from `/tmp/openai-docs-cache/codex-manual.md` (lines 9144–9600).
**Scope:** generated temp-root artifacts only; no live, global, fleet, FOREMAN, or user configuration target.

| Semantic intent | Claude Code projection | Codex projection | Activation / diagnostic |
|:--|:--|:--|:--|
| `lifecycle.auto-approval` | Existing `PreToolUse` registration and `MODE=off` kill-switch | **Config-native** P5.2 `approval_policy`/`sandbox_mode`; no hook registration | Already projected through P5.2 security config |
| `lifecycle.memory` | Existing global hook plus project membership | Unsupported; no fake `SessionStart` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.notification` | Existing notification hook | Unsupported; no fake `PermissionRequest` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.command-log` | Existing `PreToolUse` Bash hook | Unsupported; no fake `PostToolUse` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.router` | Existing `UserPromptSubmit`/`SessionStart` registrations | Unsupported; no fake `UserPromptSubmit` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.run-report` | Existing `SessionEnd` hook | Unsupported; no fake `Stop` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.pack-guard` | Existing edit/write registration | Unsupported; no fake `PreToolUse` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.changelog-gate` | Existing `PreToolUse` Bash registration | Unsupported; no fake `PreToolUse` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.review-gate` | Existing `SubagentStop` registration | Unsupported; no fake `SubagentStop` handler | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.daemon-safety` | No existing registration | Unsupported; no hidden wrapper | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `lifecycle.git-guardrails` | No existing registration | Unsupported; no hidden wrapper | Required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `context.observer` | P5.7 instruction projection remains separate | **Hook-native** `SessionStart`, `startup|resume|clear|compact`; generated handler emits observer policy | Trusted project and reviewed hook |
| `context.output-style` | Existing `outputStyle` with `off` kill-switch | Explicitly unsupported | Optional diagnostic; required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |
| `context.plans-directory` | Existing `plansDirectory` with `off` kill-switch | Explicitly unsupported | Optional diagnostic; required use blocks with `HARNESS_ACTIVATION_UNSUPPORTED` |

Only hook-native rows are emitted to `.codex/hooks.json`; config-native and unsupported rows
cannot be registered there. The generated `.codex/hooks/lifecycle.py` implements only
`context.observer`, rejects unknown surface IDs and malformed documented `SessionStart` payloads,
and commands resolve from the project git root without copying a Claude command body. Codex project
hooks require trust review; the hook-native kill-switch is `[features].hooks = false`.

## Context-budget verdict

Worktree root and the worktree-local `./packages/skiller/bin/skiller` root were both verified as
`/tmp/swissknifeman-p5.3-repair.2Tq7GQ/worktree`. `./packages/skiller/bin/skiller budget --first-turn`
reported **7,310 tokens — ELEVATED** (target ≤7,000; warn >10,000), so this is below the Owner
warn/over-budget gate. The only new context-facing carrier is `context.observer` through native
`SessionStart`; no description or `additionalContext` carrier was added.

## Focused evidence

`test_provider_hooks.py` proves exact common coverage and support states, config-native/unsupported
non-registration, required/untrusted and required/unsupported failure, payload adaptation, independent
current-Claude registration/kill-switch bytes, and deterministic generated consumer execution for every
rendered hook with unknown/malformed inputs rejected before second check-empty.
