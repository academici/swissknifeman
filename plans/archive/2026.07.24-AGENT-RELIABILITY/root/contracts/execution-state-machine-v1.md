# Execution State Machine v1 (P2.1)

RAG:— (plan-grounded: D8/D9/D23/D50/D51/D57 and D64–D68; repo-grounded:
`root/contracts/task-contract-v1.md:65-213`, `packages/task/lib/task/journal.py:39-46`,
`packages/skiller/skills/general/plan-protocol/SKILL.md` §§6–10,
`packages/task/commands/plan-{exec,run,close,audit,design}.md`, root `AGENTS.md`;
synthesis: `research/06-p2.1-contract-boundary.md` §§1–2).

## Scope

This contract seals **the lifecycle of one plan item**: which states exist, which events move
between them, which transitions are declared impossible and why, how the machine projects onto
the fleet's own vocabularies, and one deterministic decision function a supervisor may consume
instead of building a second decision engine.

It is a **layer on top of** the frozen P0.2 Task Contract, never a copy of it (D64). P0.2 owns
the compiled contract and the two checked boundaries; this contract owns what the RESULT of
those boundaries does to an item. Where the two meet, this file cites `file:line` and stops.

It seals semantics only. It implements nothing: the compiler/dispatch seam is P2.2, the
finding/review enforcement is P2.3, route evidence is P2.4 (item P2.1 Scope Excluded).

## Machine carriers

| Artifact | Role |
|:--|:--|
| `artifacts/P2.1/state-transition-cases.json` | the machine form of everything below: declared sets, all 135 cells, both projections, the corpus mapping, the F14 positive cases and the mutations |
| `artifacts/P2.1/validate_state_cases.py` | the sole executable owner of the totality, partition, projection, decision-function and doc↔data proofs |
| `root/contracts/risk-review-loop-budget-v1.md` | finding types, `finding_id`, cap and its subject — the guard values this machine branches on |
| `root/contracts/plan-portability-v1.md` | tier classification and the provenance-vs-execution-input rule for the inputs a dispatch is grounded from |

## Frozen upstream

Everything in this section is owned by an earlier item and is **cited, never restated**. A
paragraph here that could be replaced by one of these references is a defect of this contract.

| Fact | Owner | Source |
|:--|:--|:--|
| Precedence ladder, `CONFLICT_PRECEDENCE_VIOLATION`, `CONFLICT_UNRESOLVED` | P0.2 | `root/contracts/task-contract-v1.md:65-84` |
| Authority classes, the G1 wording «cannot be rolled back / visible outside», `authority.loop_budget`, `same_finding_max` | P0.2 | `root/contracts/task-contract-v1.md:86-99` |
| Public-acceptance rule and the proof-class gate | P0.2 | `root/contracts/task-contract-v1.md:101-113` |
| The twelve ordered pre-mutation reason codes | P0.2 | `root/contracts/task-contract-v1.md:135-154` |
| The three pre-final reason codes and the `n/a` rule | P0.2 | `root/contracts/task-contract-v1.md:156-165` |
| Root/subagent slice partition, `SLICE_INCOMPLETE` | P0.2 | `root/contracts/task-contract-v1.md:167-178` |
| Cold-start payload rule, `COLD_START_INCOMPLETE` | P0.2 | `root/contracts/task-contract-v1.md:180-185` |
| The six canonical plan statuses | plan-protocol §6 | `packages/skiller/skills/general/plan-protocol/SKILL.md:344-351` |
| Journal `COMMANDS` | P1.1 journal schema | `packages/task/lib/task/journal.py:39` |
| Journal `RESULT_VALUES` | P1.1 journal schema | `packages/task/lib/task/journal.py:43-46` |
| The two-commit close topology and the tree anchor for numbers | plan-protocol §8 | `packages/skiller/skills/general/plan-protocol/SKILL.md:697-747` |
| The six escalation triggers | plan-protocol §10 | `packages/skiller/skills/general/plan-protocol/SKILL.md:980-999` |

**Reason codes are never re-minted.** An existing condition reuses its exact P0.2 code. The
eight conditions this layer adds that P0.2 names nowhere are declared in
`state-transition-cases.json::new_reason_codes`, each with a `distinct_from` justification
naming the P0.2 code it is **not**; the validator refuses a new code that collides with a frozen
one or whose `distinct_from` does not name a frozen code.

