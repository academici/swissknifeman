---
name: task-review
description: "Read-only review of code, docs or specs; rank findings by demonstrated impact."
---

# Task review

Generated Codex adapter for semantic command `task:review`.

- Invocation: `$ task:review <arguments>`
- Routing: `frontier/xhigh -> gpt-5.6-sol/xhigh`
- Canonical source: `packages/task/commands/review.md`
- Canonical SHA-256: `sha256:2a027c9f5d627305927c3ec38525b15858ca2902df082b883ab95b5c367b5c66`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
