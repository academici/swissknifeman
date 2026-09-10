---
id: D60
date: 2026-08-10
status: accepted
item: P6.2
items: [P0.1, P3.3, P6.2, P7.1]
supersedes: []
superseded_by: null
---
## Решение

Every skill/listing/first-turn measurement carries provider, model/version, unit, method,
observation time/expiry, confidence and exact/lower/upper/unknown class. Authoritative provider
counters/replays outrank character heuristics, but even Anthropic token counts remain estimates.
Claude token units and Codex character/listing units never enter one scalar verdict; near-threshold
content decisions require headroom and live replay. RAG:✅ 2026-08-10 Anthropic/OpenAI official
verification plus repository measurement findings in findings/13.

## Почему

This prevents a convenient estimate or one provider's budget from becoming false cross-provider
precision.
