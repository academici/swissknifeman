# P2 continue-first lifecycle synthesis

## Sources

- `artifacts/source-roadmap/2026.08.11-local-repair-vs-escalation-classifier.md`
- `artifacts/source-roadmap/2026.08.14-validation-repair-without-redesign.md`
- `artifacts/source-roadmap/2026.08.15-checkpoint-repair-without-redesign.md`
- `artifacts/source-roadmap/2026.08.14-agelto-p11-false-terminal-block.md`
- `artifacts/source-roadmap/2026.08.15-empty-producer-ledger-must-continue-first.md`
- `artifacts/source-roadmap/2026.08.16-terminal-phase-reentry-priority-fix-branch.md`
- `artifacts/source-roadmap/2026.08.15-task-plan-archive-brain-independence.md`
- `findings/03-p2-design-baseline.md`

All conclusions below are repository-grounded (`RAG:—`); P2 has no external fact class.

## Vertical decomposition

1. **P2.1 owns the shared repair decision.** `repair-decision/v1` captures the original carrier,
   baseline/candidate evidence, affected paths and attribution, bounded diff, material-surface axes,
   pre/post results and the conditional design question. Its pure reducer returns only
   `repair-in-current-attempt`, `gather-evidence`, `block-candidate` or `design-required`. The last
   outcome is valid only with a decision question, evidence gap, alternatives and expected artifact.
   The existing `block-candidate/v1` remains the separate terminal-boundary review; it cites the
   repair evidence digest instead of reclassifying the signal.
2. **P2.2 makes producer consumption and terminal re-entry typed.** A producer declares one exact
   `producer-readiness/v1` directive in Deliverables. Its terminal journal event carries the
   validated record; bundle generation projects that digest-bound payload to the named consumer.
   Modes are exactly `nonempty-candidates` and `empty-by-decision`; the latter requires an accepted
   owner D# and exclusion proof. Missing/stale output first enters the P2.1 reducer. A separate
   `phase-reentry-justification/v1`, with optional nested `fix-branch/v1`, permits re-open only for
   owner-decision change, irreparable terminal-evidence invalidity, or safety/authority boundary.
   A priority fix targets an already declared item and carries origin, owner, scope, rollback,
   validation and exact resume target; no dynamic hidden item is synthesized.
3. **P2.3 removes an orthogonal false gate.** Archive validates only terminal repository carriers,
   moves the plan, migrates `root/`, repairs links/ACTIVE, appends the terminal event and builds the
   delivery receipt. Brain remains an optional docs sync outside that lifecycle and is never invoked
   by archive.

## Alternatives and ownership

- Prose-only clarification is rejected because the same meaning already existed when three field
  incidents still produced false terminal handoffs.
- Extending `block-candidate/v1` to own repair, redesign, readiness and terminal proof is rejected:
  the reviewer would again receive a preclassified premise and the terminal reducer would become a
  policy grab-bag.
- Separate `validation-repair`, `checkpoint-repair` and `producer-repair` reducers are rejected as
  duplicate policy. One origin enum feeds one repair decision; origin-specific schemas remain only
  where they describe producer output or re-entry state.
- Locale-corpus content and its historical plan are not mutated. The current nonempty ledger proves
  that replaying the old recovery is unnecessary; isolated fixtures preserve the empty scaffold,
  approved no-op and corrupt-output cases without widening P2 into corpus admission work.

D7 owns these choices. `plan_repair.py` owns the generic decision, `plan_readiness.py` owns producer
and re-entry records, `plan_blocking.py` remains terminal confirmation, and command/provider text is
generated from canonical Task and plan-protocol sources.

## Validation economy and stop conditions

Each item starts with its new pure reducer/schema tests, then affected command/lint/projection tests,
then Task validation. Skiller validation runs only where canonical plan-protocol or generated skill
projections change. The phase audit, not each item, owns the one full cross-item integration verdict.

- A qualified repair cannot emit terminal status or a design handoff; the original carrier must be
  rerun and its post-result bound to the same evidence.
- Missing or stale producer evidence is nonterminal until the repair reducer proves a real boundary.
- A closed phase cannot be targeted by design without a valid re-entry record and one closed trigger.
- A priority fix cannot hide work: its target item must already exist and its exact resume target is
  journaled and projected.
- Any public/frozen/security/authority/irreversible change still follows block/decision gates.
- Archive never calls Brain; a nonterminal plan or non-repo Home still fails before mutation.
