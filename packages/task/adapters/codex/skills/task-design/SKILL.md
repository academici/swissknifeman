---
name: task-design
description: "Only when explicitly invoked. Explicit design request: produce a plan or ADR; implementation is separate."
---

# Task design

Generated Codex adapter for semantic command `task:design`.

- Invocation: `$ task:design <arguments>`
- Routing: `frontier/high -> gpt-6-astra/high`
- Canonical source: `packages/task/commands/design.md`
- Canonical SHA-256: `sha256:9ac07eaa534ec502bded59a27b55e1af5d7b1ba68be508e694072ca2dc65d83f`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Activate only when the owner explicitly invokes this Task command or skill. Task is not an
automatic workflow for development, fixes, design, or a repository containing plans.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
