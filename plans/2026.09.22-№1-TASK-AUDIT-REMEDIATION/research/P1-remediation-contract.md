# P1 remediation contract

## Practical execution decision

The ledger is a reference, not a demand for 100% formal proof. Implementation is
one product-hardening stream with four outcomes, tested on real work as it lands:

| Order | Outcome | Findings used | Practical proof |
|:--|:--|:--|:--|
| 1 | Stop false success: exit status, transported context, batch continuation, runtime validation and Task CI tell the truth. | N-01, N-02, N-04, N-05, N-13 | Focused exploit regression + happy path + one Corex task. |
| 2 | Stop self-authorized or replayed work: owner evidence is honestly a workflow guard unless a real provider trust channel exists; activation and replay state are durable. | N-03, N-06, N-10, N-11, N-14 | Focused forgery/replay regression + one Agentools task. Do not build a signing system merely to satisfy the audit. |
| 3 | Make history trustworthy enough to recover: serialize terminal append, reject corrupt history, validate basic dates/metrics and acknowledge durable writes honestly. | N-07, N-12, N-15, N-16, N-17 | Focused concurrency/corruption tests + lifecycle smoke; no exhaustive crash proof on every filesystem. |
| 4 | Keep bundles inside the boundary: policy-owned minimization and complete path classification/containment. | N-08, N-09 | Focused sensitive/path regressions + one Edufy task. |

P6 reconciles the three real runs and removes ideas that did not improve behavior.
It does not repeat every unit test or run a synthetic evaluation campaign. A slice
is done when the representative bad path fails safely, the valid path still works,
the package suite is green, and its real task either completes or stops with the
correct actionable reason.

## Status and frozen boundary

This contract turns the reproduced ledger into five owning iterations. It does
not authorize implementation outside each referenced item. The ledger found no
`not-reproduced` rows, so every claim has exactly one code-owning phase; P6 owns
cross-cutting consumer semantics and field evidence, not duplicate fixes.

Global invariants:

1. A declared command, caller assertion, local hash or structurally valid carrier
   is not runtime evidence, observed fact, authenticated origin or durable state.
2. Security-labelled owner authorization requires a trust channel outside the
   constrained agent principal. Without it, protected action fails closed; local
   reversible workflow is honestly labelled a workflow guard.
3. Authoritative state is activated once, last, under one lock domain. Views,
   bundles and status pages are reconstructable projections.
4. Every rejection exposes a stable reason category while logs retain detail.
5. Schema/CLI tightening is versioned or staged. Compatibility never means
   silently restoring the defective acceptance path.

Deliberately deferred unless real field behavior demands them: cryptographic
provider attestation infrastructure, a journal hash chain, broad telemetry
analytics, statistically significant field samples, and cross-filesystem crash
certification. The plan records these as boundaries, not hidden acceptance work.

## Coverage matrix

