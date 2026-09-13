---
name: task-design
description: "По явному запросу проектирования: проектные артефакты (план / решения / ADR), кода НЕ пишем. frontier/high."
---

# Task design

Generated Codex adapter for semantic command `task:design`.

- Invocation: `$ task:design <arguments>`
- Routing: `frontier/high -> gpt-5.6-sol/high`
- Canonical source: `packages/task/commands/design.md`
- Canonical SHA-256: `sha256:0002f2976b4416042f432f46c44bbcd7f912849f263ddafe6708b0deecd41efa`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `references/intent-routing.md` from the configured Task marketplace runtime before selecting
the workflow. Skill relevance alone is not workflow authority; the latest explicit owner
request determines the work product. Direct development and fixes require no plan lifecycle.

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
