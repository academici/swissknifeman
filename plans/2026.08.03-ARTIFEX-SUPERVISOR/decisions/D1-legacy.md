---
id: D1
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Artifex v1 проектируется как внешний durable supervisor, а не named Workflow, agent-pack orchestrator или длинная parent-agent сессия. RAG:✅ current OpenAI/Anthropic long-horizon and subagent docs; repo-grounded current Harness inspection.

## Почему

Workflow повторно раздувает coordinator context и не владеет durable execution state; живой `_common.orchestrator` только планирует для main session.
