---
name: task-review
description: "Only when explicitly invoked. Read-only review of code, docs or specs; rank findings by demonstrated impact."
disable-model-invocation: true
---

# Task review

Generated Cursor adapter for semantic command `task:review`.

- Invocation: `task:review <arguments>`
- Routing: `frontier/xhigh -> claude-opus-5-thinking-high/xhigh`
- Canonical source: `packages/task/commands/review.md`
- Canonical SHA-256: `sha256:541d71ed58c765e34d50dcde3ca6ccc62d60e677fb1423fcfd0f1e172b2fa9ab`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as the user prompt.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
