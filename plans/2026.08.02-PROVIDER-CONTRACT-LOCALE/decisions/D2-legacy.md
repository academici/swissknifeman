---
id: D2
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

Locale precedence is command/session → environment → project → user → built-in `en`; `response`, `plan`, and `diagnostics` resolve independently. RAG:— (internal product rule grounded in `brief/00-brief.md` and synthesized in `research/02-p2-locale-authoring-design.md`).

## Почему

Makes a one-off Russian plan possible without changing default response language; no external standard is claimed to prescribe this precedence.
