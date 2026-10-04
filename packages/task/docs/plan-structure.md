# Task plan structure - layout v2

Normal execution does not add a lifecycle carrier: `task.plan_lifecycle` transiently selects
focused or widened validation from declared impact, while existing route, projection, continuity and
delivery owners retain their respective carriers.

SSOT - compact skill `general/plan-protocol`; detailed media table - its
`references/plan-layout-v2.md`. Meta field `Layout | v2` required; absence or `v1`
is rejected by diagnostic `PLAN_LAYOUT_V1_RETIRED`.
When checking root-wide, the archived v2 plan is dated until `2026.09.09` inert: new requirements for
state/downstream/handoff do not rewrite its historical evidence. Explicit lint of this
of the archive remains under strict forensic verification.

```text
plans/<PLAN-ID>/
├── plan.md            # stable core: Meta, Context, Rules, Routing
├── status.md          # generated status view
├── phases/Pn/         # stable phase index/items + generated state/closure
│   ├── Pn.md
│   ├── Pn.m.md
│   ├── Pn.m.state.md
│   └── Pn.closed.md   # legacy report, not required by new execution
├── bundles/Pn.m.json  # ordered digest-qualified executor inputs
├── acceptance/       # candidate-bound phase/plan Validation evidence
├── closure/plan.json # whole-plan closure proof
├── decisions/         # append-only records + generated views/owner gates
├── handoff.md         # rolling owner/design/audit pointer; not executor input in v2
├── journal.jsonl      # append-only execution history
├── journal-exceptions.jsonl # optional D51 exact historical-schema exception sidecar
├── journal-migrations/ # owner-gated preimage + exact manifest/receipt for sealed repair
├── brief/             # owner input/refinements
├──findings/ # RAG extracts and recon reports
├── research/          # authored synthesis
├── artifacts/ # working material of the phases - fate: archive along with the plan
├── root/ # long-lived material - fate: project documentation
└── open-questions.md # controversial/unresolved with statuses (does not block the plan)
```

For v2 the required executor path is exactly `plan.md` → `phases/<Pn>/<Pn>.md` →
`phases/<Pn>/<Pn.m>.md` → `bundles/<Pn.m>.json` → `<Pn.m>.state.md`. `handoff.md`, all
`status.md`, the entire magazine and the entire catalog of solutions are not included in this path.

Historical phase closure has two different media: opt-in `closure/<Pn>.json` captures the class
evidence-judgments, and generated `phases/<Pn>/<Pn>.closed.md` is a terminal contract and
result for designer/owner. One does not replace the other. New execution verifies phase acceptance
without a phase-close lifecycle. Only `task:plan-close <PLAN-ID>` closes the whole plan.

## Evidence anchors

`evidence-graph/v1` - derived runtime carrier, not handwritten map. It binds spec,
bundle digest inputs, declared product paths and closure. Before mutation `Files ∩ digest_inputs`
with required fresh closure check is rejected as `SELF_INVALIDATING_EVIDENCE_ANCHOR` and requires
minimum product/closure split. If there is no collision, one collapsed anchor is used.
Closure proves byte identity product paths; registry-owned volatile projections, journal and
handoffs are considered bookkeeping until item explicitly displays them in Deliverables.

## Public reason taxonomy

`task.task_contract evaluate` and CLI `check` keep accurate internal diagnostic in
`pre_mutation`/`pre_final` and additionally return `reason_codes` for recovery logic.
Public closed set: `schema-invalid`, `evidence-missing`, `evidence-stale`,
`evidence-forged`, `policy-denied`, `conflict`, `corrupt-state`, `durability-failed`.
Each entry carries the original `internal_code` and a short action; unknown internal
diagnostic is safely normalized in `policy-denied`. This is an additive JSON change: old
consumers continue to read the old fields, the new ones do not have to parse the message text.

## Terminal admission lease

`terminal-admission-lease/v1` is ignored project-local runtime state, not a sixth plan carrier.
It is keyed by provider/session + Task session/run + plan/subject/command, with monotonic
progress and bounded expiry; each event retains its turn identity separately, so a later turn of
the same run cannot silently bypass the active lease. `final-admission-event/v1` is append-only hash-only evidence: the
same refreshed typed P1.3 terminal decision, exact terminal receipt and exact machine-authored
recommendation fragment are required for `final_allowed=true`. No lease leaves ordinary chat
untouched; invalid, stale or released applicable state returns a stable `re-arm` recovery verdict.
Provider adapters may translate this reducer, but cannot replace its terminal policy.

