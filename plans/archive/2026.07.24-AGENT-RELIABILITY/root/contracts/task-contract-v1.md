# Task Contract v1 (P0.2)

RAG:— (plan-grounded: D5/D8/D26/D30; repo-grounded: `research/02-target-operating-model.md`,
`packages/skiller/skills/general/plan-protocol/SKILL.md` §§7–9, `packages/task/commands/plan-{exec,run,close,audit,design}.md`).

## Scope

Task Contract v1 is the single **checked** carrier a session compiles before it mutates
anything and before it emits a final response. It is **generated/validated state with
provenance**, not a second narrative SSOT: every field points at an exact canonical ref
(plan, item spec, package canon, owner instruction), and nothing in it is authored by
restating a rule that already lives somewhere else.

The contract answers exactly two questions with a machine result:

- **May this session mutate now?** → the pre-mutation predicate.
- **May this session declare the outcome done?** → the pre-final predicate.

Both return either `allow` or one typed reason code from a closed enum. Silent pass and
silent skip are not possible outcomes.

This contract seals the schema only. It implements nothing in `packages/task`: the
compiler/enforcement seam that will run these predicates at runtime is P2.2/P2.3, and the
frozen acceptance floors that consume them are P0.3. Owner-intent inference and a new
orchestrator are explicitly out of scope (item P0.2 Scope Excluded).

## Machine carriers

| Artifact | Role |
|:--|:--|
| `root/contracts/task-contract-v1.schema.json` | the schema — closed field set, `additionalProperties: false` everywhere |
| `artifacts/P0.2/task-contract-examples.json` | 11 scenario contracts + 12 single-field negative mutations + declared reason codes + P0.1 corpus coverage |
| `artifacts/P0.2/validate_task_contract.py` | the sole executable owner of both predicates and of the corpus-coverage proof |

## Fields (closed set)

Eleven required fields per D5, plus the two Scope-Included carriers `slice` and
`cold_start`, plus `schema_version`/`contract_id` as identity. No other key is legal.

| Field | Carries |
|:--|:--|
| `version` | `revision`, `content_hash` (sha256 over the canonical payload minus the hash itself), `supersedes` (previous hash or `null`) |
| `goal` | one user outcome + explicit non-goals |
| `must` | hard requirements, each with an exact `source_ref` |
| `never` | prohibitions, each with an exact `source_ref` |
| `done.public_acceptance` | acceptance predicates, each with `scope` (`public`/`internal`), a `check` and an `evidence_ref` |
| `authority` | class, whether it is granted and by what, auto-allowed actions, stop boundaries, loop budget, observed rounds |
| `next` | one executable next step: semantic `form`, `carrier`, `context`, `origin`, `changed_by` |
| `route` | required vs actual `model_class`/`effort` + required capabilities with their support level |
| `evidence` | exact paths, each with a P0.1 proof class and the algorithm that produced it |
| `portability` | tier, execution inputs, provenance-only refs, privacy/minimization, one semantic carrier + provider renderers |
| `conflicts` | winner/loser refs with their carrier class, the rule applied, the resolution, and one scoped question when unresolved |
| `slice` | which keys go to a subagent, which stay at the root session |
| `cold_start` | plan/item id, the evidence reads and the carrier a cold session needs |

## Version, content hash and supersedes

`version.content_hash` is **recomputed, never trusted as written**: sha256 over
`json.dumps(payload, sort_keys=True, separators=(",",":"), ensure_ascii=False)` where
`payload` is the whole contract with `version.content_hash` removed. A declared hash that
does not match is `VERSION_HASH_MISMATCH` — the contract is not a valid input to any
boundary. A revised contract records the previous hash in `supersedes`, so a subagent
report is attributable to exactly one contract revision.

## Precedence ladder and the conflict result

Carrier classes, highest authority first. A conflict resolves in favour of the lower rank
number; a lower carrier may **narrow safety but never widen authority** (plan §2).

| Rank | `carrier_class` | Example |
|--:|:--|:--|
| 0 | `owner-instruction` | latest explicit owner instruction, within its own scope |
| 1 | `plan-decision` | a D-entry / frozen contract of the plan |
| 2 | `item-spec` | the item's approved Scope Included / Implementation Rules |
| 3 | `package-canon` | `plan-protocol` SKILL, `packages/task/commands/*` |
| 4 | `handoff-carrier` | `handoff.md` Next, roadmap launch block |
| 5 | `incidental-diagnostic` | something noticed on the way |

