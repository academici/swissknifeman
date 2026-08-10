# P0.1 baseline observations — 2026-08-03

## Verdict

There is no matched numeric incumbent baseline that can support an economic GO today. The manual
and Workflow lanes are `baseline_pending`; the only fully normalized incumbent sample is the
committed `harness-run` fixture wave, and it is `synthetic`. P0.5 must therefore preserve unknown
economics and may use this bundle for schema/reliability/reuse decisions only.

The selection rules were written first in `artifacts/P0/baseline-selection.md`. The normalized
adjudication is `artifacts/P0/baseline-catalog.json`, validated independently by
`artifacts/P0/validate-baseline.py`.

## Evidence inventory

Repository anchor for the inventory: `243d05a8728a4ab0f58ba3c9bcf49a0f269e5b4b`.

### Committed plan journals

`git ls-files 'plans/**/journal.jsonl'` found 8 tracked journals at the anchor. Parsing the exact
`git show HEAD:<path>` bytes yielded 873 valid records, 563 `plan-exec|plan-run` rows with null
`run_id`, and 338 `closed-green|closed-deviations` rows. Across the full committed corpus,
`cost_usd`, `num_turns`, `duration_ms`, and `run_id` are non-null in 0 records. The per-file
SHA-256 anchors are:

| Journal | Records | SHA-256 |
|:--|--:|:--|
| `plans/2026.08.03-ARTIFEX-SUPERVISOR/journal.jsonl` | 17 | `64027eb73e89dc717f84d34aa37a09336da6eb5d34fe53c30d0d087bfe3254a5` |
| `plans/archive/2026.07.18-FOREMAN/journal.jsonl` | 15 | `c6a2c20e271b1f5192aa7a783cdb572f8ff75f099d415a96f079d8b0f6e15060` |
| `plans/archive/2026.07.19-DUAL-PROVIDER/journal.jsonl` | 296 | `7e76282427018a9771f5b14d2a90ef118fb9b309932cf6f07ed4cd5b884c2169` |
| `plans/archive/2026.07.23-FLEET-DUAL-PROVIDER/journal.jsonl` | 48 | `10b67e9803c11c5fa8881f08eb9456d6ded7c84ed17a99a77bf4ceb37547b603` |
| `plans/archive/2026.07.24-AGENT-RELIABILITY/journal.jsonl` | 100 | `f55801b8f500394174852f433e123310653dc22ecdd650b35839c04c744ccfba` |
| `plans/archive/2026.07.25-ECO-OPT/journal.jsonl` | 172 | `44787bbf0ee9cd9b4e16f8499c6c4bb04c39fcb152907ac77ea9b9ccce72c259` |
| `plans/archive/2026.07.29-HARNESS-AGNOSTIC/journal.jsonl` | 103 | `b76e5e017e0b6686405fd024d4925bfd71c9f207a412c49c5aec0bc7952cbdc2` |
| `plans/archive/2026.07.31-SKM-LEAN/journal.jsonl` | 122 | `ffd7070271b417b1cb53cad48e906e4722120c25662a56cbdf52b259266cd4d0` |

The journals prove durable outcomes and friction but cannot be converted into tokens per accepted
slice: no row binds a normalized scope/acceptance hash to structured usage. The 45 terminal green
or deviation rows in the SKM-LEAN journal are retained as reliability history, not treated as 45
matched economic samples.

### Sanitized machine-local run reports

Only aggregate structured fields were read from `.claude/runs/*.json`; no prompt, transcript,
secret, chain-of-thought, cwd value, file name, or environment value was copied. All 30 files
parsed. Their sanitized aggregate is 42,683 input tokens, 1,023,508,310 cache-read tokens,
14,168,213 cache-creation tokens, 4,439,905 output tokens, and 5,467 turns; the canonical aggregate
JSON hashes to `77016852d3097854256ae64cfe818eb8eb0ddc2fbce35f626ef283fbbc9193ba`.
The same reports contain 0 Workflow records and no stable plan-item/scope/acceptance linkage.
They are therefore `ineligible`, not divided by an invented accepted-slice denominator.

### Workflow history