## Declared sets (D51/D65)

Literal and closed. The executor does NOT extend them silently: a real transition that does not
fit is a **spec defect** (`plan-protocol` §6) — stop, record a D#, and let the owner of the spec
change it. Silent widening is a refusal of the item, not a fix.

Nine states. `🟢` and `🟠` are **not** states: both are `DONE`, separated by the attribute
`material_deviation`; a `DONE_WITH_DEVIATIONS` state would multiply terminal branches across the
whole matrix.

<!-- declared-set: states -->
```text
READY
EXECUTING
VERIFYING
FIXING
DONE
INCIDENT
OWNER_BOUNDARY
ESCALATED
SKIPPED
```

| State | Means |
|:--|:--|
| `READY` | the item is declared and detailed; no session holds it |
| `EXECUTING` | one executor session holds it and may mutate under the per-mutation boundary |
| `VERIFYING` | the Scope diff is complete; the item's own `Validation` and the pre-final predicate are evaluated |
| `FIXING` | a bounded repair round inside the same item |
| `DONE` | closed by the two-commit topology; `material_deviation` selects 🟢 or 🟠 |
| `INCIDENT` | the declared budget is spent: cause/action/verification are recorded and no inline repair is attempted |
| `OWNER_BOUNDARY` | stopped at a G1 action with the exact missing authority named |
| `ESCALATED` | the spec diverged from reality; `plan-design` repairs it, not the executor |
| `SKIPPED` | closed ⛔ by an explicit decision |

Fifteen events. Parameterized events (`pre-mutation-deny`, `pre-final-deny`, `typed-finding`,
`audit-verdict`, `owner-decision`, `escalation-trigger`) carry a payload but remain ONE event:
unfolding an audit verdict into three events triples the matrix without adding meaning.

<!-- declared-set: events -->
```text
dispatch
pre-mutation-allow
pre-mutation-deny
mutation-complete
validation-green
validation-red
typed-finding
same-finding-third
pre-final-allow
pre-final-deny
close-committed
audit-verdict
owner-decision
escalation-trigger
skip-by-decision
```

Six decision outputs — the entire result vocabulary of the decision function below.

<!-- declared-set: decision_outputs -->
```text
continue-next
retry-fix
escalate-design
escalate-owner
incident
stop-terminal
```

`continue-next` = the supervisor may proceed with the next executable unit (this includes a
green or deviation close and a recorded no-move). `stop-terminal` = this transition authorizes
no next step and the session must not invent one (a routing stop, or a decision that kills the
item). The other four name their target state.

Four decision values an authority holder may return. Under `owner-gated` the holder is the
owner; under `self-host` it is the agent for everything except G1 (see
`risk-review-loop-budget-v1.md` § Authority profiles) — one event, two subjects, never two
vocabularies.

<!-- declared-set: owner_decisions -->
```text
granted
refused
deferred
accept-deviations
```

Four deny classes. They **partition** the twelve frozen P0.2 pre-mutation codes exactly; the
validator proves the partition against `task-contract-v1.md:135-154` rather than trusting this
table. This is the whole mechanism by which the machine branches on a P0.2 result without
re-minting a single code.

<!-- declared-set: deny_classes -->
```text
route
authority
loop-budget
contract-defect
```

| Class | Frozen P0.2 codes |
|:--|:--|
| `route` | `ROUTE_UNDERSHOOT`, `CAPABILITY_UNSUPPORTED` |
| `authority` | `AUTHORITY_BOUNDARY` |
| `loop-budget` | `LOOP_BUDGET_EXCEEDED` |
| `contract-defect` | `VERSION_HASH_MISMATCH`, `CONFLICT_UNRESOLVED`, `CONFLICT_PRECEDENCE_VIOLATION`, `NEXT_CHANGED_WITHOUT_TRANSITION`, `PORTABILITY_EXTERNAL_INPUT`, `PORTABILITY_INPUT_MISSING`, `SLICE_INCOMPLETE`, `COLD_START_INCOMPLETE` |

Four audit outcomes — the audit verdict combined with whether the defect lies in THIS item's
deliverable, because `plan-audit`'s remediation default (follow-up items in the next phase)
differs from its reopen case by exactly that question.

<!-- declared-set: audit_outcomes -->
```text
green
attention
red-own-deliverable
red-other-scope
```

