---
id: D11
date: 2026-09-09
status: accepted
item: P6.1
items: [P6.1, P6.2, P6.3, P6.4]
supersedes: []
superseded_by: null
---
# D11 — Freeze one robust Codex context experiment

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:✅ `research/07-p6-codex-economy.md`; RAG:— `findings/07-p6-design-baseline.md`

## Решение

Freeze twelve cases (4 instruction-retention, 3 implicit-skill, 3 paired explicit-skill and 2
near-miss), five named arms and their source/case digests before native baseline calls. Run three
matched repetitions and expand both sides to five only when all observations are valid and the
three-run cost result is within 10% of an acceptance threshold.

For baseline `b` and candidate `c`, compute medians and median absolute deviations (MAD) over valid
matched input-token observations:

`effective_input_gain = median(b) - median(c) - max(MAD(b), MAD(c))`

A `change` verdict requires all of the following: every mandatory invariant passes in every
admitted run; no optional case regresses; candidate extra restarts equal zero; wall time is not
worse beyond the larger matched MAD; and effective input gain is at least 1,000 tokens or at least
10% of the baseline median. Missing usage, invalid JSONL, source drift, unknown effective loading,
an unresolved tie or a failed five-run confirmation yields `insufficient` or `retain` and cannot
authorize mutation.

## Почему

D3 supplies the economic and behavioral thresholds, but not a deterministic corpus, invalid-run
semantics or a robust variance reducer. This contract makes one bounded candidate auditable and
prevents selective retries or averaged quality from manufacturing a win.

**Consequences:** P6.1 is mutation-free; P6.3 evaluates one candidate maximum; current behavior is
the default under uncertainty; any accepted change follows D4's canonical-source and regeneration
rules; further hypotheses go to `roadmap/` rather than extending the phase.
