# P1 execution-economy synthesis

## Sources

- `artifacts/source-roadmap/2026.08.17-task-five-file-read-output-budget.md`
- `artifacts/source-roadmap/2026.08.11-plan-views-history-cli-contract.md`
- `artifacts/source-roadmap/2026.08.11-roadmap-batch-selection-is-authoritative.md`
- `artifacts/source-roadmap/2026.08.15-owner-decision-same-session-continuity.md`
- `findings/02-p1-design-baseline.md`

All conclusions below are repository-grounded (`RAG:—`); P1 carries no external fact class.

## Vertical decomposition

1. **P1.1 completes input acquisition.** A successful transport response is not proof of complete
   context. One content-addressed snapshot with byte-cursor continuation protects both ordinary
   five-file reads and a single-line bundle over the outer output cap. The same slice repairs the
   history CLI/caller mismatch because both outcomes establish complete, executable item evidence.
2. **P1.2 makes the declared execution unit authoritative.** The older roadmap proposed a separate
   `execution-batches` carrier. Current plan-protocol already owns Batch in `plan.md §3 Routing`, and
   `plan_lint_checks.engine` parses and checks it. D6 therefore chooses compiler/admission reuse of
   that carrier; a second JSON map would create drift rather than authority.
3. **P1.3 preserves the admitted work in the right root.** It consumes P1.2's remaining suffix and
   combines it with provider-attested route/context state. The pure controller owns the decision;
   renderers and delivery consume it. Provider UI/final transport is explicitly left to P4 under D5.

## Coupling and order

`plan-exec.md`, `plan-run.md`, `command_render.py`, `task_contract.py`, plan-lint fixtures and the
plan-protocol skill are the P1 coupling hotspot. P1.1 must land first because later admission cannot
trust incomplete inputs. P1.2 lands second because continuity needs authoritative remaining batch.
P1.3 lands last and may reuse the same provider projection/validation setup. One phase-local manual
batch is cheaper than three cold starts while preserving per-item journal, validation and commits.

## Validation economy

Each item runs the narrow unittest modules named in its Validation and then the Task package
validator. Skiller validation is required only because canonical plan-protocol content and generated
registry outputs change. Full root/fleet audits are not repeated inside P1; the phase audit owns the
cross-item integration verdict after the three item receipts exist.

## Stop conditions

- A missing/truncated/digest-mismatched snapshot is a pre-journal typed refusal, not a partial start.
- A request that is not exact batch/solo/receipt-bound suffix is a pre-journal typed refusal.
- A continuity choice without attested inputs or a canonical hard-boundary reason is rejected.
- A new frozen/public contract, external provider write-site or owner authority change is escalated;
  local parser/projection/test drift is repaired in the owning item.
