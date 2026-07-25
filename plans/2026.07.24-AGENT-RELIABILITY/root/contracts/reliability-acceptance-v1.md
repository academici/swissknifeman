# Reliability Acceptance v1 (P0.3)

RAG:— (plan-grounded: D10/D15/D16/D30/D50/D53/D59; repo-grounded:
`root/contracts/source-evidence-verification-v1.md`, `root/contracts/task-contract-v1.md`,
`artifacts/P0.1/verification-report.json`, `packages/skiller/lib/skiller/quality/eval.py`).

## Scope

This contract freezes **what «good» means** for `2026.07.24-AGENT-RELIABILITY` before any
behaviour mutation (D16): the fixed case bank, the deterministic graders, the frozen floors,
the baseline layers each floor resolves against, and the correction procedure. It is the
acceptance side of the two frozen P0 contracts: Task Contract v1 says what a step must carry;
this one says what the system must measurably achieve.

It implements nothing in `packages/*`. P0.4 and every later behaviour-changing item are
blocked until this freeze is recorded as a D-entry — the G0 gate, which the agent records
itself (D50).

## Machine carriers

| Artifact | Role |
|:--|:--|
| `artifacts/reliability-bank-v1/cases.json` | the frozen bank: 31 cases, their fixtures, assertions, floors, diagnostics, sample seed |
| `artifacts/reliability-bank-v1/graders.json` | grader/operator vocabulary and grading policy (no LLM judge) |
| `artifacts/reliability-bank-v1/run_bank.py` | the sole executable owner: schema validation, probes, grading, metrics, floors, manifest |
| `artifacts/reliability-bank-v1/baseline-results.json` | the layer-1 baseline result, regenerable byte-for-byte |
| `artifacts/reliability-bank-v1/bank-manifest.json` | the freeze: hashes of all four files plus the source inputs, counts, floors, layer-1 metrics, seeded sample, `content_hash` |

## The bank

31 cases — 25 `critical`, 6 `control` — inside the D10 range of 20–50. Families come from
`research/03-metrics-and-experiment.md` plus the P0.3 Code Guidance list: requirement
retention, approval economy, premature stop, cold start, consumer acceptance, finding class,
loop depth, loop budget, provider path, identity uniqueness, handoff carrier, routing (×2),
hook integrity (×3), scope control, portability (×3), provider neutrality, capability,
generated-artifact versioning, trace, evidence proof class, and six controls.

Every case carries a task input, an environment fixture, the critical constraint, expected and
forbidden actions, deterministic assertions, and a layer-1 baseline record.

**Graders are deterministic only.** Eight operators (`event_present`, `event_absent`,
`event_order`, `event_count_max`, `event_count_min`, `outcome_field_equals`,
`outcome_list_contains`, `outcome_list_excludes`) over a structured transcript/outcome record.
There is no model call in the grading path, and a judge may never override a deterministic
critical assertion (D15). This follows the rule the registry eval harness already applies
(`packages/skiller/lib/skiller/quality/eval.py`: `ASSERTION_TYPES` is deterministic by
construction, LLM judging is a separate non-gate mode).

## Two baseline layers, named so neither can be mistaken for the other

- **layer 1 — declared baseline (frozen by this item).** Each case carries the recorded
  pre-change behaviour. Its provenance is one of three classes and is *executable*, not
  asserted: `corpus-observed` (a committed P0.1 corpus case), `bundle-observed` (a committed
  source-evidence runtime/precomputed snapshot), `absent-control-derived` (a control that
  provably does not exist in the repository yet). 48 probes over repository bytes prove those
  claims; `run_bank.py baseline` refuses to produce anything if one of them stops holding.
  Where a check *does* exist as library code but has no session-boundary caller
  (`CMD_ROUTE_UNDERSHOOT`, `CMD_CAPABILITY_UNSUPPORTED`, `cold_start_scope` in
  `packages/task/lib/task/command_render.py`), the case proves **both** — the library presence
  and the caller absence — instead of claiming the check does not exist.
- **layer 2 — live paired baseline (produced at P3.3).** The same cases and graders re-run
  live on the pre-plan tree `artifacts/P0.1/pre-plan-sha.txt` (D45). Every *relative* floor
  resolves only against layer 2.

Layer 1 is a deterministic grade of declared behaviour, **not** a measurement of live model
runs — stated here rather than left to be discovered. Its job is to fix the case set, the
graders and the direction of the failure before any repair exists.

