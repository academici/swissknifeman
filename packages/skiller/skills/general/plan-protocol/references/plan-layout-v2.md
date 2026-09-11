# Plan layout v2 reference

This reference expands the compact `plan-protocol` entry carrier for the sole executable layout.

## Selection and compatibility

`plan.md` must declare `Layout | v2`. Missing, `v1`, and unknown declarations fail closed with
`PLAN_LAYOUT_V1_RETIRED`; provider projections are adapters over these shared semantics.

## Carrier registry

| Carrier | Path | Owner reader | Mutability | Purpose |
|:--|:--|:--|:--|:--|
| plan core | `plan.md` | designer | handwritten/stable | identity, context, rules, routing |
| status view | `status.md` | owner | generated/volatile | phase and item status projection |
| decision record | `decisions/<D-id>.md` | auditor | append-only/slow | one accepted decision and provenance |
| decision views | `decisions/{current,archive,index}.md` | designer | generated/slow | current/superseded navigation |
| decision queue | `decisions/queue.jsonl` | owner | append-only/volatile | request/claim/response events |
| owner gates | `decisions/_gates.md` | owner | generated/volatile | unresolved authority gates |
| phase index | `phases/<Pn>/<Pn>.md` | designer | handwritten/stable | Phase Context and item addresses |
| item spec | `phases/<Pn>/<Pn.m>.md` | executor | handwritten/stable | sealed 11-field execution contract |
| item state | `phases/<Pn>/<Pn.m>.state.md` | executor | generated/volatile | status and five result fields |
| phase closure | `phases/<Pn>/<Pn>.closed.md` | owner | generated/slow | terminal phase contract/result |
| history view | `.plan-cache/history/<Pn.m>.md` | auditor | generated/on-demand | bounded journal projection |
| journal | `journal.jsonl` | auditor | append-only/volatile | execution events |
| handoff | `handoff.md` | owner | handwritten/volatile | next semantic action and launch block |
| brief/findings/research | named Markdown files | designer | handwritten/stable | evidence layers |
| bundle | `bundles/<Pn.m>.json` | executor | generated/stable | ordered digest-qualified inputs |
| roadmap | `roadmap.md` | owner | handwritten/slow | execution grouping, never routing override |
| canon | `packages/skiller/skills/general/plan-protocol/SKILL.md` | designer | handwritten/stable | protocol identity, invariants, enums, navigation |

The machine-readable registry for the plan programme is
`root/contracts/reader-contract-v1.registry.json`. New carriers require a decision record and a
reader-path justification; adding a convenient second owner for an existing fact is forbidden.

## Reader paths

### Executor

Read exactly, in order:

1. `plan.md` (identity, Context, Execution Rules, Routing only);
2. `phases/<Pn>/<Pn>.md` (Phase Context only);
3. `phases/<Pn>/<Pn.m>.md` (the selected immutable item spec);
4. `bundles/<Pn.m>.json` (ordered inputs and digests);
5. `phases/<Pn>/<Pn.m>.state.md` (fresh volatile state).

`handoff.md`, full `status.md`, full decisions, and raw journal are excluded from this path.
Capture all five members before exposing one through `task.plan_context.capture()`. Chunk continuation
uses only the immutable snapshot bytes and contiguous byte cursors; each member ends with its
terminal marker and binds the snapshot digest. Missing terminal proof, output truncation, a cursor
gap, or a changed live member fails before journal mutation with
`PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH`. The bundle may route to named required
reads; every entry is resolved and digest checked before mutation. Missing, unreadable, stale, or
digest-mismatched input fails closed.

`plan-lint` verifies that the first runnable item behind the terminal phase/item prefix has a
byte-fresh bundle. This catches a plan that looks valid but cannot fill the executor's fourth
mandatory slot. It intentionally does not require bundles for later predecessor-dependent items:
those artifacts can become resolvable only after the preceding item commits its declared output.
Build the eligible carrier with `plan-views.py bundle --plan-dir <plan> --item Pn.m`, then rerun
the check; never hand-edit the JSON.

### Designer