## Totality: 9 × 15 = 135 cells

Every cell is covered **exactly once** by either a declared transition or a declared
impossibility carrying its own reason. A wildcard/default rule has no representation in the
carrier format and is forbidden by name: a default rule is precisely the mechanism by which an
uncovered cell passes silently.

No two rules may exist for one `(state, event)`. A guarded cell partitions its guard's declared
value set exactly — disjoint and exhaustive — and the validator proves the partition instead of
counting branches. Totality is proven **by construction**: the validator enumerates the
cartesian product in code and consumes cells from that set; leftovers are missing cells,
repeats are duplicates. Counting 135 entries would not be a proof.

The declared impossibilities fall into seventeen named classes (`impossibility_classes` in the
cases file); each individual cell still carries its own reason naming its own state and event.

| Class | Why the event cannot legally fire in that state |
|:--|:--|
| I1 | a mutation event cannot be attributed to an item no session holds |
| I2 | the Validation of record belongs to `VERIFYING`, over the item's finished Scope diff |
| I3 | the same-finding counter counts fix rounds; a state that has had none cannot reach its third |
| I4 | the pre-final predicate runs only after pre-mutation allowed and the item claimed completeness — P0.2 fixes `n/a` otherwise |
| I5 | a close without any execution is the no-op close `plan-audit` detects |
| I6 | the item is already held by a session; a second dispatch forks ownership |
| I7 | a close that skips `VERIFYING` skips the item's Validation |
| I8 | a phase audit is dispatched only over a phase whose items are all terminal |
| I9 | no mutation happens in `VERIFYING`; a repair enters `FIXING` first |
| I10 | the item is terminal-closed, so an execution-loop event has no object on it |
| I11 | a Validation re-run over a closed item is an audit observation whose carrier is `audit-verdict` |
| I12 | a second close duplicates the bookkeeping and breaks the commit→item map |
| I13 | a terminal item cannot be skipped |
| I14 | an open incident forbids repair without a recorded cause/action/verification and an explicit decision |
| I15 | the G1 boundary withholds exactly this action until the authority is granted |
| I16 | an escalated item is repaired by `plan-design` before any execution event may fire on it |
| I17 | a ⛔ item carries no execution loop |

### The load-bearing paths

- **Happy path.** `READY --dispatch--> EXECUTING --mutation-complete--> VERIFYING
  --validation-green--> VERIFYING --pre-final-allow--> VERIFYING --close-committed-->
  DONE`. The two-commit topology (`plan-protocol` §8) is what the `close-committed` event
  reports; this contract does not restate its steps.
- **Bounded repair.** `VERIFYING --validation-red | pre-final-deny | typed-finding[reopens]-->
  FIXING --mutation-complete--> VERIFYING`. Ordinary findings raised while the item is still
  mutating stay in `EXECUTING`: entering `FIXING` before the item claims completeness would
  inflate the fix-round counter with ordinary development.
- **Cap.** `* --same-finding-third--> INCIDENT`, and `* --pre-mutation-deny[loop-budget]-->
  INCIDENT`. The resolution of an incident is the ONE place where the authority profile changes
  the outcome, not merely the actor (below).
- **Authority.** `OWNER_BOUNDARY` is entered **only** on the G1 boundary — «cannot be rolled
  back / visible outside» (tag/push/release, fleet, consumer repositories, FOREMAN outward
  parts) — and never on a competence boundary; the transition names the exact missing authority.
  Every `close-committed`/`mutation-complete` cell in that state is a declared impossibility for
  that reason.

## Projections (total both ways)

`project(state, material_deviation) → status` is a **total function**. `DONE` is the only state
whose image depends on the attribute, and that is required by D65 itself: 🟢 and 🟠 are one
state separated by the `plan-protocol` §6 material predicate, so the attribute must be
projection INPUT or D65 could not hold. Every other state has a constant image.

The six canonical statuses are NOT re-minted here; they are cited from
`packages/skiller/skills/general/plan-protocol/SKILL.md:344-351` and carried in
`state-transition-cases.json::referenced_sets.canonical_statuses`.

