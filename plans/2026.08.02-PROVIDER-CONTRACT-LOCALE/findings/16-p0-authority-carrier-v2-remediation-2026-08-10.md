# P0 authority carrier and JIT bundle remediation — 2026-08-10

## Observation

P0.3 and P0.4 still named `plan.md` as the decision-log input after the plan moved to
`Layout: v2`. In v2, immutable authority lives in `decisions/DNN-*.md`; `plan.md` contains
only a pointer to generated decision views, and `decisions/_*.md` files are projections.
Letting the future checker parse either carrier would make an external security mutation depend
on an appendable or generated view instead of the exact accepted authority record.

P0.4's mandatory `bundles/P0.4.json` is currently absent because P0.3 is not terminal and its
declared producer files do not exist. This is the intentional JIT boundary recorded in
`findings/15-remediation-disposition-F26-F30-2026-08-10.md`; generating placeholder inputs or
hashes would violate that boundary. The existing P0.4 Required Reads also named
`artifacts/P0.3/recovery-gates-check.json` twice.

The item admission probe additionally found no plan-local
`root/contracts/read-budget-v1.md` and no declared producer edges for the absent P0.2/P0.3
outputs. Without the contract, D2(a)/D2(b) cannot run; without `(producer: Pn.m)` annotations
and exact producer Deliverables paths, P0.4 is misclassified `ready` instead of
`pending-producer`.

After adding the contract and annotations, `plan-weight item … P0.4 --json` still reports
`admission_state=ready`, `producer_edges=[]` and a missing Bundle v1. The current Task runtime
classifies producer timing only from `required_read` gaps emitted after a bundle is readable,
while Bundle v1 itself refuses absent producer files. That circular pre-materialization boundary is
a Task package defect; this plan-only design pass does not modify package runtime. P0.4 therefore
keeps an independent hard gate on terminal P0.3 plus real producer paths before it invokes bundle
generation, so the incorrect early `ready` label cannot authorize work.

RAG:— (repo-grounded: `plan.md` Layout v2, `packages/task/lib/task/plan_decisions.py`,
`packages/task/lib/task/plan_bundle.py`, P0.3/P0.4 specs, D10/D46/D51/D62 and findings/15).

## Remediation

- P0.3's checker interface resolves exact records from `decisions/` via `--decision-dir` and
  rejects `plan.md` plus generated decision views as authority.
- P0.4 generates and byte-checks its Bundle v1 only after terminal P0.3 and real producer paths;
  an unresolved producer remains `waiting`.
- The no-op branch remains authority-free. A mutation-needed observation without authority stops
  before write and becomes a durable `decision-request` v1. After acceptance, a new P0.4 design
  pass binds exact decision/procedure paths and regenerates the bundle before mutation.
- The duplicate Required Read is removed; the stable D10/D46/D51 and JIT-disposition carriers are
  explicit inputs.
- The unchanged frozen read-budget v1.1.0 contract is materialized plan-locally from
  `2026.08.07-PLAN-ECONOMY`, and P0.2/P0.3 Deliverables plus P0.4 Required Reads expose exact
  producer edges for the corrected runtime to consume. Until the runtime defect is repaired,
  P0.4's own terminal-producer/bundle gate remains the fail-closed carrier.

No provider, fleet, Brain, credential, trust or package state was mutated during this design pass.

## Executable downstream repair

The P0.4 Validation carrier now begins with the exact no-write P0.3 checker `check` invocation.
Its addressed paths include the P0.2 classification and P0.3 checker, contract, action matrix and
evidence, so downstream-gate v1 classifies it `unknown` before those producers exist and executes
it only after the producer commit contains them. The separate P0.4 Bundle v1 generation remains an
item-entry gate after terminal P0.3 state; it is not executed prematurely while P0.1 closes.

This preserves three distinct proofs: downstream producer compatibility, terminal-predecessor
admission, and byte-current P0.4 input bundling. None can substitute for another. RAG:—
(repo-grounded: `packages/task/lib/task/plan_downstream.py`, P0.3/P0.4 Validation and D62).

## P0.1 read-budget refinement

The first generated P0.1 bundle resolved every path but exceeded read-budget v1 because it made
ten package implementation modules mandatory for a read-only observer. P0.1 now consumes the
package AGENTS, public guides and worktree-local launchers as stable interface inputs and observes
behavior through the exact public CLI commands already named by Validation. No package-internal
module is imported or displaced into hidden context. Bundle regeneration plus `plan-weight item`
is the acceptance carrier. The reproducible check is
`python3 packages/task/scripts/plan-weight.py item plans/2026.08.02-PROVIDER-CONTRACT-LOCALE P0.1 --json`;
it must report `admission_state=ready`, `admission_pass=true`, both D2 predicates as true, and no
admission gaps. RAG:— (repo-grounded: `root/contracts/read-budget-v1.md` §§2,5 and P0.1
Scope/Code Guidance).