Read plan core, current status, current decisions, phase indexes/specs in design scope, roadmap,
handoff, brief, and the evidence named by the design task. The designer owns stable specifications
and appends decisions; it never hand-edits generated state/views.

### Auditor

Read plan core, phase/item specs, relevant bundle, decision records, generated current views, and
the bounded history projection through the selected journal position. Recompute evidence where
possible and classify the rest. The audit does not inherit an executor's uncommitted reasoning.

### Owner

Read `status.md`, `decisions/_gates.md`, phase closure views, and `handoff.md`; drill into specs or
evidence only when a decision requires it.

## Stable item spec and volatile state

The v2 item spec contains exactly the stable fields:

`Intent, Why, Scope Included, Scope Excluded, Inputs, Files, Required Reads, Implementation Rules, Code Guidance, Validation, Deliverables`

The generated state contains exactly:

`Status, Completion Notes, Pending Work, Known Deviations, Escalation Needed`

The journal is authoritative history; the state file is a projection. Attempts append journal
events, then regeneration derives current state. A state byte mismatch is a stale-carrier error,
not permission to hand-edit it.

## Decisions

Each `decisions/<D-id>.md` records id, date, status, decision, reason, evidence marker,
consequences, supersession links, and actor/model provenance. Accepted records are append-only in
meaning. Correct a decision with a new record that supersedes it. Generated current/archive/index
views provide navigation and compact compatibility pointers.

Owner requests use `decisions/queue.jsonl`: request → claim → response or auto-answer. The queue
does not replace a decision record. A resolved response is reconciled into the owning item/decision
before execution resumes.

Optional phase-audit consent is one accepted, unsuperseded phase-scoped decision with one fenced
`audit-admission/v2` JSON object. It contains `schema_version`, `target` with `phase_id` and
`candidate_fingerprint`, `run_id`, nonempty `residual_risks` rows with
`id`/`impact`/`evidence_gap`/`bounded_question`, `owner_message` in the form
`brief/file.md#id`, and `scope_sha256`. Existing `REPOSITORY-OWNER-MESSAGE` provenance must validate
that reference. The scope digest hashes canonical JSON of `target`, `run_id`, and `residual_risks`;
`consent_request(record)` maps it to gate `AUDIT-<Pn>`, branch `phase-audit`, and scope
`audit-admission/v2:<scope_sha256>`. The matching phase/run/fingerprint in-progress journal event
reserves the consent and its terminal event consumes it. It cannot be reused for another audit.
Normal direct close records no consent payload or additional audit gate.

## Closure carriers

`closure/<Pn>.json` is opt-in judgement evidence under `Closure Protocol | v1`. It says which data
class supported item/gate/metric claims: `real`, `synthetic`, or `baseline_pending`.

`phases/<Pn>/<Pn>.closed.md` is the generated v2 phase closure contract. It states the terminal
item set, phase result, scope commit, optional separate bookkeeping commit, gates, limitations, next action, and
source digests. It is produced at the terminal transition and checked against current specs/state.

These carriers are orthogonal: the JSON explains evidentiary judgement; the Markdown view supplies
the designer/owner closure contract. Neither can be inferred away from the other.

## Context boundary and adaptive failure handling

Context is chosen from the boundary predicate, not from command name:

| Value | Predicate |
|:--|:--|
| `continue-root` | authoritative root session can continue within budget/capabilities |
| `isolated-child-return` | bounded reviewer/worker returns evidence; root remains authoritative |
| `cold-start-root` | root cannot safely resume and a new root must reread committed carriers |

`cold-start-root` requires exactly one reason:

- `context-budget` — root cannot complete within its measured context budget;
- `capability-missing` — required capability cannot be added to the current root;
- `owner-pause-no-resume` — owner paused and no resumable root exists;
- `whole-plan-independent-audit` — adversarial audit of the whole plan requires independence.
- `design-root-terminal` — a completed `task:plan-design` hands its recommendation to a separately
  routed root and never executes or spawns the successor itself;