| State | Canonical status |
|:--|:--|
| `READY` | `⬜ Not started` |
| `EXECUTING` · `VERIFYING` · `FIXING` · `OWNER_BOUNDARY` | `🟡 In progress` |
| `DONE` (`material_deviation = false`) | `🟢 Done` |
| `DONE` (`material_deviation = true`) | `🟠 Done with deviations` |
| `INCIDENT` · `ESCALATED` | `🔴 Blocked` |
| `SKIPPED` | `⛔ Skipped by decision` |

`OWNER_BOUNDARY` projects to `🟡`, not `🔴`: `plan-protocol` §8 reserves `🔴` for a DEFECT (plan
diverged from code, needs re-design) and classes a healthy wait on external state as `waiting:`.
An ungranted G1 authority is a healthy wait. `INCIDENT` projects to `🔴` because an exhausted
budget IS a defect of the loop, and its canonical remediation is a decision plus a re-design.

The journal projection runs the other way: **every one of the eight `RESULT_VALUES`
(`journal.py:43-46`) must be produced by at least one declared transition.** An unreachable
value is named as a finding — either a state was lost or the journal value is dead — never
hidden. No third status vocabulary is introduced: the machine's own states are the only new
names, and they map onto the two existing vocabularies rather than replacing either.

## The decision function

```text
decide(state, event, payload, profile) → one of the six declared decision outputs
```

Pure and deterministic: same inputs → same output, no clock, no filesystem, no randomness. It
is a lookup over the 135-cell matrix — the guard, if any, selects the branch; the branch names
the output. `2026.07.18-FOREMAN` consumes exactly this instead of building a second decision
engine (its D49/D51/D59; `plans/README.md` § «Разведение супервизора»).

A cell declared **impossible** returns the uniform output `escalate-design` together with that
cell's own declared reason: observing an event the matrix declares impossible is a spec↔reality
divergence, and its owner is `plan-design`. That is not a default rule — every such cell carries
its own reason, and no cell is left uncovered for a default to absorb.

`profile` is a real parameter, not decoration: at an exhausted cap
`decide(INCIDENT, escalation-trigger, …, owner-gated) = escalate-owner` while
`decide(INCIDENT, escalation-trigger, …, self-host) = escalate-design`. The subject of that
decision is owned by `risk-review-loop-budget-v1.md` § Authority profiles (D68).

## Supervisor, item executor and fresh dispatch

- The **root supervisor** persists across items. It holds the compiled contract, the resolved
  conflicts and the portability decisions — the root-only slice of P0.2
  (`task-contract-v1.md:167-178`). It never delegates a resolution problem, only a resolved
  contract.
- Each next executable item is delegated to a **fresh item-executor session** grounded from the
  committed plan and handoff, not from the supervisor's chat tail (root `AGENTS.md`
  § «Codex launch and hook integrity»; `plan-protocol` §8 «item/phase → handoff → context
  boundary»). The subagent receives the subagent slice plus the contract's version hash, so its
  report is attributable to exactly one contract revision.
- Sequentially dependent items run **one at a time**; the supervisor continues automatically
  after a green close or audit and yields only at an `OWNER_BOUNDARY`, an `INCIDENT`, or an
  `ESCALATED` state.
- A **launch block is a recovery carrier**, never a request for the owner to relay routine work.
  Its form, its three `Context` values and its scope-payload are `plan-protocol` §8's; this
  contract adds nothing to them.

### Launch-carrier semantics and the §7 orchestration verdict (D67)

`plan-protocol` §7 requires a ready workflow script only when one of two signals fires. Measured
on the facts of phase P2 rather than judged by feel, as §7 itself demands:

- signal «N≥3 items with independent scope» does **not** fire — `Inputs` of P2.2 reference P2.1,
  P2.3 reference P2.2, P2.4 reference P2.2/P2.3, P2.5 reference P2.2–P2.4
  (`phases/P2.md:54,73,92,111`): the chain is strictly sequential;
- signal «a long autonomous chain without manual intervention between items» does **not** fire —
  every item boundary is a canonical checkpoint (two commits, a rewritten `handoff.md`, an
  attributed `plan-lint`), and the supervisor's auto-continuation runs INSIDE that protocol,
  not around it.

**Verdict: phase P2 carries no workflow script.** The inverse condition is fixed here as the
rule, not as a one-off: *a phase that gives up per-item close MUST carry a script* — because
that is exactly when state stops passing through git and the plan. Writing a script "just in
case" would create a second launch carrier beside the `roadmap.md` launch blocks, the duplicate
this plan exists to remove.

