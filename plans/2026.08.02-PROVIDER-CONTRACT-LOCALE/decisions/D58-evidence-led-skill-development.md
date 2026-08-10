---
id: D58
date: 2026-08-10
status: accepted
item: P7.1
items: [P0.1, P2.3, P4.3, P7.1, P7.2, P7.4]
supersedes: []
superseded_by: null
---
## Решение

Skill development uses official provider/specification documentation first, then real Claude Code
and Codex workflow replays, no-skill/minimal/provider-tuned baselines and instruction ablation.
Deterministic unit/schema/golden/generator tests are mandatory regression support but cannot prove
provider discovery, invocation or outcome behavior. Skipped or unavailable live-provider evidence
is not GREEN. RAG:✅ 2026-08-10 official eval guidance in findings/13.

## Почему

Synthetic fixtures are excellent for implementation defects and poor evidence for emergent model
behavior; the plan must measure both without confusing their roles.
