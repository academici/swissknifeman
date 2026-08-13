# P5 target design: one audit invocation owns detection and repair

## Evidence chain

Owner intent is preserved in `brief/01-refinements.md`. Current runtime and command behavior is
recorded in `findings/15-P5-audit-fixer-redesign.md`; the earlier candidate design remains in
`research/07-P5.2-candidate-audit-closure-design.md` with its supersession marker.

## Target lifecycle

```text
terminal bounded phase candidate
  → fresh independent audit root
  → replay declared acceptance and inspect committed phase diff
  → cluster findings by root seam
  → repair every safe in-scope seam in this root
  → rerun the original validation and owning generators
  → append exact item repair/terminal evidence through journal owners
  → rebuild item state/status/bundles and phase candidate
  → final same-candidate audit verdict
  → phase close
```

`AUDIT-ROOT-TERMINAL` still applies after the final verdict: the completed audit invocation hands
`plan-close` to a fresh routed root. It no longer forces a separate repair root before that verdict.
RAG:— (repo-grounded: `packages/task/commands/plan-audit.md`, owner refinement).

## Closed classifier

| Class | Audit-root action | Owner-facing successor |
|:--|:--|:--|
| Safe in-scope product defect | Fix, test, commit and rebuild candidate in the same root | none before final verdict |
| Qualified bounded incidental repair | Record `local-repair`, fix and repeat the original carrier | none before final verdict |
| Deterministic generated/bookkeeping drift | Run the owning generator once and recheck | none before final verdict |
| Repeated same fingerprint | Change tactic; after another repeat or material risk use one isolated reviewer return | none before final verdict |
| Out-of-scope non-product observation | Record as non-gating evidence; do not color phase acceptance | `plan-close` after GREEN |
| Authority, safety, or public/frozen-contract change | Materialize the exact DecisionRequest or confirmed block evidence | owner/capability gate only |

Difficulty, number of touched files, test duration, a downstream consumer that has not run yet,
unrelated dirty paths and a first failed tactic are not classes in this table. RAG:—
(owner-grounded: `brief/01-refinements.md`; repo-grounded:
`roadmap/2026.08.11-local-repair-vs-escalation-classifier.md`).

## State and evidence

- The audit root may append existing `in-progress`, `local-repair`, `closed-green` or
  `closed-deviations` results for the owning item under `command=plan-audit`; no parallel handwritten
  state carrier or new terminal status is introduced.
- A blocked item with accepted redesign/resume evidence becomes resumable without pretending the
  historical block never happened. The first audit/exec write appends `in-progress` before product
  mutation and generated state becomes `🟡 In progress`.
- Every repaired item still proves `write-site: pre_mutation: allow · pre_final: allow`, exact
  validation and product/bookkeeping commits. Audit-fixer is not a waiver of the item contract.
- Candidate fingerprint is recomputed after every material repair. The terminal `audit-green`
  binds only the final repaired candidate, so `phase_close_gate()` remains byte-strict.

## P5 producer/consumer split

P5.2 changes Task canonical audit/runtime semantics and runs focused tests that do not require
fresh provider projections. P5.3 immediately consumes that committed producer, updates the EN-only
plan-protocol canon, regenerates Claude/Codex/registry/docs carriers through their owners and runs
the aggregate Task/Skiller validation. P5.3 being not started is `dependency-not-ready`; it cannot
terminalize P5.2. The full phase audit runs only after both items are terminal.

## Acceptance matrix

1. A phase with several `🟠` items enters one audit invocation; all safe in-scope deviations are
   fixed, exact item states are regenerated, a new candidate is built and the final verdict is GREEN.
2. A product finding discovered by audit is fixed and validated without emitting a repair
   launch-block or starting a second audit command.
3. Candidate bytes change after product/spec/state repair; appended audit bookkeeping alone does not.
4. Same-fingerprint recurrence changes tactic and permits at most one isolated reviewer return in
   the same authoritative root; it does not create an owner-facing loop.
5. Public/frozen, authority and safety fixtures remain fail-closed and produce an exact durable
   DecisionRequest/block candidate; mere complexity fixtures cannot do so.
6. A stale P5.3 provider projection is classified `dependency-not-ready` by P5.2 focused closure;
   P5.3 regeneration plus full validation makes the aggregate phase green.
7. `plan-audit` provider projections, methodology and plan-protocol canon carry one meaning; all
   generators and `--check` commands are byte-clean.
