---
name: planner-design
description: "Only when explicitly invoked. Explicit design request: produce a plan or ADR; implementation is separate."
disable-model-invocation: true
---

# Planner design

Generated Cursor adapter for semantic command `planner:design`.

- Invocation: `planner:design <arguments>`
- Routing: `frontier/high -> claude-opus-5-thinking-high/high`
- Canonical source: `packages/planner/commands/design.md`
- Canonical SHA-256: `sha256:1ea50aa97adbde27580b0c04913c0ed7afd0dba929a8188d3939abba3cac3b6d`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