| Iteration and executable specification | Owned claims | Exact change surfaces | Acceptance contract | Compatibility / rollback boundary |
|:--|:--|:--|:--|:--|
| P2 — [`phases/P2/P2.1.md`](../phases/P2/P2.1.md) | N-01, N-02, N-04, N-05, N-13 | `task_contract` CLI/stage semantics and validation receipts; `plan_context` byte binding; batch receipt derivation; Task CI/Ruff job. | CLI subprocess matrix; chunk mutation matrix plus exact reconstruction; mandatory/recommended prefix parity derived from terminal evidence; declared/non-zero/stale validation receipts block; seeded Task test and lint failures fail CI. | Keep `check` a full gate and add stage-specific commands; version chunk/batch/validation envelopes; add CI job without weakening existing jobs. Rollback may reduce matrix breadth or old-schema diagnostics, never allow final/block to exit zero or caller-owned completion. |
| P3 — [`phases/P3/P3.1.md`](../phases/P3/P3.1.md) | N-03, N-06, N-10, N-11, N-14 | Provider attestation contract; plan-level prepare/verify/activate transaction; mandatory durable commitment/response state in enforced mode; claimed/observed/verified action model. | Forged local transcripts/env, missing fields, replay, expiry and subject mismatch reject; failure before activation exposes no grant; concurrent materialization yields one activation; cumulative scope and duplicate response work across processes; observed-risky beats claimed-safe. | Preserve transcripts as diagnostics and an explicit stateless evaluator. Protected actions fail closed; reversible local paths may opt into labelled degraded workflow mode. Envelope/store backends can roll back behind the same exact action and unique-consume semantics. |
| P4 — [`phases/P4/P4.1.md`](../phases/P4/P4.1.md) | N-07, N-12, N-15, N-16, N-17 | Typed decision resolution for exceptions; journal lock/read/check/append/durability; strict journal schema and chronology; calendar-valid decisions; shared no-follow durable projection writer. | Proposed/rejected/superseded/unrelated grants reject; malformed history blocks; parallel terminals produce one row or conflict; strict UTC/finite/non-negative/integer values; valid/invalid calendar cases; crash and symlink tests for journal/projections. | New writes are strict; legacy data receives a report/migration path, never fail-open parsing. Projection/hash-chain enhancements may be rolled back independently, but lock, corruption refusal, no-follow and acknowledged-durability semantics remain. |
| P5 — [`phases/P5/P5.1.md`](../phases/P5/P5.1.md) | N-08, N-09 | Frozen `BundleInputPolicy/v1`; manifest/path resolver; full execution-input representation; independent privacy and portability lint; containment/symlink/special-file checks. | Sensitive bytes reject regardless of declaration; duplicate/absolute/traversing/outward-link/special entries reject; POSIX, drive, UNC, URI, home/env externals remain visible and reject; minimal regular in-root bundle passes. | First run scanner report-only against legacy bundles, then enforce. Policy exceptions are owner-controlled, typed and narrow. Rollback individual allowlist entries, never let bundle authors define their own exclusion/minimization policy or drop external inputs. |
| P6 — [`phases/P6/P6.1.md`](../phases/P6/P6.1.md) | Cross-cutting consequences for N-01…N-17 | Stable public reason taxonomy; prompt/docs/policy wording; consumer migration notes; the pinned real-project paired protocol. No duplicate runtime repair. | Every repaired negative maps to `schema-invalid`, `evidence-missing`, `evidence-stale`, `evidence-forged`, `policy-denied`, `conflict`, `corrupt-state` or `durability-failed`; real tasks show behavioral evidence, not only lint/form. | Add machine-readable codes before changing prose. Unknown-code consumers retain generic failure. Roll back copy or aliases, never collapse distinct failure semantics needed for safe recovery. |

All claim IDs from the verified ledger occur in the P2–P5 ownership rows exactly
once; P6's range notation is deliberately consumer-wide rather than ownership.

## Iteration contracts

### P2 — contract truth and CI

Dependencies: P1 terminal GREEN only. It must not depend on the future owner gate.

Implementation boundary:

- Separate `check-mutation` and `check-final` semantics if needed, but retain
  `check` as a backwards-recognizable full gate where any block is non-zero.
- Bind every chunk's logical path, member digest, offset, actual byte length and
  exact content to the immutable snapshot, then hash reconstructed members.
- Compute completed batch prefix from matching current-plan terminal events; bind
  plan, membership, routing/spec and terminal identities into the receipt.
- Compile validation clauses as `declared`. Only a versioned runtime receipt bound
  to command, contract, repository state and result may promote proof.
- Add Task tests and Ruff coverage as an explicit required workflow job.

Non-goals: provider authentication, journal storage redesign, privacy policy.

Stop rules:

- Existing production caller requires exit-zero for a full-gate block and cannot
  migrate in the same item.
- A chunk/receipt schema consumer cannot be identified or safely versioned.
- CI branch requirements are externally frozen and adding the job needs owner or
  hosting authority.

### P3 — trust, activation and durable authority

Dependencies: P2 evidence schemas and full-gate semantics. The implementation may
use P4's durable primitive only if P4 has landed first; otherwise P3 owns a narrow
private primitive that P4 later consolidates without weakening guarantees.

Trust decision:

- Current Codex/Claude transcript and environment evidence is diagnostic only.
- A security boundary requires provider-issued proof whose signing/issuance secret
  and nonce store are inaccessible to the agent principal. The exact envelope
  binds issuer, subject/session/turn, command arguments, cwd, plan/item, action
  digest, issued/expiry time, nonce and schema/adapter version.
- If no such provider capability exists, security-labelled protected actions are
  denied. The project may retain local transcript matching only under a public
  `workflow-guard` mode that makes no authentication claim.

Activation protocol:

1. Acquire the plan authority lock and reread authoritative state.
2. Verify the exact provider envelope, freshness, nonce and observed action.
3. Prepare owner message/decision/projections in staging and validate them.
4. Atomically consume nonce/response and publish one activation record last.
5. Sync acknowledged state; rebuild derived views after activation as needed.

Non-goals: proving a human identity from same-principal files, making projections
authoritative, inferring safety from caller vocabulary.

Stop rules:

- Provider cannot issue proof outside the agent trust domain: choose fail-closed
  or the explicitly degraded workflow guard, never an invented security claim.
- No durable atomic uniqueness mechanism is available for nonce/response consume.
- Trusted diff/carrier analyzers cannot observe a predicate: route it to approval.

