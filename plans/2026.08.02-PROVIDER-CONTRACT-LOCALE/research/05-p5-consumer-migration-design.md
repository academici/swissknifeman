# P5 consumer migration design

## Inputs and boundary

This design derives from `findings/09-p5-consumer-migration-recon-2026-08-02.md`, the P0
classification/recovery specifications, the P3 reconcile/status specifications and the P4
terminal repository acceptance bundle. It does not inspect or reclassify live consumer content.

P5 is a controlled rollout, not another provider implementation. Provider meaning, ownership,
rendering, locks, diagnostics and readback remain in the frozen P1–P4 contracts and public P3
adapters. A plan-local runner may only bind stable project/artifact IDs to current roots, enforce
the sealed action manifest, call those APIs in order, and emit redacted transaction evidence.

## Chosen transaction shape

1. **Freeze without writes.** Rebind every P0 project ID to a current root as a locator only,
   reject identity/preimage drift, compile an exact-set action manifest, exercise it on temporary
   roots, and obtain one Owner D# over immutable action-set IDs.
2. **Preserve first.** For `local-override`, preserve bytes by default and register an override
   only when the frozen P1 contract has an explicit compatible carrier and the approved action
   names it. `ambiguous` is always an unresolved no-op. This phase establishes exclusions before
   any managed repair can run.
3. **Repair non-destructively.** Reconcile approved `canonical-equivalent`, `broken-link` and
   refreshable `stale-managed-copy` rows through the provider-scoped P3 adapters. Each project is
   its own rollback domain; one provider's success never masks the other's failure.
4. **Quarantine, then prove convergence.** Only rows whose sealed action is
   `quarantine-remove` and whose SKM ownership/preimage still match may leave the active path.
   Bytes move to a private per-project rollback area before unlink/removal. A second complete
   observe/diff/readback pass must be a no-op for every migrated row; unresolved rows remain
   explicit and keep aggregate migration readiness non-green.

Every live item uses the same durable append-only carrier,
`artifacts/P5/fleet-transaction-log.jsonl`; the item-level `P5.x-results.json` files are
derived views and never the restart authority. A project/action-set transaction gets one stable
ID derived from the frozen manifest hash, destination item, project ID, ordered action IDs and
source/contract identities. Before the first write the runner appends a canonical `before` event,
flushes it, calls `fsync`, reopens and verifies the hash chain. It then appends the closed states
`applied`, `readback-passed|readback-failed`, and terminal `accepted` or
`rollback-started → rolled-back`; every event carries the previous-event hash, ordinal, exact
pre/post hashes, backup/rollback identity and frozen action/source identities. Acceptance is
atomic at the project transaction: an aggregate may count no action until every selected provider
row has fresh readback and the terminal `accepted` event is durable.

Restart is deterministic. Validate the whole schema/hash chain and frozen identities, select the
first non-terminal transaction in manifest order, then observe without writing. Exact planned
postimage plus valid backup/source identities permits a fresh public readback and `accepted`;
`readback-failed`/`rollback-started` or any exact partial planned postimage requires rollback and
exact preimage verification before `rolled-back`; an exact preimage is reconciled as rolled back.
Any third state, changed source/action set, missing backup, ambiguous mixed image or chain defect
refuses the remaining rollout. Already `accepted` rows are re-read and never replayed; already
`rolled-back` rows remain explicit unresolved outcomes. No restart cursor may skip the first
non-terminal or drifted transaction.

The action vocabulary is closed: `no-op-unresolved`, `preserve`, `register-override`,
`relink`, `refresh-managed`, and `quarantine-remove`. Classification does not imply action:
P0.2 supplies a proposed disposition, P5.1 validates it against the frozen gates, and only the
Owner D# authorizes the immutable action-set IDs.

## Alternatives rejected

| Alternative | Benefit | Why rejected |
|:--|:--|:--|
| Run `skiller update --all` directly | Existing fleet loop | It does not consume the sealed P0 action matrix and may perform adoption or legacy-link cleanup under package-local discovery. |
| Run generic `maind sync --all` as the migration contract | Existing project/provisioner fan-out | It is deliberately fail-soft and provisioner-oriented; it does not freeze per-artifact P0 classification, action or rollback authority. |
| Execute ad-hoc commands project by project | Simple local reasoning | No exact-set coverage, immutable approval carrier, protected-project delta or reproducible second-run proof. |
| Put provider semantics in a P5 helper | One apparent place to migrate | Duplicates P3 adapters/locks and will drift; the helper is limited to transaction sequencing and evidence. |

## Failure model and mitigations

| Failure | Detection before write | Required result |
|:--|:--|:--|
| Registry path now points to another repository | stable ID + repository identity + preimage mismatch | refuse that project before observation/apply |
| Local override is mistaken for managed drift | class/action contradiction or exclusion-set miss | refuse the whole action set; preserve bytes |
| Claude succeeds and Codex fails | independent provider readback rows | rollback the current project; aggregate remains non-green |
| A crash occurs after project apply/readback but before aggregate results | fsync'd hash-chained `before/applied/readback/accepted-or-rolled-back` events plus deterministic reconcile | prior accepted/rolled-back projects remain explicit; the first non-terminal project is reconciled before any later action; no fleet-wide GREEN |
| Cleanup destroys recoverable content | ownership/preimage gate + private quarantine | rollback before proceeding; no irreversible delete |
| Source or contracts change mid-rollout | pinned item commits/contract versions/source identities | refuse the remaining action set and return to plan-design |
| Evidence leaks roots or secrets | redacted schema/self-tests | refuse evidence commit; private backups stay outside plan artifacts |

## Orchestration verdict

P5 does not declare a workflow. Its four items are sequential: approval depends on the no-write
manifest; managed repair depends on preservation exclusions; cleanup depends on successful
repair; convergence depends on all earlier results. Live external state and owner gates also make
an unattended fan-out inappropriate. Every item is `manual` with full review.

## Verification

- **RAG:** no new query; all new decisions are repo/plan-grounded in the P0/P3 contracts and
  `findings/09-p5-consumer-migration-recon-2026-08-02.md`.
- **Unverified → repeat pass:** terminal P0/P3/P4 artifact versions and public function/CLI names
  must be rebound from their committed Completion Notes before P5 execution; a mismatch blocks.
- **Workarounds/[POSSIBLE-DEFECT]:** none. The plan-local runner is explicitly non-semantic and
  may be discarded with the archived plan after P7; recurring product behavior remains in P3
  adapters and mAInd package-owned fleet orchestration.
