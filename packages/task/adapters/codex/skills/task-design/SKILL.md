---
name: task-design
description: "Explicit design request: produce a plan or ADR; implementation is separate."
---

# Task design

Generated Codex adapter for semantic command `task:design`.

- Invocation: `$ task:design <arguments>`
- Routing: `frontier/high -> gpt-5.6-sol/high`
- Canonical source: `packages/task/commands/design.md`
- Canonical SHA-256: `sha256:3e2215a33373d1403e46b7c083a0d8f9b1ce8f52b203f33db6b75c349e52c0a9`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
