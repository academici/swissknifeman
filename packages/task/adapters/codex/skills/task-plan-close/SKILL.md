---
name: task-plan-close
description: "Only when explicitly invoked. Close or archive Task plan work with plan.py; ordinary execution already closes inline."
---

# Task plan-close

Generated Codex adapter for semantic command `task:plan-close`.

- Invocation: `$ task:plan-close <arguments>`
- Routing: `implementation/low -> gpt-6-sol/low`
- Canonical source: `packages/task/commands/plan-close.md`
- Canonical SHA-256: `sha256:378a74d26f851ad5534071e9f6ea8a182996462c7f79650f769ba22ea92e858e`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
