---
name: task-design
description: "Only when explicitly invoked. Explicit design request: produce a plan or ADR; implementation is separate."
disable-model-invocation: true
---

# Task design

Generated Cursor adapter for semantic command `task:design`.

- Invocation: `task:design <arguments>`
- Routing: `frontier/high -> claude-opus-5-thinking-high/high`
- Canonical source: `packages/task/commands/design.md`
- Canonical SHA-256: `sha256:06f407bd9341ea0fe1973a9f857e2c529e457fe6cbf325b0a64c59c30d12d3c1`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