Before `audit-green` audit-finalization regenerates owned projections once, rebuilds candidate and
records `audit-finalization/v1` with `close_admission=allow`. Phase acceptance consumes that evidence;
the compatibility gate name does not authorize a separate phase-close launch.

## Phase Assurance | v1

A missing block means isolated, seam-free, reversible and direct-close. Handwritten block with
`Impact`, named `Integration Seams`, `Live or Irreversible`, `Audit Intent` and non-empty `Rationale`
is only needed for seam/hard-risk/live boundary, owner-requested audit or ambiguous default.
`plan_assurance.evaluate()` is the only reducer for the first audit/direct close and for
post-GREEN impact. The explicit `direct-close-eligible` is retained for compatibility; material risk without
fresh owner-bound admission remains a recommendation, not an automatically assigned audit. Candidate
runtime is built from plan-dir + phase-id. After GREEN runtime saves the snapshot and classifies
field variance as `audit-impact/v1`, returning only `gate-rebind`, `delta`, justified
`full`, `gather-evidence` or `owner-review`; bare stale/full is prohibited.

Historical `Audit Intent: light` normalized in named `legacy-light`: direct close
is saved only for one green item without material risk; any other legacy-light candidate
remains audit-required. New phases do not use this compatibility intent.

Next to the plan catalogs there is `plans/ACTIVE.md` - 4-line index of the active plan
(parses `plan-lint`); flat `.md` directly into `plans/` - plan mode drafts,
unfold `/task:plan-design from-draft <file>`.

## Historical journal exception

`journal-exceptions.jsonl` optional and append-only: it never carries an event, status, or Next.
It may waive only an exact historical `friction` schema failure when the target physical line, raw
SHA-256, plan ID, exact field set, and an existing Owner D# all match. Any duplicate, malformed or
valid target, foreign plan, hash mismatch, or additional invalid field fails closed. Create it only
with `task.journal exception`; do not rewrite or compensate the historical journal event.

## Sealed journal migration

Ordinary execution remains append-only. If an already sealed row cannot be made valid by a
compensating append or the deliberately narrow D51 `friction` exception, an accepted Owner D# may
authorize one exact `journal-migration/v1`. The manifest lives at
`journal-migrations/<migration-id>/manifest.json`, binds the complete source/target SHA-256 and
every changed line, and permits only neutral missing-field backfill, bounded terminal-evidence
recovery, explicit legacy enum/friction normalization, and reset of an orphan `in-progress` row
that never had a durable session/run identity. A later duplicate qualified execution start may
also become `no-op` only when one earlier start of the same plan/item/attempt/run survives,
its session derives that run ID, timestamps are ordered, and the run has no terminal. All other
fields and the first start remain unchanged; the accepted decision and exact manifest still apply.
`task.journal_migration` saves the original `journal.jsonl` bytes as
`journal.preimage.jsonl`, writes a digest receipt, and fails closed on drift, path traversal,
unlisted semantic edits, or an absent accepted decision. This is the sole exception to physical
append-only storage; the preserved preimage remains the historical source.

## root/ vs artifacts/ - semantic difference

Two catalogs of artifacts differ in fate, not in format: `root/` - timeless material,
which will survive the plan and become the docs of the project; `artifacts/` - working material of phases,
leaving for `plans/archive/<ID>` along with the plan. Set of files `root/` - as needed
plan, not all are required.

## Migration table root/ → docs

When archiving a plan (`/task:plan-close archive <ID>`), the contents of `root/` migrate to
project documentation on Diátaxis types:

| File in `root/` | Diátaxis-type | Where in the project docs |
|:--|:--|:--|
| `architecture.md` | explanation | architectural section docs |
| `philosophy.md` | explanation | “why is this so” - next to architecture |
| `data-model.md` | reference | data model reference |
| `contracts/` | reference | contracts/API directory |
| phase guides | how-to | how-to guides |

Migration checklist (what was transferred to docs, what remained in the archive) - a mandatory part
final `handoff.md` archived plan.

## Routing (§3 plans) – Batch, route and review