The committed TELEMETRY-OPT synthesis records 15 Workflow invocations across 2 run IDs in the
examined dterema session. It also proves that the terminal notification arrived: the repeated
resumes were iterative in-session script repair, not absence of the Workflow completion signal.
Because the script/gates changed during execution and no committed sanitized per-run usage envelope
remains, this row is `baseline_pending`. Its combined source SHA-256 is
`e2d2b1a0b744305f18f588a5c2ec4f89ae645f55daa2981b091163d0ac4dd93f`.

### Live-driver evidence

The committed P4.6 acceptance report provides a normalized synthetic final wave:

- 2 accepted fixture slices, 2 provider calls, 0 driver interventions, and 0 retries in the final
  accepted wave;
- 77 turns, 309,897 ms, and USD 1.8969 from the structured worker envelopes;
- token fields unavailable, preserved as `null` with `unknown_reason`;
- source SHA-256 `d8436d1ac746cd24c3405d15363f2b844f0e1b9500b0f1f08c401492851bc036`;
- fixture scope SHA-256 `a7a6253aa88f603798652da41f4c7f0d7a9554d2173450c33a04f2f87346c62b`;
- normalized validation/acceptance SHA-256
  `6478145cbe3383338fcd1411e7c814c05498f1a0eb55901fd6732206558bd255`.

The earlier failed fixture-spec attempt is excluded because its acceptance input changed before the
successful wave. It is not silently pooled as a retry. This evidence proves the driver loop, not a
battle-wave economy floor.

## Harness reuse and gap verdict

| Capability | Reuse verdict | Exact evidence or gap |
|:--|:--|:--|
| phase queue and route refusal | reuse | `harness.run.plan_reader` already orders a phase and drives only literal `Exec=plan-exec` |
| fresh worker process | reuse | `harness.run.worker` launches one `claude -p` item at a time with timeout |
| deterministic post-run gate | reuse | `harness.run.gate` combines outcome, lint, Git topology, and terminal item fields |
| per-plan journal backstop | reuse | `harness.run.journal` writes only when the worker cannot complete close protocol |
| wave summary | reuse with extension | accepted/attention/red, interventions, cost, duration, and client versions already aggregate |
| Codex worker parity | gap | the committed driver launches Claude only |
| durable resume/reconcile | gap | no snapshot/hash reconciliation or unknown-third-state refusal exists |
| retry/idempotency policy | gap | the driver has no retry tiers or side-effect idempotency keys |
| decision and owner-gate machine | gap | the driver produces results but does not package/resolve owner decisions |
| budget/circuit-breaker enforcement | gap | no durable token/cost budget gate controls dispatch |
| isolated write lanes/integration | gap | execution is serial in one worktree; no worktree ownership/integration protocol exists |

Conclusion: reuse the queue, worker-process seam, gate, journal backstop, and summary concepts. Do
not rename `harness run` to Workflow or treat it as an Artifex candidate. P1/P2 must add durable
state, recovery, authority, budget, provider parity, and isolation around the reusable seams.

## Exact accrual conditions

No further run is launched by P0.1. A candidate may leave `baseline_pending` only when one immutable
run supplies all of the following under the same source anchor: repository and plan hashes,
provider/model class/effort, scope hash, validation/acceptance hash, terminal accepted-slice count,
input/cache/output/reasoning tokens where the provider reports them, cost if provider-reported,
turns, duration, provider calls, retries, and owner interventions. A journal row and sanitized run
report must be linked by a stable trace/session/run identifier; prose adjacency is insufficient.

Lane-specific accrual conditions:

- manual: P5.1 must preselect the work and immutable hashes before the owner launches it; the
  manual close journal and sanitized provider envelope must share the same trace/session identity;
- workflow: the preselected immutable script/run ID must retain the same scope and acceptance
  hashes, and a terminal notification plus sanitized provider metrics must be committed as an
  aggregate; a changed script begins a new candidate;
- harness-run: the driver must execute preselected non-synthetic work with a non-null run ID and
  the same hashes/route; the worker envelope and journal backstop must reconcile without a third
  state.

Until those predicates hold, P5 economic comparison remains NO-GO-by-unknown rather than zero-filled.
