---
name: task-plan-run
description: "Only when explicitly invoked. Execute authorized Task plan items under the current session route with inline closure."
---

# Task plan-run

Generated Codex adapter for semantic command `task:plan-run`.

- Invocation: `$ task:plan-run <arguments>`
- Routing: `inherited-plan -> validate the current session against the selected plan item`
- Canonical source: `packages/task/commands/plan-run.md`
- Canonical SHA-256: `sha256:21a20c3b12eb6966dcb6139dc24fa9ab321f52e80cb51ca2820f46618954dd1f`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