The new layout-v2 plan uses exactly six columns:
`Batch | Items | Model class/effort | Exec | Review | Why`. Routing covers every item
exactly once. `Exec` — enum `run` | `plan-design` (legacy `plan-exec`/`manual`/`plan-run` read as `run`); `Review` —
`full` | `light` | `none`.

Adjacent items of one phase are combined when the common producer/consumer, Required Reads, setup
or Validation allows you to save a repeated cold start. Separate commit/Deliverable is not
breaks Batch: the lifecycle of each item is executed within the group. `solo` requires specific
reasons - incompatible Exec, owner/irreversible gate, separate capability or context budget.
Batch does not cross phase audit/close and does not mix Exec; startup uses maximum
model/effort/review groups and union capabilities.

## Contracts (§7/§11 plan) — cross-plan notification

Section `## 7. Contracts` in `plan.md` fixes the public contract of the plan: `### Exported`
(SemVer version, what is frozen, date of notification to consumers) and `### Consumed` (which
contracts of other plans are used, which is noticed on their update, reaction). Item, bumping
Exported-contract is obliged to update the donor line `Exported` in the same bookkeeping commit and
line `Consumed` of each consumer plan **in the same root `plans/`**; cross repo push -
mAInd bus task, not plan protocol (an entry remains in `open-questions.md` of the donor).

## Portability: two shooting ranges and bundle requirements

The plan/task carries **portability range** - how much material must travel with
task so that the cold session can execute it without chat. Enum tiers, both failure codes
(`PORTABILITY_INPUT_MISSING`, `PORTABILITY_EXTERNAL_INPUT`), block `privacy` and pair
`semantic_carrier`/`provider_renderers` belong to Task Contract v1; **rule
classification** - Plan Portability v1 (both contracts - plan,
`root/contracts/`).

```text
tier(work) := committed-bundle if work.sessions == "multi"
                                 OR work.risk == "high"
                                 OR work.handoff
                                 OR work.audit
              brief-acceptance otherwise
```

Tier assigns **root supervisor**, compiling Task Contract, BEFORE dispatch - not
item'executor and not a subagent: the subagent receives an already resolved shooting range, not a task
classification. Re-assignment - only when changing one of the four characteristics, recording with
with the same hash in `supersedes`. The compiler is machine checked: `plan_lint`
(`_lint_tiered_portability_22`, threshold `PORTABILITY_TIER_CANON_DATE`) rejects, in this
order: (1) shooting range, which the rule does not issue for the advertised work; (2) `committed-bundle`
with empty `execution_inputs`; (3) a path present in both `execution_inputs` and
`provenance_only`; (4) absolute / `~`-root / beyond the root / URL-like input;
(5) `produced-by-predecessor`-input without named manufacturer.

**Provenance against execution input - by ROLE, not by spelling.** Path - execution input,
if the item actually READS it (it is named in `Inputs`/`Required Reads`/`Validation`); path -
provenance, if it only explains the origin and not a single item'field reads it.
Interlinear test for `tmp/` is incorrect in both directions: committed readable path with `tmp` in
name is the input, and the draft, which the performer looked at, but did not name a single field, is
provenance, wherever it lies. Host, chat, mAInd and other people's repositories - provenance by
construction.

**What is obliged to carry `committed-bundle`** (not “everything that was at hand”):

| Requirement | Meaning |
|:--|:--|
| Minimization | only that for which the input is actually read; `privacy.minimized = true`, and `privacy.excluded_classes` names the excluded - raw bodies, chain-of-thought, tool-payload's, secrets |
| Deterministic manifest **and** verifier | integrity is recalculated, not verified: hashes are calculated anew, they are not taken on faith, the verifier is committed along with the bundle |
| Full dependency closure | an input referencing another artifact pulls it along with it - otherwise the cold session crashes on the second file |
| One neutral semantic carrier + provider-renderers | the rendered Claude or Codex call is a **projection**, not the source of truth; `context` is a neutral literal, Russian lines of command files are its projections |
| Proof class | no public acceptance predicate stands on `pinned-not-recomputable`/`unknown`; such material travels only as a marked context |

