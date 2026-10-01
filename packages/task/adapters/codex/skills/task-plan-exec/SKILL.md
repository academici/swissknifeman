---
name: task-plan-exec
description: "Only when explicitly invoked. Execute authorized Task plan items using declared routing and inline closure."
---

# Task plan-exec

Generated Codex adapter for semantic command `task:plan-exec`.

- Invocation: `$ task:plan-exec <arguments>`
- Routing: `implementation/medium -> gpt-6-sol/medium`
- Canonical source: `packages/task/commands/plan-exec.md`
- Canonical SHA-256: `sha256:4f59377b17e4c4d2d13a578e9c69fa20a86250d29b37814d7aa005f24daae275`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
