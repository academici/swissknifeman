---
disable-model-invocation: true
description: "Read-only Task design or phase audit; phase audit needs owner-bound consent."
argument-hint: "<PLAN-ID> <Pn|design> --reviewer <provider/model> [--effort xhigh]"
---
Invocation payload: `$ARGUMENTS`.

Require an explicit `--reviewer <provider>/<exact-model-id>` and use a fresh non-executor
session whose captured provider/model matches it; effort defaults to `xhigh`. Native frontmatter
does not pin a model/effort; compatibility routing minima do not replace the selected reviewer.
On mismatch render the selected review launch and do not audit under another route.
Historical audit evidence remains readable. This argument never grants phase-audit consent.
Optional `/context` and `/effort` suffixes may follow the model, in either order, with a trailing `/`.
Examples: `grok/grok-4.7/500k/`, `grok/grok-4.7/xhigh/`, `grok/grok-4.7/500k/xhigh/`.
Normalize through `task.review_packet.invocation_selection`; `hight` is high. A conflicting explicit
effort flag fails closed. Context is a provider-proven capacity requirement, never a spend budget.

Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/review-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory review context.

Audit is adversarial and read-only over product work. Read the declared assurance, the Task Contract's
sole exact executable Routing compiler result, and prior terminal evidence; compare only the changed-risk delta.
For `design`, first run `scripts/plan-work.py design-gate --plan-dir <dir>`. Require a completed
`finalize-design --finish` and audit the returned current fingerprint across every declared phase,
item, dependency and execution-sheet row. Persist the audit journal event with that fingerprint
using the existing `--fingerprint` field. A changed design input makes the verdict stale; after
correction, repeat finish and the design audit. GREEN is the only result that satisfies a `Design Audit: required` gate; by default the design audit is optional.
Before phase audit, consume one accepted, unsuperseded `audit-admission/v2` decision whose bounded
residual-risk question, target phase, material candidate fingerprint, audit run, owner-message
provenance, and scope digest all match. Foreign, stale, ambiguous, or already consumed consent does
not admit a run. Legacy `required`/`auto`/`light`, risk prose, integration seams, missing assurance,
or an agent-authored grant are advisory only. Without matching consent, preserve a bounded
recommendation and leave GREEN evidence eligible for direct close; missing or RED acceptance
returns owning repair.
Persist the runtime candidate snapshot with
a GREEN verdict. A post-GREEN mismatch is `audit-impact/v1`: gate-rebind, delta, justified full,
evidence gathering, or owner review—never bare stale/full. This classification scopes native repair
and evidence; it does not authorize another audit. Fresh deterministic evidence is reused.
Before GREEN, regenerate audit-owned carriers once, rebuild the candidate and persist
`task.plan_evidence.audit_finalization()` with the exact `phase_close_gate` admission; product
paths must remain byte-identical between the product and closure anchors.

Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput(audit=True))` as advice: at most one deterministic audit-owned bookkeeping
repair is allowed. A product defect returns one exact owning continuation; it does not trigger a
second audit, full replay, product write, or fresh root merely because this command is an audit.
Material risk selects one independent review path. Persist the semantic Next through `plan_delivery`.
One consent admits one bounded run; its in-progress journal event reserves it and its terminal event
consumes it. A repeat needs a new question, candidate/run-bound consent, and material hypothesis.

Audit does not bypass terminal admission: an applicable lease can only emit `waiting-owner` or its
typed continuation until a fresh terminal receipt and exact final fragment exist.

Persist a product finding as audit-attention (or audit-red) with decision action
`return-owning-continuation`, evidence IDs, reason_code, scope_class=<owning item>,
recovered=false, terminal=false,
and exact run-items owning continuation. Reviewer completion leaves the phase open.