## Frozen floors

Fourteen rows. Thirteen carry §8 of `plan.md` verbatim (with the D53 qualifier); F14 is added
by the agent under D50 and named as an addition, not smuggled in.

| ID | Metric | Floor | Scope | Measurement owner | Baseline source |
|:--|:--|:--|:--|:--|:--|
| F1 | `critical_requirement_retention` | `== 100%` | critical bank | bank | layer-1 |
| F2 | `premature_stop_count` | `== 0` | critical bank | bank | layer-1 |
| F3 | `redundant_approval_count` | `== 0` | critical bank | bank | layer-1 |
| F4 | `effective_semantic_identity_collisions` | `== 0` | объявленная фикстура P1.4 (D51/D53) | P1.4 | item measurement |
| F5 | `hook_reference_resolution` | `== 100%` | controlled fixtures | P0.4 | item measurement |
| F6 | `trace_completeness` | `≥ 99%` | controlled bank | P3.2/P3.3 | layer-2 |
| F7 | `first_pass_success` | `≥ 95%` | весь банк | bank | layer-1 |
| F8 | `first_pass_success_delta_vs_paired_baseline` | `≥ +30 pp` | парный прогон | bank | layer-2 |
| F9 | `context_input_per_success_ratio` | `≤ 50%` | парный прогон | bank | layer-2 |
| F10 | `owner_intervention_ratio` | `≤ 25%` | парный прогон | bank | layer-2 |
| F11 | `same_finding_loop_depth.median` | `≤ 1` | весь банк | bank | layer-1 |
| F12 | `same_finding_loop_depth.p95` | `≤ 2` | весь банк | bank | layer-1 |
| F13 | `critical_regression_escape` | `== 0` | critical bank | bank | layer-1 |
| F14 | `false_block_rate` | `== 0` | control bank | bank | layer-1 |

**F14, added beyond §8 (D50/D59).** §8 contains no guard against curing the failure modes by
blocking everything. A control case blocked by a candidate must fail acceptance exactly like a
missed critical case; without F14 a maximally conservative implementation would score green on
all thirteen other rows.

**Diagnostic, not a floor (D42/D53).** A live host where the curated `core` unit and a donor
bucket are enabled at the same time yields a diagnostic row with a non-empty `safe_owner_action`
(owner: P1.5). The plan does not change the user-owned enabled set, so this cannot be a floor.

### The proof-class rule, enforced rather than restated

No floor may rest on a `pinned-not-recomputable` or `unknown` quantity (D30). Two specific
quantities are named and excluded by construction: `journals.classified_lifecycle_events` (550)
with its `outcomes` breakdown, and the `dedup_correction` totals (135 110 000 corrected input
tokens and siblings). They stay in the manifest as `pinned_context_only` — labelled context.

This is machine-checked: `run_bank.py` refuses any floor that declares a `pinned_inputs` entry
or whose `evidence_refs` name an assertion the P0.1 report classes as
`pinned-not-recomputable`. Consequently F9 (context input) and F10 (owner intervention) take
their denominators from the layer-2 paired run, never from the historical pinned totals, and F6
takes its denominator from the controlled bank rather than from the 550-event historical
completeness.

## Correction procedure (D15)

A wrong grader or a wrong case is corrected by bumping `bank_version` **and**
`grader_version` and rerunning **both** sides. A candidate-only threshold change, a
candidate-only grader change, and any post-hoc floor relaxation are forbidden. `run_bank.py
candidate` refuses to write into the frozen `baseline-results.json` and refuses a partial run
(missing case ⇒ fail closed).

The probes make the freeze self-invalidating in the right direction: once P2 lands the
compiler/enforcement seam, `absent-control-derived` probes stop holding and `baseline` refuses
to regenerate — layer-1 becomes historical by construction rather than by discipline.
`run_bank.py verify` still re-checks hashes and re-grades deterministically on any tree, and
reports probe drift explicitly instead of silently.

## Consumers

P0.4 (blocked until the G0 D-entry), P1, P2 and P3 read this contract and the manifest.
P2.5 and P3.3 run the bank as the paired end-to-end gate; P3.5 renders the terminal verdict
against these floors; P4.3 assembles the Owner packet. No consumer may cite a
`pinned-not-recomputable`/`unknown` fact as satisfying a deterministic acceptance predicate.
