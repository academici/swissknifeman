# Risk / Review / Loop Budget v1 (P2.1)

RAG:— (plan-grounded: D8/D9/D23/D50/D57/D59 and D64/D66/D68; repo-grounded:
`root/contracts/task-contract-v1.md:96-99`, `root/contracts/reliability-acceptance-v1.md:89-93`,
`packages/task/commands/plan-audit.md:45-58`,
`packages/skiller/skills/general/plan-protocol/SKILL.md` §§6, 9;
synthesis: `research/06-p2.1-contract-boundary.md` §§4.1, 4.3).

## Scope

This contract seals **what a finding is, when it may reopen product, how many times, and who
decides when the budget is spent.** It is the guard vocabulary the execution state machine
branches on and the finding vocabulary two foreign plans already declared they will read rather
than duplicate.

It is a **layer on top of** the frozen P0.2 Task Contract (D64): P0.2 already owns the
`authority.loop_budget` field, `same_finding_max` and the code `LOOP_BUDGET_EXCEEDED`. This
contract owns the semantics those numbers count — the identity of a finding, the reopen
predicate, the review cadence and the SUBJECT of the decision at an exhausted cap.

It seals semantics only; `packages/task/lib/task/review_policy.py` is P2.3.

## Frozen upstream

| Fact | Owner | Source |
|:--|:--|:--|
| `authority.loop_budget`, `audit_rounds_max`, `same_finding_max`, `LOOP_BUDGET_EXCEEDED` as a runtime transition | P0.2 | `root/contracts/task-contract-v1.md:96-99` |
| Authority classes and the G1 wording «cannot be rolled back / visible outside» | P0.2 | `root/contracts/task-contract-v1.md:86-99` |
| F14 `false_block_rate == 0` over the control bank | P0.3 | `root/contracts/reliability-acceptance-v1.md:89-93` |
| Review-depth enum `full` / `light` / `none`, its default and the batching invariant | plan-protocol §9 | `packages/skiller/skills/general/plan-protocol/SKILL.md:963-978` |
| The material/process deviation predicate that separates 🟢 from 🟠 | plan-protocol §6 | `packages/skiller/skills/general/plan-protocol/SKILL.md:356-400` |
| Audit stop rules: scope boundary, severity ≠ verdict, the two-round cap, follow-up as the remediation default | package canon | `packages/task/commands/plan-audit.md:45-58` |

Review depths are **not** re-minted: `full`/`light`/`none` stay `plan-protocol` §9's, and this
contract only binds cadence to them.

## Declared sets (D51/D65)

Three finding types. This is the vocabulary `2026.07.25-ECO-OPT` P9 reads for its
`answer-key.json` `type` field as a foreign surface, so it lives in machine-readable form in
`artifacts/P2.1/state-transition-cases.json` as well as here — a scorer reads data, not prose
(D66).

<!-- declared-set: finding_types -->
```text
product
evidence
process
```

| Type | Effect on a product already proven green |
|:--|:--|
| `product` | may reopen at any severity |
| `evidence` | reopens only when it invalidates acceptance; otherwise it becomes its own record |
| `process` | never reopens; it is recorded in Known Deviations / Pending Work |

Four severities.

<!-- declared-set: severities -->
```text
blocker
major
minor
nit
```

Two authority profiles. The subject of the decision at an exhausted cap is a **parameter of the
profile, not a constant** (D68).

<!-- declared-set: authority_profiles -->
```text
owner-gated
self-host
```

## The reopen predicate

```text
reopens_product(finding) :=
      finding.type == "product"
   OR finding.severity == "blocker"
   OR finding.invalidates_acceptance == true
```

This is the guard the state machine branches on for every `typed-finding` event. Only a branch
whose guard value is `true` may target a repair state; the validator refuses a transition that
reopens product on any other branch (`REOPEN_WITHOUT_PRODUCT_FINDING`). An evidence repair does
NOT re-open a demonstrably green product — the third same-finding event creates an incident, not
a fourth fix loop (plan §2 Execution Rules, D9).

## Finding identity

`finding_id` is derived from the **seam of the defect** — the file, the rule or contract locus,
and the defect class — never from the wording of a report, its severity label, the way a
reviewer split the text, or the reviewer's identity.

| Field | Value |
|:--|:--|
| `derived_from` | `seam` |
| seam fields | `file`, `rule_or_contract_locus`, `defect_class` |
| forbidden sources | report wording · severity label · report section split · reviewer identity |
| `reopen_of` | a finding that re-raises a closed one carries `reopen_of: <finding_id>`; the pair counts as **one** identity against `same_finding_max` |

**Split ban.** Splitting one seam into several reports does not create several identities: the
id is recomputed from the seam, so the cap cannot be evaded cosmetically. This is the load-bearing
half of the budget — with a wording-derived id the cap never trips at all, which is why the
validator refuses any other derivation (`FINDING_IDENTITY_UNSTABLE`).

## Loop budget and cadence

- `same_finding_max = 2` fix rounds. The third occurrence of one stable identity is `INCIDENT`
  with cause, action and verification recorded and **no inline repair**.
- `audit_rounds_max = 2` per phase — the package canon's cap
  (`packages/task/commands/plan-audit.md:52-54`), consumed here, not re-declared.
- Both are runtime transitions, not prose: `observed_rounds` above the declared budget returns
  the frozen P0.2 code `LOOP_BUDGET_EXCEEDED` **before** the next mutation, which the state
  machine's `loop-budget` deny class routes to `INCIDENT`.
