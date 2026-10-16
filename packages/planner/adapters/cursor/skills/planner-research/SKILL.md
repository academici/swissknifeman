---
name: planner-research
description: "Only when explicitly invoked. Research an explicit question using verified sources; return findings and Next."
disable-model-invocation: true
---

# Planner research

Generated Cursor adapter for semantic command `planner:research`.

- Invocation: `planner:research <arguments>`
- Routing: `frontier/high -> claude-opus-5-thinking-high/high`
- Canonical source: `packages/planner/commands/research.md`
- Canonical SHA-256: `sha256:6080f825740c10cc28214b86cafadf3ceb3e1fd48079996f8aa6634ceb18e2c8`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
