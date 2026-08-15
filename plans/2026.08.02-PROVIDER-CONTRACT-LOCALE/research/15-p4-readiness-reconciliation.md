# P4 execution-read reconciliation

## Product contract preserved

P4 still produces the same vertical chain: locale runtime → admission tooling → skills → commands/plugins/diagnostics → code prose → docs and terminal regeneration. Frozen P1/P2/P3 contracts, D40/D45 bounded content review, D50 deferred-derived semantics and D61 evidence admission remain unchanged. The redesign changes only routing, mandatory-read topology and stage-aware producer metadata. Source: `findings/24-p4-readiness-preflight-2026-08-15.md`.

## Execution topology

Each item is a separate `manual` plan-run because it ends at a durable producer, rollback or integration boundary. P4.1 owns root/core then Harness and Task slices; P4.2 owns root admission tooling then one Skiller slice; P4.3–P4.6 each own a long bounded ledger whose next item may start only after terminal state. Package mutations still use fresh package cwd sessions under D39; the root coordinator alone owns shared ledger, plan evidence and item close. P4.3–P4.6 contract reviewers remain product evidence and do not turn `Review=none` into another Task-level review loop. RAG:— (repo-grounded: D39, D40, D45, D79 and `roadmap.md`).

## Compact mandatory-read boundary

The executor reads contracts and small topology carriers, not exhaustive data that deterministic code can consume. In P4.1 the complete IANA registry is runtime/checker data: validation binds its approved SHA-256 and adjacent provenance, while the model reads the frozen locale contract, `upstream.json` and normative small fixtures. P4.2 reads only the source/overlay/review contracts, P2 carrier matrix, template/generator seams and current package guide; it does not preload unrelated Harness/Task renderers or a full roadmap already restated by its item contract. Downstream absent paths carry explicit `producer: P4.1` or `producer: P4.2` edges and are named verbatim in the producer Deliverables. RAG:— (repo-grounded: `root/contracts/read-budget-v1.md`, P4 item specs and `findings/24-p4-readiness-preflight-2026-08-15.md`).

## Recovery boundary

The existing P4.1 manifest is reconciled, not deleted or presented as completed work. If its recorded preimages and foreign-diff set still match, resume at the first pending slice; otherwise rebuild only the plan-owned manifest before product mutation. Future dependency absence is `pending-producer`, never a block of P4.1. A frozen contract mismatch, unsafe preimage drift or actual acceptance failure keeps the corresponding item nonterminal and follows the plan's continue-first reducer. RAG:— (repo-grounded: `artifacts/execution/P4.1/manifest.json`, journal P4.1 events, D79 and plan-protocol v2).
