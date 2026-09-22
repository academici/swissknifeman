---
name: task-research
description: "Only when explicitly invoked. Research an explicit question using verified sources; return findings and Next."
disable-model-invocation: true
---

# Task research

Generated Cursor adapter for semantic command `task:research`.

- Invocation: `task:research <arguments>`
- Routing: `frontier/high -> claude-opus-5-thinking-high/high`
- Canonical source: `packages/task/commands/research.md`
- Canonical SHA-256: `sha256:496ce8ae1b95b6df6c4f25578178abc103713742d8080edf91606597ba7d82c6`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
