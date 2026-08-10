---
id: D7
date: 2026-08-03
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Каждый слайс получает fresh worker, immutable minimal context bundle и capped structured return; полный parent transcript не переносится. RAG:✅ OpenAI/Anthropic subagent docs.

## Почему

Изоляция шума экономит coordinator context; сами subagents не объявляются бесплатными по токенам.
