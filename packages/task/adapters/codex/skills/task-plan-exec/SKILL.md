---
name: task-plan-exec
description: "Only when explicitly invoked. Execute authorized Task plan items using declared routing and inline closure."
---

# Task plan-exec

Generated Codex adapter for semantic command `task:plan-exec`.

- Invocation: `$ task:plan-exec <arguments>`
- Routing: `implementation/medium -> gpt-5.6-terra/medium`
- Canonical source: `packages/task/commands/plan-exec.md`
- Canonical SHA-256: `sha256:6ae5cf6c1db923a06372e0288222be13f94e4810b08c115838027b18d54ca111`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