- **Validation cadence.** Full validation runs once on the terminal item of a phase; targeted
  checks run after each bounded fix. Audits do not run on bookkeeping steps.
- **Review depth** is `plan-protocol` §9's enum and its rules apply unchanged: default `full`,
  doubt → `full`, and a batch inherits the MAXIMUM risk of its participants. This contract adds
  no depth and overrides no default.

## Authority profiles

| Profile | Subject at an exhausted cap | Source |
|:--|:--|:--|
| `owner-gated` | owner | `packages/task/commands/plan-audit.md:52-54` — the package canon default, and today's behaviour across the fleet |
| `self-host` | agent | `plans/2026.07.24-AGENT-RELIABILITY/plan.md` D50 — the agent closes forks by record; only G1 stays with the owner |

The profile is supplied by the caller and **never inferred**. A cap resolution taken without a
declared profile is `AUTHORITY_PROFILE_UNDECLARED`; the validator additionally refuses a state
machine whose cap-resolution cell is not guarded by the profile at all, because hardcoding
either subject silently rewrites the other carrier.

**`OWNER_BOUNDARY` is orthogonal to the profile.** It is entered only on the G1 boundary —
«cannot be rolled back / visible outside»: tag/push/release, fleet, consumer repositories,
FOREMAN outward parts — and never on a boundary of competence. The transition names the exact
missing authority; a boundary that cannot name one is a defect, not a stop.

## The F14 gate: positive cases are mandatory (D59 п.3)

`reliability-acceptance-v1.md:89-93` sets `false_block_rate == 0` over the control bank
precisely because §8 of the plan contains no guard against curing the failure modes by blocking
everything: a maximally conservative implementation scores green on all thirteen other floors.

Therefore the fixture carries **at least five positive routine cases** whose expected decision is
`continue-next`, and a positive case yielding anything else **fails the item**. A contract that
blocks everything is formally total and practically useless; the corpus control case
`honest-http-clean-control` is retained as the clean bounded control and is never scored as a
failure.

## Boundaries (И1–И3)

| Not touched here | Owner (plan AND item) | Reason | ПРОХОД |
|:--|:--|:--|:--|
| `packages/task/commands/plan-audit.md` and the rest of the package canon | `2026.07.24-AGENT-RELIABILITY` **P2.2** (then P2.3) | the fleet of 17 projects follows this canon; a second writer in the same pass is a race | the canon must say something else → D# + the edit lands in P2.2's Scope, never here |
| `plan-protocol` §9 review depths | **P2.2** | depth is already a closed enum with a default and a batching invariant | a fourth depth is genuinely needed → D# against `plan-protocol`, not a private enum here |
| `root/contracts/reliability-acceptance-v1.md` (F14 and the other floors) | **P0.3** (terminal) | the acceptance bank is frozen; a floor edited by a consumer is a post-hoc relaxation | a wrong floor → D# with `supersedes` and a `bank_version`/`grader_version` bump by P0.3's owner |
| `2026.07.25-ECO-OPT` P9 files | **ECO-OPT P9** | P9 reads this vocabulary as a foreign surface and declares it will not duplicate it | a needed change to the vocabulary → D# here + the `## 7. Contracts` § Exported row; never an edit of their plan |

**Freeze semantics (И2).** Frozen as `v1` at the close of P2.1, extension **additive**: a new
finding type or severity is a **major** bump (every consumer's exhaustiveness breaks), a new
forbidden derivation source or a cadence note is **minor**, wording is **patch**.

## Contribution gate (D23)

- **Existing extension points surveyed first.** `task-contract-v1.md:96-99` already carries the
  budget FIELDS; `plan-audit.md:45-58` already carries the audit stop rules;
  `plan-protocol` §§6/9 already carry the material predicate and the review depths. What none of
  them carries is the **identity** of a finding and the **subject** of the cap decision — the two
  things this contract adds, and nothing else.
- **Named consumers:** `P2.3` (`review_policy.py`), `P2.5` (end-to-end bank), `P3.1` (trace),
  `P4.3` (Owner packet), plus **outside this plan** `2026.07.18-FOREMAN` P2/P5 (retry/escalate
  decisions) and `2026.07.25-ECO-OPT` P9 (`answer-key.json` `type` vocabulary — its
  `research/18-P9-target-design.md:76-88,260-268`).
- **Alternatives considered (≥2).** (a) *Hardcode the owner as the cap subject, as the package
  canon reads today* — rejected: it re-imposes on this plan exactly the manual gate D50 removed.
  (b) *Hardcode the agent, as D50 reads* — rejected: this contract travels into the package canon
  through P2.2 and would silently rewrite the behaviour of a 17-project fleet, an edit of a
  foreign surface without its owner (И2). The profile parameter is the only option under which
  neither carrier overwrites the other.
- **SemVer/ADR result:** new contract at `v1`, additive; `plan-audit.md` keeps its current
  behaviour as the `owner-gated` default, so no existing carrier changes meaning on the day this
  contract freezes. The ADR is this section plus D68.

## Consumers

`P2.3` implements the predicate, the identity derivation and the cap as executable policy;
`P2.5` proves the historical `five-audit-loop` case against it; `P3.1` carries `finding_id` and
the decision output into the unified trace; `P4.3` reports the measured loop depth against floors
F11/F12. `2026.07.18-FOREMAN` P2/P5 and `2026.07.25-ECO-OPT` P9 consume it as a foreign contract,
gated by the terminal phase P2 of this plan (`plans/README.md` § «Кросс-плановая
последовательность»); neither is notified by editing its plan — the carrier is the
`## 7. Contracts` § Exported row (D66, И2).
