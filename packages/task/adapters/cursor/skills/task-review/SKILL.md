---
name: task-review
description: "Read-only review of code, docs or specs; rank findings by demonstrated impact."
---

# Task review

Generated Cursor adapter for semantic command `task:review`.

- Invocation: `task:review <arguments>`
- Routing: `frontier/xhigh -> claude-opus-5-thinking-high/xhigh`
- Canonical source: `packages/task/commands/review.md`
- Canonical SHA-256: `sha256:2a027c9f5d627305927c3ec38525b15858ca2902df082b883ab95b5c367b5c66`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
