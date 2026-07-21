# HANDOFF — 2026-07-21 — after P6.1

**Next:** design-item: task:plan-design 2026.07.19-DUAL-PROVIDER P6.1

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | command.filesystem-read · command.git-read |
| Context | cold-start — plan-step |
| Суть | Decide the frozen P5 MCP projection contract needed for P6.1 semantic server descriptors. |

```text
$ task:plan-design 2026.07.19-DUAL-PROVIDER P6.1

РЕЖИМ: remediation
ВХОД: plans/2026.07.19-DUAL-PROVIDER/phases/P6.md → P6.1 escalation; packages/harness/configs/common/mcp/catalog.json and provider bindings
СКОУП: 1) determine whether P5's frozen MCP catalog must gain P6 semantic server IDs and independent Claude/Codex bindings; 2) record the required D#/SemVer and exact Files; 3) preserve mAInd as semantic inventory owner and P5 as renderer
НЕ ТРОГАТЬ: P6.1 package code, P7+, live self-host, FOREMAN, fleet, user-global state, and existing frozen contract semantics without an approved decision
```

**Done:** P6.1 preflight completed with no package-code changes. The effective P5 MCP projection
catalog lacks entries/bindings for the P6.1 mAInd semantic inventory.

**Remaining:** P6.1 needs plan-design remediation before P6.2–P6.6 may proceed. P7+, live
self-host, FOREMAN, fleet and push remain outside authority.

**Sources of truth:** `phases/P6.md` P6.1; frozen P5 harness/artifact contracts;
`artifacts/P5-harness-conformance.md`; `packages/harness/configs/{common,claude-code,codex}/mcp/`.

**Open risks:** P6 is blocked because adding missing provider MCP bindings appears to be a frozen
P5 contract/catalog change outside P6.1 scope. Target plan-lint retains two historical P5 warnings.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: P7+, live self-host, FOREMAN, fleet and push.
- open_questions: whether existing generic `memory` can lawfully represent mAInd without violating P6.1's stable semantic server identity requirement.
