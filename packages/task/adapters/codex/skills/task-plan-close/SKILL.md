---
name: task-plan-close
description: "Only when explicitly invoked. Verify acceptance and close the whole Task plan."
---

# Task plan-close

Generated Codex adapter for semantic command `task:plan-close`.

- Invocation: `$ task:plan-close <arguments>`
- Routing: `implementation/low -> gpt-6-sol/low`
- Canonical source: `packages/task/commands/plan-close.md`
- Canonical SHA-256: `sha256:45ea434f167828404dfdcd036e9b8e490d2a7f2a5226aaadf9dd898836113966`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
