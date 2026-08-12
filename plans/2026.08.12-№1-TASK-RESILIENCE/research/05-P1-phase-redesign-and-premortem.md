# P1 phase redesign and pre-mortem — 2026-08-12

## Inputs and owner authority

- `findings/04-layout-v1-migration-results.md` — first-target Routing failure.
- `findings/05-layout-v1-full-fleet-admission-matrix.md` — exact 15-target preview matrix.
- `research/04-P1.2-migration-policy-boundary.md` — phase decomposition recommended over one expanded item.
- `decisions/queue.jsonl` — owner selected `authorize-phase-redesign`; exact action covers plan
  carriers, Task migrator/tooling and the 15 `migration_order` targets.

## Selected decomposition

P1.2 remains the narrow D15 compatibility repair: normalize only comma-list Routing cells into
legal v2 rows. P1.3 owns frozen admission semantics and proves all 15 previews green without
changing any source. P1.4 is the only external-write item: it rechecks source digests, applies
approved previews, rolls back before advancing on failure and produces the zero-live ledger.
P1.5 retires Layout v1 runtime only after that ledger. This keeps policy, external state and
reader deletion independently reviewable while retaining phase-local batch reuse. RAG:—
(repo-grounded: findings/05, D15, owner response).

## Closed transformation invariants

1. Every source tree is archived byte-for-byte with a manifest before projection; Git history is
   additional rollback, not a substitute for the archive.
2. Routing normalization splits only already-legal item/range tokens and never widens runtime
   grammar.
3. Missing or unknown legacy journal history remains verbatim in the source archive. The active
   v2 journal may import canonical current state with provenance, but must not fabricate a
   chronological history.
4. Empty decisions remain empty; noncanonical decision IDs receive an explicit reversible map in
   the migration inventory. Original decision text and identifiers remain in the archive.
5. An empty legacy skeleton phase remains a nonterminal skeleton index; it is not silently marked
   done/skipped and does not receive invented work.
6. Read-budget and handoff carriers are produced from frozen current canon and projected current
   state, not copied stale from v1 and not edited after generation.
7. Apply uses the exact green preview, validates the full preimage digest, writes only the plan
   subtree through staged swap, and restores the preimage on any post-write failure.
8. The applied owner action covers the 15 migration-order targets. Registry deletion or semantic
   repair of invalid candidates outside that list requires an exact durable DecisionRequest.

RAG:— (repo-grounded: findings/05, current migrator/runbook, root worktree/evidence rules).

## Alternatives

- Single expanded P1.2: rejected by the owner's selected `authorize-phase-redesign`; it couples
  syntax, policy, external writes and reader deletion.
- Routing-only repair then retire: rejected because 0/15 previews are green and invalid/unreachable
  roots remain.
- Hand-edit each migrated preview: rejected because generated artifacts have owning tools and
  target-specific patches cannot prove a reusable migration contract.
- Remove or ignore stale/invalid registry entries during migration: rejected unless separately
  authorized; absence from a scanner result is not evidence of quiescence.

## Pre-mortem: «P1 failed after 6–12 months»

| Failure cluster | Early signal | Mitigation / owner |
|:--|:--|:--|
| Resume semantics changed while lint stayed green | migrated status/Next differs from legacy current carrier | P1.3 policy rows assert status/Next/decision invariants; source archive + mapping are mandatory; owner: P1.3 |
| Fleet write overwrote concurrent work | source digest or plan-subtree diff changed after preview | P1.4 full-preimage check, staged swap and rollback before next target; owner: P1.4 |
| Reader removed with a hidden v1 consumer | current registry has unreachable/invalid/v1 row | P1.4 fresh dual-registry inventory must reach zero for all three classes; owner gate for registry/invalid repair |
| Migrator learned target names instead of contracts | `if plan_id` or fixture-only branch appears | defect-class dispatch only, negative mutations and all-15 matrix; owner: P1.3 review |
| Historical evidence became unauditable | normalized journal/decision text has no raw provenance | byte-exact archive and explicit ID/current-state maps; owner: P1.3 |
| Retirement deletes unrelated `v1` schemas | broad string deletion or unrelated tests fail | P1.5 semantic branch search + explicit exclusions + Task/skiller full validation; owner: P1.5 |

The phase fails closed on these signals but uses nonterminal repair/DecisionRequest rather than
claiming terminal `Blocked` without the plan's later P4 confirmation machinery.
