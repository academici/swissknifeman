---
name: task-dev
description: "Only when explicitly invoked. Implement an authorized feature directly, with checks proportionate to risk."
---

# Task dev

Generated Codex adapter for semantic command `task:dev`.

- Invocation: `$ task:dev <arguments>`
- Routing: `implementation/high -> gpt-6-sol/high`
- Canonical source: `packages/task/commands/dev.md`
- Canonical SHA-256: `sha256:4daf4662e3c0502cc714525a38a1468b87bed47b501f80a0d66c1d5ac30444c9`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
