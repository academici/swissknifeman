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
- Canonical SHA-256: `sha256:9df646c85be25dca0a689708d43f460b3166a67dbef1fc330a5f70414f1d331f`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
