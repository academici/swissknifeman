---
name: task-design
description: "Задача ПРОЕКТИРОВАНИЯ: research-fanout + проектные артефакты (план / решения / ADR), кода НЕ пишем. Пинит frontier/high."
---

# Task design

Generated Codex adapter for semantic command `task:design`.

- Invocation: `$ task:design <arguments>`
- Routing: `frontier/high -> gpt-5.6-sol/high`
- Canonical source: `packages/task/commands/design.md`
- Canonical SHA-256: `sha256:2375c5d8d953aa704f9b96aac97bcc3800e6c97f198a0ec86c67fda61b3318ac`
- Runtime projection: `command.md` (generated and provenance-locked; never edit it as source)

Read `command.md` completely and execute it with the invocation payload as `$ARGUMENTS`.
Preserve the semantic command ID, gates, status literals, scope, and validation behavior.
