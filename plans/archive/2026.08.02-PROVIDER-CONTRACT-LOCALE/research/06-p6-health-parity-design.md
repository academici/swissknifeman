# P6 Brain repair and provider-health design

## Inputs and ownership

This design derives from `findings/10-p6-health-control-recon-2026-08-02.md`, the current
Brain observations in `findings/03-current-defects-2026-08-02.md`, the P0 recovery gates, P3
status/reconciliation design, P4 repository acceptance and P5 migration/convergence design.
Terminal producer artifacts remain execution gates; this document does not claim they exist.

P6 composes existing owners instead of creating a universal checker. Skiller owns skill
selection, dependency closure, channels and first-turn budget. Harness owns provider profiles,
trust/security, settings and environment checks. P3 adapters own desired-versus-observed
provider status and readback. P4 owns locale/source acceptance. mAInd owns the sealed fleet loop,
memory/graph/code-graph probes and the aggregate operational report.

## Brain transaction

Brain is one named, protected consumer and one rollback domain. P6.1 first generates a no-write
plan from the sealed P0/P5 identity and current preimages. It may propose only these classes:
credential-containment verification, provider profile/trust reconciliation, dependency-closure
repair, channel/profile normalization and first-turn-budget reduction. The exact action set,
preimages and rollback must receive an Owner D# before apply. The author cannot select between
adding a required dependency and removing its requester, cannot enable full access, and cannot
rotate/revoke a credential on its own.

All writes use the worktree-local public CLIs/P3 reconciliation boundary. Private backups remain
inside the consumer's contract-owned state area. A failed provider readback or budget/dependency
check rolls back the entire Brain transaction; a P0.4 no-op with an unresolved security finding
keeps Brain non-green rather than moving credential work into P6 implicitly.

The restart authority is the D52 hash-chained, append-only Brain WAL, not a derived result file.
Before and after every public write and readback boundary P6.1 appends the stable transaction/action
identity, previous-event hash, plan/approval/source identities, pre/post hashes and backup identity,
then flushes, fsyncs and reopens the complete chain. `resume` first reconciles the first non-terminal
action: an exact postimage continues at readback, an exact preimage is recorded terminal rolled-back,
a recognized partial image rolls back from the named backup, and any third state blocks without a
write. Torn or hash-invalid WAL tails fail closed; derived summaries are emitted only from terminal
verified events.

## Versioned health contract

`provider-health-v1` is a composition contract, not a new provider-status store. Every result is
keyed by sealed project ID, provider ID where applicable, axis/capability ID, desired requirement,
observed evidence identity and stable diagnostic. It preserves explicit `not-selected`,
`unsupported`, `unavailable`, `unresolved` and passing states instead of collapsing absence into
green.

The aggregate is GREEN only when the observed project set exactly equals the sealed P0 set and,
for every required project:

1. desired selection and P3 adapter readback agree for every selected provider;
2. required shared capabilities satisfy the manifest level and provider-specific strengths are
   evaluated against their own declared support, never byte equality;
3. trust/security profile and settings audits pass for each selected provider;
4. skill channels and transitive dependencies are closed, with no required dependency hidden by
   exclusion; the project-specific first-turn policy passes through Skiller's own measurement;
5. required memory/MCP/code-graph and locale/repository-acceptance axes have fresh evidence; and
6. P5 required unresolved/missing/red rows remain non-green.

Unsupported or not-selected capabilities are legal only when desired intent does not require
them. A complete non-green report still completes the evidence item: item status records whether
the scan was produced correctly, while fleet capability maturity/readiness stays in the health
matrix. P7 may release only on a GREEN required aggregate or a later explicit Owner exception
that names consequences; P6 never edits evidence to manufacture GREEN.

## Execution shape and alternatives

P6 is sequential. P6.1 repairs the protected Brain target under an exact owner gate. P6.2 uses
that incident plus frozen P1/P3 semantics to add the recurring package-owned health contract and
CLI. P6.3 consumes both and performs two read-only exact-set fleet scans, emitting a minimized
evidence bundle. A workflow is not declared: the items depend on each other's committed outputs,
and the fleet loop is one deterministic command rather than independent agent work.

| Alternative | Benefit | Why rejected |
|:--|:--|:--|
| Treat `maind health` as fleet health | Existing strict command | It covers one project and only its current memory/MCP/trust axes. |
| Treat `harness doctor --provider-audit` as consumer health | Rich provider matrix | It proves package conformance, not desired selection or consumer readback. |
| Infer health from P5 migrated rows | Reuses rollout output | Migration completion is not current capability, trust, dependency or locale health. |
| Build one monolithic P6 parser over provider files | One apparent source | It duplicates Skiller/Harness/P3 ownership and will drift from their diagnostics. |
| Auto-fix Brain from the finding | Fast | The exact dependency/security/trust choice and external writes require preimage-bound Owner authority. |

## Pre-mortem

| Failure after 6-12 months | Detection/mitigation | Owner |
|:--|:--|:--|
| One green provider masks another missing adapter | exact provider rows and non-masking aggregate | P6.2 contract/tests |
| Fleet membership drifts between scans | sealed P0 set plus locator rebind and exact set difference | P6.3 exporter |
| Brain repair overwrites a local policy or credential | exact preimage, Owner D#, private backup and whole-project rollback | P6.1 executor/Owner |
| Required skill is excluded but warning is lost | machine-readable dependency-closure diagnostic | Skiller changes in P6.2 |
| Package conformance is mistaken for project health | separate evidence classes and project-bound readback | P6.2 contract |
| Health output leaks roots or secrets | minimized schema, forbidden-class self-tests and bundle verifier | P6.3 exporter |
| Green report is stale immediately after migration | two consecutive fresh no-write scans on pinned SKM and contract identities | P6.3 executor |

## Verification

- **RAG:** no new query; the design uses only repository-owned contracts, code and recorded
  observations.
- **Unverified -> repeat pass:** exact terminal contract/API versions and Brain/fleet preimages
  must be rebound at execution. Any mismatch returns to plan-design instead of adding a fallback.
- **Workarounds/[POSSIBLE-DEFECT]:** none. The plan-local P6 evidence exporter is disposable;
  recurring provider-health evaluation and diagnostics remain in package-owned code.