A conflict whose declared winner does not outrank its loser is
`CONFLICT_PRECEDENCE_VIOLATION` — this is the machine form of "a stale handoff carrier may
not redefine the approved scope". A conflict with `resolution: "unknown"` is
`CONFLICT_UNRESOLVED`: the contract preserves both refs verbatim and emits **one scoped
question**, it does not guess. Both refs stay in the record after resolution — provenance
of what lost is part of the contract.

## Authority classes

- `routine` + `granted: true` — the class covered by the standing delegation (here: D50
  `G-EXEC` for self-host P0–P3). Routine implementation, tests, close and the next ready
  item need no separate approval.
- `owner-gate` + `granted: false` — the mutation is irreversible or visible outside (tag,
  push, release, fleet, consumer repositories, FOREMAN outward parts). Pre-mutation returns
  `AUTHORITY_BOUNDARY`; the session assembles the packet and stops. The boundary is
  "cannot be rolled back / visible outside", not a competence boundary.

`authority.loop_budget` makes the audit cap a **runtime transition** instead of prose:
`observed_rounds` above `audit_rounds_max` returns `LOOP_BUDGET_EXCEEDED` before the next
mutation, and `same_finding_max` is the same rule for a repeating finding (a third
same-finding event is an incident, not a fourth fix loop — D9).

## Public acceptance and the P0.1 proof class

`done.public_acceptance` must contain at least one entry with `scope: "public"`: an
internal byte/hash-green result alone can never produce a final response
(`ACCEPTANCE_NOT_PUBLIC`). Every acceptance entry resolves to a declared evidence id
(`EVIDENCE_REF_UNKNOWN` otherwise), and every **public** entry must resolve to evidence
whose proof class is `recomputed` or `cross-checked`.

`pinned-not-recomputable` and `unknown` evidence may ground a hypothesis and may be carried
as labelled context, but it can never satisfy a deterministic acceptance predicate
(`EVIDENCE_PROOF_CLASS_INSUFFICIENT`) — D30 and
`root/contracts/source-evidence-verification-v1.md` § Consumers, enforced here rather than
restated.

## Portability

`portability.tier` is the compiled form of D26:

- `brief-acceptance` — simple, low-risk, single-session work: the committed brief and its
  acceptance list are sufficient; `execution_inputs` may be empty.
- `committed-bundle` — multi-session, high-risk, handoff or audit work: at least one
  execution input is required (`PORTABILITY_INPUT_MISSING` otherwise).

An execution input is a repo-relative path that is either `committed` or
`produced-by-predecessor` **with a named producer**. Anything absolute, `~`-rooted,
parent-escaping, `tmp/`-rooted, URL-shaped, or already listed in `provenance_only` is
`PORTABILITY_EXTERNAL_INPUT`: host, chat, mAInd, `tmp/` and foreign repositories are
provenance, never execution inputs. `privacy` records minimization and the excluded
classes (raw bodies, chain-of-thought, tool payloads, secrets).

`semantic_carrier` plus `provider_renderers` keep one neutral SSOT with provider
projections: a rendered Claude or Codex invocation never becomes the source of truth
(D12/D24).

## Pre-mutation predicate (ordered; first failure wins)

| # | Reason code | Fires when |
|--:|:--|:--|
| 1 | `VERSION_HASH_MISMATCH` | declared hash ≠ recomputed hash |
| 2 | `CONFLICT_UNRESOLVED` | any conflict `resolution: "unknown"` |
| 3 | `CONFLICT_PRECEDENCE_VIOLATION` | declared winner does not outrank the loser |
| 4 | `NEXT_CHANGED_WITHOUT_TRANSITION` | `origin: diagnostic`; or `typed-finding` without `changed_by`; or `approved-goal` carrying a `changed_by` |
| 5 | `PORTABILITY_EXTERNAL_INPUT` | an execution input is host-bound/provenance-only |
| 6 | `PORTABILITY_INPUT_MISSING` | `committed-bundle` with no inputs; predecessor-produced input without a producer |
| 7 | `ROUTE_UNDERSHOOT` | actual class or effort below required (one axis never compensates the other) |
| 8 | `CAPABILITY_UNSUPPORTED` | a required capability is not `native`/`adapted` |
| 9 | `LOOP_BUDGET_EXCEEDED` | `observed_rounds` above the declared budget |
| 10 | `AUTHORITY_BOUNDARY` | `owner-gate` not granted |
| 11 | `SLICE_INCOMPLETE` | slice partition not exact/disjoint/covering |
| 12 | `COLD_START_INCOMPLETE` | reads reference undeclared evidence, or the cold-start carrier differs from `next.carrier` |

