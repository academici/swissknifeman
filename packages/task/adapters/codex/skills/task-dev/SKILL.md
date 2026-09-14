---
name: task-dev
description: "Implement an authorized feature directly, with checks proportionate to risk."
---

# Task dev

Generated Codex adapter for semantic command `task:dev`.

- Invocation: `$ task:dev <arguments>`
- Routing: `implementation/high -> gpt-5.6-terra/high`
- Canonical source: `packages/task/commands/dev.md`
- Canonical SHA-256: `sha256:80eca26ed89d46495b3a7487b28849d5f2728c41d7b19f305c6fc117a7433cef`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
