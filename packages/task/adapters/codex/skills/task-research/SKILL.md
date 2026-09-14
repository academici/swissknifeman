---
name: task-research
description: "Research an explicit question using verified sources; return findings and Next."
---

# Task research

Generated Codex adapter for semantic command `task:research`.

- Invocation: `$ task:research <arguments>`
- Routing: `frontier/high -> gpt-5.6-sol/high`
- Canonical source: `packages/task/commands/research.md`
- Canonical SHA-256: `sha256:417b37dbca208f58ec3ca9373736dde751db43be02d2910180377649df631d9b`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