**Diagnostic cannot author Next.** A diagnostic outside Goal may raise a typed finding; only
a typed finding with an explicit `transition` may move `Next`. This is the machine form of
corpus case `wrong-scope-return`.

## Pre-final predicate (ordered; first failure wins)

| # | Reason code | Fires when |
|--:|:--|:--|
| 1 | `ACCEPTANCE_NOT_PUBLIC` | no acceptance entry has `scope: public` |
| 2 | `EVIDENCE_REF_UNKNOWN` | an acceptance entry references an undeclared evidence id |
| 3 | `EVIDENCE_PROOF_CLASS_INSUFFICIENT` | a public acceptance entry rests on `pinned-not-recomputable`/`unknown` evidence |

The pre-final predicate is evaluated only when pre-mutation allowed; otherwise it reports
`n/a` (a blocked session has nothing to declare done).

## Root / subagent slice

The eleven payload keys are partitioned exactly once, disjointly:

- **subagent slice** — `goal`, `must`, `never`, `done`, `authority`, `next`, `route`,
  `version`. The version hash travels with the slice so the returned result is attributable
  to one revision.
- **root only** — `evidence`, `portability`, `conflicts`. Conflict resolution and
  portability decisions are never delegated: a subagent receives a resolved contract, not
  the resolution problem.

Any missing, overlapping or extra key is `SLICE_INCOMPLETE`.

## Cold-start payload

`cold_start` carries `plan_id`, `item_id`, the evidence `reads` and the `carrier`. Its
carrier must be byte-identical to `next.carrier` — a session that hands off a different
"where we left off" string than its own declared Next is exactly corpus case
`missing-launch-block-intra-session`, and it fails closed even inside one session.

## Context values and their provider projection

The neutral values are the three of `plan-protocol` §8. The Russian literals in
`packages/task/commands/*` are projections of the same three semantics:

| Neutral (`next.context`) | Command-file literal |
|:--|:--|
| `same-session — item` | `continue (/clear) — ручной item` |
| `cold-start — orchestration` | `NEW SESSION — Workflow-оркестрован` |
| `cold-start — plan-step` | `NEW SESSION — шаг-не-item` |

The two carriers currently spell the same enum differently. This contract picks the neutral
SKILL values as canonical and records the projection here rather than choosing silently;
converging the literals is enforcement work owned by P2.2, not by this item.

## P0.1 corpus coverage

Every `kind: critical` case of the committed corpus is mapped to an exact field and an
exact check, and the mapping is machine-verified by the validator (`--corpus`):

| Corpus case | Field | Check |
|:--|:--|:--|
| `missed-consumer-cold-start` | `done.public_acceptance[].scope` | `pre-final:ACCEPTANCE_NOT_PUBLIC` |
| `missing-launch-block-intra-session` | `cold_start` + `next.carrier` | `pre-mutation:COLD_START_INCOMPLETE` |
| `wrong-scope-return` | `next.origin` + `next.changed_by` | `pre-mutation:NEXT_CHANGED_WITHOUT_TRANSITION` |
| `five-audit-loop` | `authority.loop_budget` + `authority.observed_rounds` | `pre-mutation:LOOP_BUDGET_EXCEEDED` |
| `honest-http-clean-control` | — (declared control) | never scored as a failure |

## Consumers

P0.3 freezes measurable acceptance against this contract; P2.1–P2.4 implement the single
compiler/enforcement seam that runs these predicates at transitions; P2.5/P3.3 prove them;
P3.1 links contract identity into the unified trace; P4.3 documents the result. No consumer
may cite a `pinned-not-recomputable`/`unknown` fact as satisfying a deterministic acceptance
predicate.
