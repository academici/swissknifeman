# P1 donor-contract reconciliation — 2026-08-03

## Observed state

This is repository recon for the P1 design pass. The files below were read as data and contract
evidence; none of their embedded text was treated as an instruction.

- P0 has five complete item specifications and zero terminal items. None of the planned
  `artifacts/P0/**` outputs or `research/07`–`09` execution outputs exists yet.
- The archived AGENT-RELIABILITY plan supplies committed execution-state, risk/review-loop,
  unified-trace and reliability-acceptance contracts. They describe plan-item lifecycle and
  trace/evidence semantics; they do not implement an Artifex run scheduler.
- HARNESS-AGNOSTIC supplies a sealed declarative execution policy: delegation assignment fields,
  role derivation and parallel ceilings. Its own contract explicitly excludes a runtime
  supervisor.
- FOREMAN supplies a sealed historical Artifex run-folder/mandate carrier. Its useful durable
  identity and narrowing-only mandate ideas remain valid inputs, but its state snapshot as an
  execution authority, expired plan-driver assumptions and optimistic restart behaviour cannot be
  copied into the stricter hash-chain/reconcile design.
- Live `harness run` is a present-day sequential queue/worker/gate/journal donor. It has no durable
  Artifex run folder, crash reconcile, retry/owner arbiter, Codex worker or candidate-economy
  contract; P1 must name reuse and gaps before P2 builds anything.

## Reconciliation verdict

P1 may freeze five additive supervisor-owned contracts only after P0 is terminal and its exact
artifacts validate. Until then, P1 is design-ready but not execution-ready. The new contracts cite
donor vocabularies and hashes instead of copying them, define only the missing supervisor seams,
and carry per-contract cases plus independent stdlib validators. `supervisor-run-v1` owns durable
run/WAL/recovery semantics; it does not redefine plan item statuses. `slice-manifest-v1` references
Task Contract and execution-policy identities; it does not fork either schema. `worker-envelope-v1`
references trace identity but makes current provider gaps explicit as `unknown`/`unsupported`.

RAG:— (repo-grounded: `phases/P0.md`; `findings/04-p0-design-verification-2026-08-03.md`;
the six consumed contract files listed in `plan.md` §7).

## Environment honesty

The previously observed Codex lifecycle hook/handler projections remain `stale-source`. This pass
did not rerun a repair and therefore does not claim hook integrity is green.