**Evidence Classes** (private enum, Source Evidence Verification v1): `recomputed`
(re-derived from the committed bytes by its own algorithm) · `cross-checked` (two or more
committed documents are checked against each other, none is considered true in itself) ·
`pinned-not-recomputable` (committed constant as marked context) `unknown`
(the output base has not yet been installed). Transition from the last two classes to the first two -
only by editing the list of contract statements and the verifier algorithm, **never in prose**.

## Form `Next` and order of closing item'a

`handoff.md` carries provider-neutral `Next` as the first line. enum includes execution/audit/
close/archive/manual/waiting/terminal and design forms, including
`design-finish: task:plan-design <ID> finish` and
`design-roadmap: task:plan-design <ID> roadmap`. Historical slash forms are read for
compatibility. Each execution Next carries the `Batch` line from Routing and the command for everything else
adjacent-suffix; linter does not allow handoff to silently collapse a group to one item. Closed
item must be PRINTED in `Completion Notes`
both boundary codes are `pre_mutation:` and `pre_final:`, both with the value `allow` (`n/a` in green
does not count). From 2026-07-27 this is not only a prose of the audit checklist: `plan_lint`
(`_lint_write_site_codes_44`, threshold `WRITE_SITE_CODES_CANON_DATE`) gives ERROR on `🟢`/`🟠`
item'e, whose date in the `Updated` column of the `## Phase Status` column is not less than the threshold, but there is no code
or it is other than `allow`. Scope forward-only by date **item'a**: closed to threshold not
is diagnosed at all - the new gate does not retroactively recolor other people's living plans.
After the first non-GREEN phase audit `plan-run` can once return an explicitly named
terminal item in `🟡 In progress` without re-design, if the stable technical specification has not changed and Pre-mutation
Task Contract remains `allow`. The second audit is final: its non-GREEN exhausts
`audit_rounds_max`, so the next item execution gets `LOOP_BUDGET_EXCEEDED` and does not create
third cycle.
Closing item'a - fixed order: diff Scope →
`validate.sh` package → bookkeeping plan (statuses, Completion Notes, Update Log) → rewrite
`handoff.md` → `plan-lint --baseline HEAD` **after** handoff → the invoice is published with attribution
(“new from diff item'a: K”) → bookkeeping-commit. Run `plan-lint` before rewriting `handoff.md`
is prohibited - the closing item itself changes the handoff, and the “to” count does not describe the resulting tree.

## Open Questions - protocol

A controversial item does NOT block the plan if it is submitted to `open-questions.md` with one of the statuses:
`Exploration` · `Decision pending (owner needed)` · `Resolved → D#`. Question hanging
in the body of the phase without removal, - audit finding; closing a plan with pending issues - only
`🟠 Done with deviations`. Re-design on top of closed phases - new D# with link "supersedes"
D#-old", old D# cannot be edited.

## Context v2

`Context` - exactly `continue-root`, `isolated-child-return` or `cold-start-root`.
Cold start is only allowed with the reason `context-budget`, `capability-missing`,
`owner-pause-no-resume`, `whole-plan-independent-audit` or `design-root-terminal`; team name
is not a cause in itself. Before recording handoff
one `task.plan_continuity.reduce()` accepts versioned work estimate: attested route/capabilities,
context health, digest remaining batch, loaded-input reuse, cold-start cost, lifecycle and durable
checkpoint. Renderer, DecisionRequest, delivery receipt and live lint use its typed decision,
without selecting Context again. Regular items sequence and inaccessible context telemetry
remains in root, bounded reviewer returns evidence to root, and `waiting-owner` does not release
runnable successor.

## Two house plan

Where SSOT lives is determined by the stage: at the start of exec the plan moves to the project repo
(Meta `Home: repo:<path>`). The archive only works with repository carriers; optional
synchronization with Brain is a separate documentation operation and is not a precondition for it.
Full cycle - [Methodology](./methodology).

## Short links to work

The new plan is stored in Meta `Short ID | PLAN1`, separate file task - `Short ID: TASK1`
in the document title. The numbers are constant and unique in the repository in their series,
including archive; The day number in the folder name remains a separate number.
Outside the work folder, links look like `PLAN<N>.D35`, `PLAN<N>.P2.3`, `TASK<N>.D2`; between projects -
`swissknifeman:PLAN<N>.D35`. Old plans without Short ID use the full ID before the local one
link. Commands still accept the full PLAN-ID.
Canon of assignment and references: `plan-protocol/references/work-references.md`.
