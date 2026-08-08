# Read Path Contract v1

Status: frozen by D127 after the `P1.5` owner gate (2026-08-08).

Machine-readable paths, slot resolvers, section order, and predicates:
[`read-path-v1.spec.json`](read-path-v1.spec.json). The JSON is the sole source of slot rows; this
document defines semantics and transition rules without duplicating those rows.

## Authority and versioned transition

The path specification is the single source of truth for mandatory reading. Command prose is a
generated projection and P6 must protect it with a literal conformance test, following the existing
`test_canon_literals.py` precedent. A command cannot add an informal “read if useful” slot.

The specification carries both layouts during transition. Layout `v1` preserves the current
`plan-exec.md` §1 order literally: selected plan sections, full handoff, current phase file containing
Phase Context plus the selected item, then that item's Required Reads in declared order. Layout `v2`
is the reader-specific carrier path. The compatibility descriptor is retired only when P6 switches
all command projections; until then a resolver chooses the layout from plan metadata, not by asking
the operator.

The contract determines what is read and in what order. It does not override `## 3. Routing`, select
the item, or authorize execution.

## Executor path and deterministic resolution

The target executor path contains exactly five slots: stable plan core, current phase context,
selected item specification, declared input bundle, and volatile item-state projection. The item id
from the command deterministically supplies `<Pn.m>` and its phase `<Pn>`; carrier templates then
resolve exact paths. Bundle order supplies exact digest-qualified input units. A unit is either a
whole file or a section/symbol slice that the item declaration names explicitly; inferred slices,
unanchored ranges, or content moved outside the measured bundle are forbidden. The bundle schema is
owned by P3, but it must bind both the source bytes and the selected bytes. Missing, ambiguous,
stale, or schema-invalid resolution fails closed.

The plan-core slot contains identity, Context, Execution Rules, and `## 3. Routing`. Routing stays in
this first slot under D22, so the gate runs before phase detail, inputs, or state. The specification
does not project or reinterpret a resolved route.

The phase-context resolver admits only the current non-terminal phase derived from the selected item.
Once a phase is terminal it leaves the live executor path; its closure and attempts are addressable
through audit/history carriers. P2.4 implements the physical transition, but this rule already makes
the desired resolution unambiguous.

## Handoff removal and state replacement

`handoff.md` is absent from the mandatory executor path under D26. It remains the owner's cold-start
carrier. The rejected alternative was to leave it as the last executor slot: that would still expose
plan-wide risks and next actions while the item-state projection must already carry the selected
item's executable next step, active risks, and active workarounds. Reading both would pay twice and
create conflicting current-state views.

The item-state contract therefore carries the executor-relevant subset, and its freshness gate is
fail-closed. Address selection comes from the command argument, not from handoff prose.

## Paths for designer, auditor, and owner

The designer path includes stable plan and item specifications plus the scoped knowledge layers:
`brief/`, phase research, and phase findings. Current decision and status views follow stable inputs.
The auditor path adds primary journal/decision evidence and the on-demand history view. The owner
path leads from stable identity and brief through open questions, roadmap, decision/phase views, and
only then volatile status, state, and handoff. Each slot has one resolver in the adjacent JSON and
uses a carrier id from the reader registry.

The paths express reader rights from `reader-contract-v1`; they do not grant write ownership.

The machine specification also declares two profiles of the existing `auditor`. `scoped-review`
resolves only caller-linked carrier instances and has `control: return-to-root`; it deliberately
does not define the evidence capsule owned by P4.5/P6.3. `full-audit` references the complete
auditor path. Both profiles return a bounded verdict to the existing root run and never create a
fifth reader or transfer ownership of that run.

Every registry carrier is addressable from at least one reader path or explicitly superseded.
`index` and `artifacts` are optional slow inputs on the designer/auditor/owner paths; they remain
absent from the executor path unless an exact artifact is declared through that item's bundle.

## Monotonic volatility predicate

Volatility ranks are `stable < slow < volatile`. For every reader path, registry volatility must be
monotonically nondecreasing by slot order. Within every multi-section carrier, the section order in
the specification must obey the same predicate. This is a machine condition, not a recommendation
(D27).

The current layout violates the condition: `plan.md` begins with `## 0. Meta`, where `Version`,
`Status`, and `Last Updated` change on item closure, before stable Context and Execution Rules. P2
must leave immutable identity (`Plan ID`, `Title`, `Repository`, `Document Type`, `Home`) at the top
and move those mutable Meta fields down or into a generated status view. Naming Meta and its fields
here is a direct consequence of the predicate, not an independent formatting preference.

Exact-prefix cache invalidation gives the ordering operational force: an early volatile byte
invalidates every later cache boundary. D8 establishes that the primary benefit is context capacity
and quality/correctness, while cache economics are secondary.

## Boundaries and failure behavior

The bundle schema and builder belong to P3, carrier migration to P2, command projection and literal
tests to P6, and the numerical budget to P0/P1.5. A resolver cannot compensate for a missing bundle
by scanning directories, cannot keep a terminal phase “for context,” and cannot put a history-class
carrier on the executor path. Such cases fail closed with the slot and carrier id named.

D8, D25, D26, D27, and D36 govern this contract.
