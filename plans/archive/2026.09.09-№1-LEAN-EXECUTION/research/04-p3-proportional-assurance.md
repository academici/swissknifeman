# P3 proportional assurance synthesis

## Sources

- `artifacts/source-roadmap/2026.08.14-phase-assurance-contract.md`
- `artifacts/source-roadmap/2026.08.14-phase-close-impact-broker.md`
- `artifacts/source-roadmap/2026.08.14-repeat-audit-evidence-reuse-budget.md`
- `artifacts/source-roadmap/2026.08.14-task-phase-close-fast-path.md`
- `artifacts/source-roadmap/2026.08.14-insiders-p6-routing-candidate-repro.md`
- `artifacts/source-roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md`
- `findings/04-p3-design-baseline.md`

All conclusions below are repository-grounded (`RAG:—`); P3 has no external fact class.

## Vertical decomposition

1. **P3.1 owns semantic assurance and impact selection.** A handwritten `Phase Assurance | v1`
   block records impact, named seams, live/irreversible state and audit intent before execution. A
   pure broker combines it with the runtime-built candidate and a field-level `audit-impact/v1` to
   choose direct close, first audit, `gate-rebind`, `delta`, justified `full`, evidence gathering or
   owner review. `Review` remains item-review depth and item count is not a risk proxy.
2. **P3.2 removes parser ambiguity at the source.** The phase-policy consumer reads the normalized
   executable Routing table produced by the P1.2/D6 compiler path. It stops after that table and
   rejects duplicate/ambiguous executable tables while ignoring later non-routing tables. No new
   regex/table parser or provider selector map is introduced.
3. **P3.3 makes item validation reusable.** `validation-receipt/v2` binds the canonical command,
   item spec, product/input/tool/route/projection identities, evidence, risk class and duration.
   Deterministic unchanged receipts may be reused; live/security/external receipts run at their
   declared boundary. A lineage budget permits one baseline full, a second only from a closed broad
   material justification, and a third only by owner decision.
4. **P3.4 closes the topology.** The evidence graph distinguishes spec, product and closure anchors,
   detects `Files ∩ digest_inputs` collisions before mutation, proves product byte identity through
   closure, and maps changed nodes to a bounded downstream closure. Audit finalization regenerates
   its own carriers, rebuilds the candidate and proves close admission before GREEN.

## Alternatives and ownership

- Always rerun every item Validation is rejected because it discards terminal item decomposition
  and reproduced at least 2,557 package cases across three P0 audits without a new product
  hypothesis.
- A numeric-only threshold is rejected as the policy owner: one central frozen contract may matter
  more than many independent documentation items. The 50% closure threshold remains one
  conservative signal inside a field-level broker.
- Automatic `full` on unknown impact is rejected. Unknown means gather evidence or owner review;
  fail-closed forbids close but does not authorize the most expensive action.
- A second handwritten phase risk/evidence map is rejected. Phase Context owns semantic assurance,
  item events own validation receipts, the runtime candidate owns material identity, and the graph
  derives edges from declared carriers.

D8 owns this split and its forward compatibility. P3.1 owns assurance/impact policy, P3.2 consumes
the D6 routing compiler, P3.3 owns receipt validity/reuse, and P3.4 owns anchor topology and final
close continuity.

## Coupling and order

`plan_gates.py`, `terminal_policy.py`, `plan_item_state.py`, `plan_downstream.py`, journal/lint,
Task commands and canonical plan-protocol text are the P3 coupling hotspot. P3.1 establishes the
closed policy vocabulary; P3.2 makes its Routing input deterministic; P3.3 supplies trustworthy
item evidence; P3.4 then compiles exact invalidation and finalization over those contracts. One
phase-local manual batch avoids reloading the same incident fixtures and provider projection setup
while retaining item-level commits and validations.

## Validation economy and stop conditions

Each item runs its focused pure/schema tests first, then affected command/lint/provider parity tests,
then Task validation. Skiller validation runs only because canonical plan-protocol content and
generated projections change. The phase audit owns one full cross-item integration baseline; item
work does not repeat it.

- Missing or invalid assurance refuses close with a named reason; it never silently schedules full.
- A second table cannot erase a valid executable Routing table, and duplicate executable tables fail
  closed.
- A receipt with changed spec/product/input/tool/route identity is not reused; live evidence is
  always rerun at its boundary.
- A second full requires durable broad-impact justification; a third requires an owner decision.
- Self-invalidating input/write topology fails before product mutation with an exact anchor split.
- Audit GREEN is illegal until post-audit regeneration and rebound candidate both admit the exact
  close continuation.
