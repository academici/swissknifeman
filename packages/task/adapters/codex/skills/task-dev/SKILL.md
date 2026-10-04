---
name: task-dev
description: "Only when explicitly invoked. Implement an authorized feature directly, with checks proportionate to risk."
---

# Task dev

Generated Codex adapter for semantic command `task:dev`.

- Invocation: `$ task:dev <arguments>`
- Routing: `implementation/high -> gpt-6-sol/high`
- Canonical source: `packages/task/commands/dev.md`
- Canonical SHA-256: `sha256:834fdddee1a8364ae761a0de25bc4cfab9a2100ef5cd5348a92b74b463b0e99e`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