## Boundaries (И1–И3)

| Not touched here | Owner (plan AND item) | Reason | ПРОХОД |
|:--|:--|:--|:--|
| `packages/task/**` and the `plan-protocol` canon | `2026.07.24-AGENT-RELIABILITY` **P2.2** (then P2.3) | single owner of the `2.11.0 → 2.12.0` bump; a second edit in the same pass is a race (`plans/README.md` § «Владение поверхностями») | the canon must change earlier → D# + move the change into P2.2's Scope, never an edit in place |
| The frozen P0/P1 contracts and their artifacts | P0.1–P0.3, P1.1 (all terminal) | the freeze is this phase's input; editing it voids the P1 proofs | a divergence → D# with `supersedes`, never a silent sync |
| `artifacts/P1.1/remediation-map.json` (`baseline_owners`) | **P1.1** | P2.1 is absent from `baseline_owners`, so no drift baseline is captured for it | a real need for a drift gate → D# + an edit by P1.1's owner, not a copy of P2.2's step |
| The user-owned enabled set of a provider | the owner (D42) | a live profile mutation lies outside any plan's boundary | a diagnostic row with a named `safe_owner_action`, never a silent edit |
| Another plan's files (FOREMAN, ECO-OPT) | `2026.07.18-FOREMAN` P2/P5 · `2026.07.25-ECO-OPT` P9 | editing a consumer's plan to "notify" it violates И2 | notification is the `## 7. Contracts` § Exported rows of this plan; both consumers are gated by terminal P2 |

**Freeze semantics (И2).** This contract is frozen as `v1` at the close of P2.1 and its
extension mechanism is **additive**: a new state, event or output is a **major** bump (it
invalidates the 135-cell totality proof and every consumer's exhaustiveness), a new guard branch
inside an existing declared enum is **minor**, a reason or note edit is **patch**. "Frozen
forever" does not exist here; frozen means *versioned, with a named way through*.

## Contribution gate (D23)

- **Existing extension points surveyed before adding one.** `task-contract-v1.md` already owns
  the compiled contract, both predicates, the slice and the cold-start payload; `plan-protocol`
  §§6/8/9 already own statuses, close topology, routing and review depth; `journal.py` already
  owns the run vocabulary. None of them owns the LIFECYCLE between two boundary checks — that is
  the gap this contract fills, and it is the only thing it adds.
- **Named consumers (Rule of Three satisfied, not imagined):** `P2.2` (compiler and root
  dispatch), `P2.3` (finding/review enforcement), `P2.4` (route evidence), `P2.5` (end-to-end
  bank), `P3.1` (trace identity), and **outside this plan** `2026.07.18-FOREMAN` P2/P5 (Artifex
  re-scoped to a thin wrapper consuming `decide`) and `2026.07.25-ECO-OPT` P9 (reads the finding
  vocabulary of the sibling contract).
- **Alternatives considered (≥2).** (a) *Let each consumer derive its own decisions from the
  prose of `plan-protocol`* — rejected: that is exactly how FOREMAN started building a second
  decision engine, which the owner cancelled (`plans/README.md` § «Разведение супервизора»).
  (b) *Extend `task-contract-v1` with lifecycle fields instead of a new contract* — rejected:
  P0.2 is frozen and its schema is `additionalProperties: false` everywhere, so the extension
  would be a breaking change to a contract three phases already consume; a sibling contract that
  cites it is additive (И10).
- **SemVer/ADR result:** new contract at `v1`, additive to the frozen set; no existing contract
  changes version. The ADR is this section plus D64–D68.

## Consumers

`P2.2` compiles and dispatches against this machine without adding states; `P2.3` implements the
finding/review side of it; `P2.4` supplies the route evidence the `route` deny class reads;
`P2.5` proves the historical corpus cases end to end; `P3.1` links the state and the decision
output into the unified trace; `P4.3` reports the measured result. Outside this plan,
`2026.07.18-FOREMAN` P2/P5 consume `decide` (its re-scope marker is removed only when P2.1
**and** P3.1 are terminal — its D59), and `2026.07.25-ECO-OPT` P9 reads the sibling contract's
finding vocabulary as a foreign surface. No consumer may introduce a state, an event or a
decision output of its own: the sets above are closed, and widening one is a D# against this
contract, not a local extension.
