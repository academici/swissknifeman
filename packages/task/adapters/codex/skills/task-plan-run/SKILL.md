---
name: task-plan-run
description: "Only when explicitly invoked. Execute ready Task plan items with plan.py under the current session route."
---

# Task plan-run

Generated Codex adapter for semantic command `task:plan-run`.

- Invocation: `$ task:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/task/commands/plan-run.md`
- Canonical SHA-256: `sha256:b93cfe5909174190d3bc1875f88a76793e573ad43fd4c0d4a2d0825df237bcc2`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
