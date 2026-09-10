---
id: D7
date: 2026-09-09
status: accepted
item: P2.1
items: [P2.1, P2.2]
supersedes: []
superseded_by: null
---
# D7 — One repair policy before block, redesign and re-entry

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:— (repo-grounded: `research/03-p2-continue-first-lifecycle.md`;
`findings/03-p2-design-baseline.md`)

## Решение

Introduce one closed `repair-decision/v1` record and pure reducer upstream of block confirmation,
redesign and producer repair. Origin-specific producer-readiness and phase-reentry records may add
their own evidence, but they reduce through the same repair action set. Keep `block-candidate/v1` as
the separate terminal-boundary confirmation and bind it to the upstream repair digest. Persist
readiness/re-entry evidence additively in the journal and project producer readiness into the named
consumer bundle; do not add a second handwritten plan map. RAG:— (repo-grounded:
research/03-p2-continue-first-lifecycle.md; findings/03-p2-design-baseline.md).

## Почему

Prose-only guidance did not prevent the PHPStan, checkpoint and test-runner false stops. Separate
validation/checkpoint/producer classifiers would duplicate the same material-surface predicates,
while putting them inside `block-candidate/v1` would let reviewer confirmation bless a mistaken input
classification again. One deterministic upstream decision preserves independent terminal review and
gives lint/delivery one evidence source for forbidding an unjustified `plan-design` handoff.

## Consequences

P2.1 owns the common schema/reducer and forward-only journal/terminal integration. P2.2 owns typed
producer/re-entry evidence and bundle/status/returns projections while reusing P2.1. Existing journal
rows and block capsules remain readable; new terminal events after the implementation cutoff must
carry the new evidence chain. Historical locale-corpus bytes stay unchanged and serve only as
fixtures for generic readiness behavior.
