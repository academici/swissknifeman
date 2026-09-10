---
id: D57
date: 2026-08-10
status: accepted
item: P1.2
items: [P1.2, P3.2, P6.2, P7.1]
supersedes: []
superseded_by: null
---
## Решение

Claude Code and Codex skill projections are additive adapters over one immutable Skill Core. Each
adapter owns discovery, invocation mapping, target paths, measurement and replay fixtures. A third
provider joins through the same descriptor/renderer/capability/meter/replay seams and may tune its
own adapter without editing existing adapters or forking shared skill meaning. Provider parity is
semantic and provider-qualified, not byte parity. RAG:✅ 2026-08-10 Agent Skills, Anthropic and
OpenAI official verification in findings/13.

## Почему

This keeps current provider strengths available without hard-coding their quirks into canonical
content or making the next provider a cross-cutting rewrite.
