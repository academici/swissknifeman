---
id: D3
date: 2026-09-09
status: accepted
item: P6.1
items: [P6.1, P6.2, P6.3, P6.4]
supersedes: []
superseded_by: null
---
# D3 — Measure Codex instruction value before reduction

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:✅ 2026-09-09 official OpenAI sources in `findings/01-codex-instruction-baseline.md`

## Решение

P6 performs a native cold-start source probe, then matched baseline/no-skill/explicit/implicit and
AGENTS variants over a fixed 10–20 prompt suite. Retain or change a carrier only from marginal
quality, token, wall-time and restart evidence. Target skill listing is at most 8,000 characters;
accept a reduction only if required invariants remain 100%, extra restarts remain zero, and median
input improves by at least 10% or 1,000 tokens beyond observed variance across 3–5 runs per arm.

## Почему

Progressive disclosure means body size alone is not resident cost, and official guidance supports
audit/eval rather than blanket deletion.

**Consequences:** no deletion before P6.1; ambiguous results preserve current behavior and record a
smaller follow-up hypothesis rather than forcing churn.