### P4 — authoritative history and durable projections

Dependencies: P1. Coordinate the durable write primitive with P3, but do not make
journal correctness depend on provider attestation rollout.

Implementation boundary:

- Resolve exceptions through parsed decisions and require accepted, current,
  item/plan/target/field-bound typed grants.
- Put read, corruption check, idempotency check and append inside one exclusive
  lock; malformed non-empty authoritative history is `corrupt-state`.
- Append with no-follow/open flags, complete writes and file/directory sync. Define
  event identity/conflict behavior and use the same lock domain for sidecars.
- Validate strict UTC timestamps, finite non-negative numbers, integral turns and
  start/terminal ordering. Parse decision dates as real calendar dates.
- Use regular same-directory temporary files, file sync, atomic replace, directory
  sync and no-follow checks for projections; concurrent generation serializes.

Non-goals: automatic repair of corrupt history, rewriting legacy journal content
without a separate migration, making reconstructable views source-of-truth.

Stop rules:

- Filesystem cannot provide the required lock/no-follow/sync behavior: return an
  explicit unsupported/durability failure, not success.
- Existing invalid legacy data needs destructive mutation or ambiguous inference:
  produce a report and obtain a separate migration decision.

### P5 — frozen bundle and input policy

Dependencies: P2's evidence and receipt versions are useful but not required for
the path resolver. No dependency on P3/P4 authority redesign.

`BundleInputPolicy/v1` minimum contract:

- Policy, not bundle/caller, defines forbidden sensitive classes and any narrow
  allowlist. `minimized=false` always fails enforced lint.
- Manifest logical names are normalized relative POSIX names: no absolute path,
  `..`, duplicates, empty names or platform reinterpretation.
- Each input survives compilation with original logical spelling plus classified
  kind; external inputs are evidence of a violation, never omitted.
- Canonical resolution must remain below the bundle/root, with every path
  component checked against symlink escape. Only expected regular files are read.
- The detector covers POSIX absolute, Windows drive/UNC, file URI, home/env forms
  and lexical-internal/canonical-external links.

Non-goals: content redaction as a substitute for minimization, accepting devices
or links because their current bytes look safe, mutating consumer repositories.

Stop rules:

- A legacy bundle cannot be classified deterministically: quarantine/report it.
- A required sensitive class needs an exception: owner must add a typed, scoped
  policy rule with a negative test and expiry/review point.

### P6 — observable semantics and field proof

Dependencies: P2–P5 terminal GREEN. P6 consumes their real public behavior.

Reason codes are stable machine output; prose can elaborate but cannot replace
them. At minimum:

| Code | Meaning | Retry / recovery expectation |
|:--|:--|:--|
| `schema-invalid` | Input cannot be interpreted under the selected version. | Fix input/version; blind retry is useless. |
| `evidence-missing` | Required evidence was never supplied/executed. | Produce evidence, then retry. |
| `evidence-stale` | Evidence is validly formed but bound to old state/time. | Recompute on current state. |
| `evidence-forged` | Origin/binding/authenticity verification failed. | Do not reuse; investigate producer/trust path. |
| `policy-denied` | Verified facts do not authorize the action. | Requires changed action or authority, not retry. |
| `conflict` | Competing authoritative state already exists. | Read winner and reconcile. |
| `corrupt-state` | Authoritative carrier cannot be parsed/verified. | Stop mutation; repair through a separate audited path. |
| `durability-failed` | Operation cannot truthfully acknowledge persistence. | Treat as unknown outcome and reconcile before retry. |

P6 must run the separate field protocol verbatim. Structural lint proves form
only; acceptance requires observable differences on real repository tasks plus no
regression on their task-specific validation.

## Non-code candidate gate

A prompt, workflow text, documentation or policy change is eligible only with a
row containing all of the following:

| Required field | Rejection criterion |
|:--|:--|
| Defect evidence | Reject if it cites only preference, style, or an old audit. |
| Mechanism | Reject if no causal path from current text/policy to observed behavior is named. |
| Exact candidate surface | Reject broad “improve prompts/docs”; name file, section and intended delta. |
| Observable change | Reject if the result cannot be seen in a real task decision, reason code, artifact or recovery path. |
| Real task/project class | Reject synthetic-only examples; identify applicable Corex, Agentools or Edufy task class. |
| Negative control | Reject if the candidate can “pass” with unchanged behavior or by self-report. |
| Compatibility/rollback | Reject if consumers, aliases and removal/reversal criteria are absent. |

These rules prevent P6 from turning runtime defects into wording-only fixes while
still allowing prompt/docs changes where they cause and measurably correct a real
behavioral failure.
