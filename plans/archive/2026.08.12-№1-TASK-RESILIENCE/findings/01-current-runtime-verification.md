# P0.1 — Current runtime verification

**Verified tree:** `28f2d2b2d39bddac3ab11e290d07511f26db9807`
**Method:** required roadmap carriers were compared with current `packages/task` and
`packages/harness` source; focused runtime tests were then run against the same worktree. The final
P0 audit finding was reproduced and repaired before this carrier was refreshed.
No previous candidate verdict was used as proof.

## Focused observations

| Roadmap carrier | Current seam | Current verdict | Exact remainder |
|:--|:--|:--|:--|
| `roadmap/2026.08.10-adaptive-plan-governance.md` | `task.plan_gates.phase_candidate_fingerprint()` excludes repository HEAD from the material digest and `task_contract` caps audit rounds. | Partial | There is no computed `review_requirements` carrier tying one scoped review to a material trigger, evidence freshness and reuse policy. |
| `roadmap/2026.08.11-local-repair-vs-escalation-classifier.md` | `journal.RESULT_VALUES`, `plan_item_state.OBSERVATION_RESULTS` and `plan_blocking.evaluate()` keep local repair and unconfirmed block candidates nonterminal. | Partial | No closed all-five local-repair evidence carrier records path, classifier predicates, pre/post validation and bounded diff; enforcement for a repair outside declared `Files` is absent. |
| `roadmap/2026.08.11-codex-effective-route-observability.md` | `route_evidence.capture_actual()` rejects populated `self-attested` evidence; `plan-run` accepts explicit `cli-flag` launch provenance. | Open | Codex still exposes no immutable thread-bound model+effort evidence. `cli-flag` is launch provenance, not effective-thread telemetry, so independently observed routing remains unavailable. |
| `roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md` | `phase_candidate_fingerprint()` hashes terminal item specs/states and declared product files while keeping `observed_repository_head` outside the digest. | Partial | The explicit `spec anchor → product anchor → closure anchor` graph, collision refusal and product-byte identity check are not implemented. |
| `roadmap/2026.08.11-terminal-final-continuity-receipt.md` | `task.plan_delivery.build_terminal_receipt()` refuses nonterminal state and binds journal, state, closure, handoff and plan digests. | Partial | Provider transport does not enforce the receipt against the actual final signal and has no Task-owned quiet/heartbeat/interrupted-resume lifecycle. |
| `roadmap/2026.08.11-terminal-handoff-recommendation-receipt.md` | `task.plan_delivery.verify_receipt()` compares exact persisted `Next` and recommendation with current handoff bytes. | Partial | No Codex/harness hook compares the emitted terminal transcript with that receipt before marking the run complete. |
| `roadmap/2026.08.11-plan-views-history-cli-contract.md` | `plan-views.py history --item P0.1` renders stdout. | Open | The declared `--stdout` form still exits nonzero because the parser rejects `args.stdout`; generated callers and help are not aligned on one interface. |
| `roadmap/2026.08.11-roadmap-batch-selection-is-authoritative.md` | No execution-batch schema, resolver or admission reason code exists in current Task source. | Open | A single-item invocation is not checked against a durable roadmap batch before journal start; no batch receipt/checkpoint preserves ordered continuation. |

The machine-readable full matrix, including every owner requirement, is
`artifacts/P0/roadmap-gap-matrix-v1.json`.

## Owner-intent verification

- Numbered plan identity is implemented in `plan_lint_checks.common` and
  `plan_lint_checks.parsing`: new dated plans require `YYYY.MM.DD-№N-CODE`, a positive daily
  ordinal and matching `Title = План №N — …`; historical IDs remain readable.
- Fully qualified `PLAN-ID Pn.m` references are stated in plan-protocol, but current Task lint
  does not scan arbitrary product comments/docstrings for bare item references.
- External block candidates are fail-closed in `plan_blocking.evaluate()`: verified nonempty
  RAG evidence and an `isolated-child-return` reviewer distinct from the executor are required
  before `terminal-block`. The schema does not prove that a specifically required Perplexity
  call succeeded, and journal has no `rag-pending` observation result.
- Layout v1 remains executable in current commands and readers, while `plan_migrate` still
  exists. Therefore the owner-ordered fleet migration and v1 reader removal are real P1 work,
  not a completed candidate assertion.
- The active plan is Layout v2 and remains active; release tag and registered-project rollout
  are intentionally absent until P6.

No unresolved owner decision remains. D12 records the owner-authorized remediation and the
AUDIT-CAP close path; each open roadmap remainder still has an owning phase and deterministic
acceptance in the JSON matrix.

## Owner-authorized final-audit remediation

The final P0 audit reproduced four existing plan-relative `Files` as constant `missing` rows in
the phase candidate snapshot. Commit `28f2d2b2` preserves repository-relative resolution first and
falls back to the plan directory, so both declared path classes bind actual bytes. The regression
test changes one plan-relative and one repository-relative product independently and requires both
mutations to change the public `phase_candidate_fingerprint()` result. On the repaired tree, all six
declared P0 product rows resolve as `file`; none remains `missing`.

## Execution-gate defects discovered and repaired during P0.1

- Task Contract initially returned `pre_mutation=allow` and
  `pre_final=block:ACCEPTANCE_NOT_PUBLIC`. The committed Validation redirects JSON output to
  `/dev/null`; `task_contract.build()` classifies a check containing an external absolute path as
  internal acceptance. Repair requires changing the stable P0.1 spec or the compiler contract,
  neither of which belongs to this item's declared `Files`.
- After the start event made P0 active, plan lint exposed missing P0.2/P0.3 bundles. Their owning
  generator refuses the declared full plan-prefixed inputs as `unresolvable_entry`: current
  `plan_weight.path_candidates()` returns no candidate for a backticked path whose plan segment
  contains Unicode `№`. Repair belongs to the future item specs or the path parser, not to the
  P0.1 evidence deliverables.

Root repaired both bounded plan defects in `bbcff1bf`: P0.1 Validation no longer uses the external
redirection; P0.2/P0.3 plan-owned inputs are relative and the P0.3 acceptance-bank input declares
`producer: P0.2`. Under the delegated generator authority, P0.1 carriers were regenerated and the
P0.2 cold-start bundle was produced. A first lint rerun then exposed that the bundle gate ignored
`pending-producer` and demanded P0.3's bundle before P0.2 had produced its declared acceptance
carrier. Root fixed that owning admission seam and its regression coverage in `7d45c292`; the
authorized P0.2 spec correction now names the same produced carrier in Deliverables and Validation.
The same Task Contract and lint gates are rerun below rather than treating either repair commit as
proof.

## Reproduction

- `PYTHONPATH=packages/task/lib:packages/task/tests python3 -m unittest ...` for journal,
  item state, blocking, delivery, identity lint, gates, route evidence and history: passed.
- `python3 packages/task/scripts/plan-views.py history --plan-dir <plan> --item P0.1 --stdout`:
  failed with `history требует --item и не принимает --all`.
- `python3 packages/task/scripts/plan-views.py history --plan-dir <plan> --item P0.1`:
  rendered the history view to stdout.