Ordinary item sequencing, local repair, or plan close does not itself justify a cold start.
Only a completed `task:plan-design` invocation is an explicit terminal-root exception. Audit
continuation uses the persisted `plan_continuity` decision and may remain in its authoritative root.
GREEN execution closes its item in the current invocation. When that is the last item of a phase
whose acceptance/safety gates are GREEN and no phase audit was explicitly admitted, it also creates
the phase closure before computing the post-closure Next. Handoff never launches close for that
result or repeats the current item.
Terminal producer phases use additive `producer-readiness/v1` evidence. Its consumer sees only a
digest-bound projection; an empty set requires an accepted owner `D#`. Re-entering an already
terminal phase is not inferred from prose or a design command: it requires the latest nonterminal
`phase-reentry-justification/v1` reducer outcome. Missing/stale producer evidence stays a bounded
repair in the current attempt, and priority fixes target only declared items through
`fix-branch/v1`.
First eligible local failure is repaired in root; a repeated fingerprint or risk trigger
permits one isolated reviewer. The child may report evidence but cannot close the root-owned item.

The strict spec is the boundary, not a demand for fixed stages. Inside a sealed item, the root may
group ready adjacent work, reorder local steps, and repair a reversible defect. It first applies
`observe → minimal reproduce → classify → act → verify`:

| Classification | Root response | Close outcome |
|:--|:--|:--|
| `procedural`, `transient`, `dependency-not-ready`, `unrelated-pre-existing` | safe fallback, bounded wait, local repair, or independent continuation | nonterminal |
| `acceptance`, `safety`, `authority` | stop only the affected item after actual-impact evidence | terminal/gated |
| unknown non-idempotent write | reconcile durable state before retry | safety pending reconciliation |

Correct routing before the start event. Do not classify a missing future consumer as producer RED;
record its dependency state. Reconcile PID/output/state before declaring an external process
terminal. A prior review remains valid without a new material scope/SHA/risk trigger. Deterministic
non-material state/view/navigation drift is repaired by its owner, regenerated once, and rerun in
the same root. The reviewer returns product findings to the executor. A new Acceptance or
ungranted authority choice requires its decision; already authorized product repair stays execution.
Declared Validation likewise remains current while relevant product/test/tool/config inputs and the
environment are unchanged. Rerun only the changed delta or a live check at its live boundary;
closure bookkeeping alone does not invalidate product evidence.

## Semantic Next extensions

In addition to execution/audit/close/archive/manual/waiting/terminal forms, v2 formalizes:

- `design-finish: task:plan-design <ID> finish` — reconcile a fully detailed plan, regenerate
  views/bundles, and prove design closure;
- `design-roadmap: task:plan-design <ID> roadmap` — refresh grouping/launch blocks without
  changing item specifications or Routing.

Both forms carry the same provider-neutral meaning. Provider-native invocations are renderings.

## Failure semantics

| Failure | Required response |
|:--|:--|
| layout missing | select v1 |
| layout unknown | fail closed |
| required carrier missing/unreadable | fail closed, name carrier |
| bundle digest mismatch | fail before mutation |
| state projection stale | regenerate from journal/spec; check bytes |
| generated view drift | run owner generator, then `--check` |
| route undershoot/unknown | fail before mutation |
| unsupported capability | owner/capability gate; no silent solo fallback |
| downstream red | keep item non-green and record finding |
| downstream unknown/unqualifiable | record limitation; follow owning contract's closure rule |
| repeated local failure fingerprint | change tactic once; then one isolated reviewer or authority/capability gate |

## Projection order

For a v2 item transition, respect these data dependencies. Independent work may be reordered:

1. append the journal event with neutral session identity and actor/model;
2. regenerate the selected item state;
3. regenerate `status.md` and decisions views if affected;
4. regenerate bundle/index views affected by stable-input changes;
5. when a GREEN item makes its phase terminal and direct close is admitted, generate
   `<Pn>.closed.md` and optional closure evidence in that execution invocation;
6. run owner `--check` commands and `plan-downstream.py --record`;
7. rewrite handoff from post-closure state with semantic Next and, for an actual runnable successor,
   its provider-native launch block;
8. lint the selected plan and commit implementation with changed bookkeeping once. A real
   digest-input collision or ownership/session boundary may require separate anchors.

Never hand-edit generated carriers. A failure or skipped check is recorded as non-green evidence.
