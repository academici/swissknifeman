---
name: task-plan-run
description: "Only when explicitly invoked. Run manual Task items under the current attested session route."
---

# Task plan-run

Generated Codex adapter for semantic command `task:plan-run`.

- Invocation: `$ task:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/task/commands/plan-run.md`
- Canonical SHA-256: `sha256:6c420f5f37689d7d76abae710f281ae09fa891a5a86f97ffd9a58c95e682b3cf`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
