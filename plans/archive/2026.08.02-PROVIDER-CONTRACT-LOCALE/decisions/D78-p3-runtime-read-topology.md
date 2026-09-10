---
id: D78
date: 2026-08-14
status: accepted
type: design_decision
item: P3.2
items: [P3.2, P3.3]
supersedes: []
superseded_by: null
---
## Решение

P3.2–P3.3 consume frozen semantic contracts plus compact, sealed reconnaissance and policy
carriers. The root coordinator follows D39 and does not preload every package implementation;
each fresh package cwd reads only its declared package slice and returns the closed evidence
record. P3.3 consumes `findings/P0-provider-fleet-baseline.md` and
`research/09-fleet-migration-classification.md`, not the 11.7 MiB per-row fleet corpus. The full
corpus remains the P5 exact-action input. RAG:— (repo-grounded:
`research/14-p3-runtime-read-topology.md`, D39, D42, D72 and frozen P1/P2 contracts).

## Почему

P3 implements finite resolver/adapter/status semantics and package-owned integration seams;
fleet-row processing belongs to P5. Owner-scoped reads preserve cold-start executability while
removing redundant cross-package preload and the demonstrably irrelevant oversized corpus.

## Consequences

P3 execution must preserve every declared package `Files` slice, package validation, readback and
negative isolation gate. A package slice may not treat the compact coordinator bundle as permission
to skip reading its own touched sources. P5 retains the cost and authority boundary of the full
fleet corpus; D78 authorizes no provider, package, consumer, credential or fleet write.
