---
id: D90
date: 2026-08-17
status: accepted
item: P7.4
items: [P7.4, P7.5, P7.6, P7.7]
supersedes: []
superseded_by: null
---
## Решение

Route the P7.4 RED forward through one adjacent local recovery chain P7.5–P7.6, then run one
bounded independent delta audit as the successor P7.7. P7.5 owns the
missing exact acceptance/crosswalk/release-tree interface and a sealed candidate/foreign path
partition. P7.6 owns candidate-only integration and proves that every candidate path equals HEAD
without changing or staging foreign worktree paths. RAG:— (repo-grounded:
`artifacts/P7-final-release-audit.md`, `research/21-p7-audit-red-recovery-design.md`).

The original P7.4 RED, reviewer capsule and external blocker set remain append-only evidence.
F1/F5 stay outside P7 authority under D88/D89. P7.7 may reuse unchanged green
receipts and rerun only the F2–F6 delta plus live exact-set identities; it is not a second whole-plan
audit and cannot issue release authorization while D89's blocker set is non-empty. RAG:—
(repo-grounded: D88, D89 and plan-protocol evidence-reuse boundary).

## Почему

One item per symptom would duplicate reads and manufacture an audit loop. The verifier and candidate
anchor form one producer/consumer chain, while generated plan drift is cheaper and safer to repair
at its owning generator. External rollout/provider access cannot be made executable by adding local
plan prose and therefore remains an explicit authority boundary.

## Consequences

P7 grows from four to seven items. P7.5–P7.6 are one `implementation/high`, `manual`, `Review=none`
batch; P7.7 is the sole bounded successor audit and P7.4 is never reopened. This preserves monotonic
producer ordering while keeping both audit records independent. The plan stays non-releasable, authorizes no tag/push/publish,
and preserves unrelated dirty-worktree bytes. Actor/model provenance: `gpt-5.6-sol/frontier/high`.
