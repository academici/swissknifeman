# Execution: orch → v2

This P07.Z log records the execution behavior retained, rewritten or retired from
`../swissknifeman`; it does not import donor packages or delete donor files.
The [phase verification record](../architecture/execution.md#p07z-verification-record)
is **complete under the owner's incremental validation procedure** on revision
`a1162f16bfc5f20e786833748f1e49b6056f7393`; the former blocked status is cleared.
The final requested chain exited 0: repaired recovery/janitor files passed
(the separate exact-count confirmation reports 39 passed in 108.57 s), e2e
reports 25 passed / 17,635 deselected in 874.68 s, and source/tools Pyright each
report 0 errors and 0 warnings. Earlier formatting, lint, links, schema and
376 architecture passes are retained; the owner reports 16,188+ non-PG passes.
This is cumulative evidence, not a new complete full-suite run. The earlier full
PG result (1,086 passed, 2 failed, 1 skipped) remains historical: the two failed
files now pass, while the extensions skip is disclosed and never counted as a
pass. Exact provenance and the historical test-typing diagnostic are in the
architecture record. Independent documentation review is `not_requested`.

## Source provenance and interpretation

In the normal repository layout the donor is `../swissknifeman`. That relative
path does not exist beside this isolated worktree. The read-only donor inspected
on 2026-11-17 is `/home/vostrikov/projects/packages/swissknifeman`, HEAD
`4170498110ccbdf147d9335cfe6d44a2a075a1c8`. In the tables, `orch/` means
`<donor>/packages/orch/lib/orch/`; other `packages/` paths are donor-relative.
These are source coordinates, not broken worktree-relative Markdown links.
No donor tests were executed and no donor files were modified.

Normative inputs for this port were the porting guide, the orch legacy inventory,
execution model §§13–14, and the execution owner §§16–18. Current behavior is
[execution](../architecture/execution.md) and [`modules/execution/`](../../src/skm/modules/execution/).
The inspected donor's `packages/orch/docs/conductor.md` headings `Stops`,
`Beacons`, and recovery describe the old contract; its line positions have moved
relative to the older spec citations. v2 owner contracts take precedence over
donor compatibility. The donor's characterization goldens are scenario sources,
not byte-for-byte expected output for v2.

## Paths and retained semantics

| Donor source | v2 path / boundary | Disposition and behavior |
|---|---|---|
| `orch/conductor/engine.py`, `application/loop.py`, `stages/*.py` | [domain/workflow/](../../src/skm/modules/execution/domain/workflow/), [apply_action.py](../../src/skm/modules/execution/application/apply_action.py), [host/stages/](../../src/skm/modules/execution/host/stages/) | REWRITE-KEEP-IDEA (P07.04.a/b, P07.07.b): versioned workflow data and pure advance decisions; explicit host dependencies; agents cannot decide acceptance |
| `orch/conductor/records.py`, `infrastructure/files.py`, `domain/item.py` | [execution domain](../../src/skm/modules/execution/domain/), [PostgreSQL repositories](../../src/skm/adapters/postgres/execution/), [memory repositories](../../src/skm/adapters/memory/execution/) | REWRITE-KEEP-IDEA (P07.02, P07.05.a–c): typed run/task/attempt/stage/output; one UoW for state, required events and receipts replaces whole-file state rewrites |
| `orch/conductor/infrastructure/lease.py`, `application/recovery.py`, `process.py` | [lease.py](../../src/skm/modules/execution/domain/lease.py), [expire_leases.py](../../src/skm/modules/execution/application/commands/expire_leases.py), [host recovery](../../src/skm/modules/execution/host/recovery.py), [process ownership](../../src/skm/platform/process/) | REWRITE-KEEP-IDEA (P07.06, P07.07): preserve process identity/reap checks; replace mtime fences and checkout/run locks as ownership authority with monotonic DB lease tokens; L1/L2/L3 recovery preserves work conservatively |
| `orch/conductor/infrastructure/work_source_receipts.py`, `commit_stages.py`; `packages/planner/lib/planner/plan/gitops.py` | [integration.py](../../src/skm/adapters/git/integration.py), [integration slots](../../src/skm/adapters/postgres/execution/integration_slots.py), [reconcile_external_effect.py](../../src/skm/modules/execution/application/commands/reconcile_external_effect.py) | PORT-REFACTOR / REWRITE-KEEP-IDEA (P07.08.a/b): intent before IO, exact immutable request and protected receipt, target slot and CAS. Unknown effects reconcile without replay; trailers are supporting identity only |
| `orch/conductor/checks.py`, `stages/checks_stage.py` | [check runner](../../src/skm/adapters/checks/command.py), [host checks](../../src/skm/modules/execution/host/checks.py), [check domain](../../src/skm/modules/execution/domain/check_execution.py) | PORT-REFACTOR (P07.03.a, P07.07.a): required/manual/advisory states, exact-output evidence, bounded command execution with closed stdin, server-side scope/sealing |
| `orch/conductor/stages/review.py`, `stages/triage.py`, `domain/fix_brief.py`, `review_batch.py` | [acceptance.py](../../src/skm/modules/execution/domain/acceptance.py), [fix_brief.py](../../src/skm/modules/execution/domain/fix_brief.py), [review_grouping.py](../../src/skm/modules/execution/domain/review_grouping.py) | PORT-REFACTOR (P07.03.a, P07.04.b): preserve finding identity, attention/deviation and bounded correction; post-integration acceptance releases dependencies; real role/reproduction extensions remain P08.06 |
| `orch/retry.py`, `conductor/domain/semantics.py`, `conductor/heal.py`, `conductor/domain/report.py` | [retry.py](../../src/skm/modules/execution/domain/retry.py), [semantics.py](../../src/skm/modules/execution/domain/semantics.py), [repair.py](../../src/skm/modules/execution/domain/repair.py) | PORT-AS-IS rules with typed/total v2 contracts (P07.03.b): preserve retry ordering and no optimistic semantic drift; deterministic extraction refuses ambiguity; invalid form retries the same role under admission |
| `orch/conductor/prompts/manifest.py`, `context/*.py`, `infrastructure/launch_budget.py`, `usage.py` | [host/context_inputs.py](../../src/skm/modules/execution/host/context_inputs.py), [context public facade](../../src/skm/modules/context/public.py), [budget.py](../../src/skm/modules/execution/domain/budget.py), [renew_lease.py](../../src/skm/modules/execution/application/commands/renew_lease.py) | PORT-REFACTOR (P07.03.b, P07.05.c, P09 context owners): draft/final prompt manifest, pinned inputs; atomically reserve final prompt cost before runtime handoff; settle actual or explicitly unknown usage |
| `orch/conductor/options.py`, `policies/authority.py`, `settings.py` | [execution settings](../../src/skm/modules/execution/settings.py), [policy facade](../../src/skm/modules/policy/public.py), [settings facade](../../src/skm/modules/settings/public.py) | PORT-REFACTOR (P07.01, P07.09): retain monotonic authority narrowing; centralized typed configuration, frozen bundle plus restricted live controls/checkpoint reconfiguration |
| `orch/conductor/cli.py`, `runs.py`, `questions.py` | [CLI commands](../../src/skm/entrypoints/cli/commands/), [execution commands](../../src/skm/modules/execution/application/commands/) | REWRITE-KEEP-IDEA (P07.09): `skm run`, `inbox`, `worker`; command bus transitions and append-only owner answers/manual verdicts replace file-based resume instructions |
| `orch/conductor/health.py`, `application/supervisor.py`, `application/autopilot.py` | [health.py](../../src/skm/modules/execution/domain/health.py), [background services](../../src/skm/background/) | Preserve health distinctions (P07.06); suspicion/unknown telemetry is not kill authority. Full advisor/stall intervention belongs to P08.08; full autopilot to P08.12, not certified by P07.Z |
| Legacy group/planner lifecycle gates | [gates.py](../../src/skm/modules/execution/domain/gates.py), [phase_gate.py](../../src/skm/modules/execution/application/stages/phase_gate.py), [plan_acceptance.py](../../src/skm/modules/execution/application/stages/plan_acceptance.py) | New v2 acceptance model (P07.11): GA1–GA6 and PA1–PA2 over immutable ranges, own-scope followups, phase dependency barrier, retained coverage report |
| `packages/orch/tests/test_characterization.py`, `test_durable_state.py`, `test_resume_receipts.py`, `test_resume_reconcile.py`, `tests/fixtures/conductor/fake_role.py` | [recovery tests](../../tests/recovery/), [M3 e2e](../../tests/e2e/test_m3_execution.py), [execution fixtures](../../tests/fixtures/execution/) | PORT as behavioral specifications (P07.10): real PostgreSQL/bus/artifact paths, fake external subprocess, SIGKILL/reap, unknown effects and fixed-cutoff typed event replay |

The exact assertion names and proof limitations for these boundaries are in the
[invariant map](../architecture/execution.md#acceptance-invariant-map-a1a12),
[worker authority map](../architecture/execution.md#worker-authority-and-final-prompt-reservation),
and [recovery index](../architecture/execution.md#crash-recovery-and-m3-proof-index).
The three environment implementations are
[worktree](../../src/skm/adapters/git/environments/worktree.py),
[existing checkout](../../src/skm/adapters/git/environments/existing_checkout.py),
and [managed clone](../../src/skm/adapters/git/environments/managed_clone.py).
Unlike the donor checkout lock, their ownership/cleanup/recheck boundaries are
explicit; user dirty baseline bytes never become the task's projected commit.

## Stop codes → outcomes and task blocking codes

This is the semantic migration from execution owner §16.1, not an automatic
import function for old runs. An `ErrorCode`, an acceptance/escalation code, a
diagnostic and a `BlockingCode` are different values. A task wait includes refs,
resolver, allowed actions and applicable recheck/deadline fields; a bare legacy
string cannot manufacture those facts. `DROP` removes a legacy mechanism/code,
not the underlying safety condition.

| Legacy stop | v2 outcome / replacement | Task blocking consequence when applicable |
|---|---|---|
| `DEPENDENCY_BLOCKED` | Preserve failed prerequisite identity | `BLOCKED_BY_DEPENDENCY`; owner restart/skip if prerequisite failed |
| `WAITING_DECISION` | `WAITING_FOR_ANSWER`, CLI exit 4 | `WAITING_ANSWER` with current decision request |
| `ITEM_BLOCKED` | Escalation payload `ITEM_BLOCKED`, task `awaiting_decision` | `WAITING_OWNER` |
| `REVIEW_LIMIT` | `REWORK_LIMIT_REACHED`, bounded escalation | `WAITING_OWNER` |
| `RUN_TIMEOUT`, `TOKEN_BUDGET` | `BUDGET_EXHAUSTED` with wall/token dimension; pause according to policy | `BLOCKED_BY_BUDGET` |
| `TOKEN_BUDGET_UNMETERED` | `BUDGET_EXHAUSTED(reason=unmetered)` under `block`; otherwise charge configured estimate | `BLOCKED_BY_BUDGET` if blocked; unknown usage is never zero |
| `BRIEF_TOO_LARGE`, `PROVIDER_CONTEXT` | `CONTEXT_OVER_BUDGET` | Refusal/escalation; no new task blocking enum named after this error |
| `OUTSIDE_MODULE` | `WRITE_SCOPE_VIOLATION` under block policy, otherwise explicit deviation | Policy/owner resolution; acceptance A12 still applies |
| `OUTSIDE_RUNTIME_ARTIFACT` | Excluded runtime paths plus `RUNTIME_ARTIFACT_IN_COMMIT` rejection | No successful integration from contaminated output |
| `CORRECTION_SCOPE_GREW` | Diagnostic plus explicit deviation | Bounded-implementer route remains backlog, not an extra execution role |
| `CHECKS_MUTATED` | `CHECKS_MUTATED` | D13 escalation; distinct from a negative check verdict |
| `GENERATE_FAILED` | Ordinary command check error for generation | Check error path, not an implicit successful retry |
| `GROUP_REVIEW_BLOCKER` | Confirmed findings create followup tasks | Gate/dependency barrier until followups close |
| `GROUP_REVIEW_FAILED` | F5/F6 on `group_review` task | Owner escalation as required by workflow |
| `ROUTE_UNDERSHOOT` | `ROUTE_UNDERSHOOT` admission refusal | Capability/owner resolution without lowering the required floor |
| `SANDBOX_UNAVAILABLE` | `SANDBOX_UNAVAILABLE` | Capability/owner resolution, no silent isolation degradation |
| `RUNTIME_TRANSPORT`, `TRANSPORT_UNSUPPORTED`, `LAUNCH_UNKNOWN` | §16 migration: `RUNTIME_NOT_INSTALLED` / `CAPABILITY_UNAVAILABLE`; actual transient runtime errors retain typed retry semantics | `BLOCKED_BY_CAPABILITY` when no eligible worker/capability; transient retry may use `WAITING_PROVIDER` |
| `LAUNCH_REFUSED` | `CAPABILITY_UNAVAILABLE` | Capability/owner resolution |
| `ROLE_FAILED`, `ROLE_OUTPUT_EMPTY`, `ROLE_OUTPUT_INVALID` | `RESULT_INVALID` after deterministic healing and bounded same-role retry, or `RUNTIME_CRASHED` | Owner escalation after retry exhaustion; no automatic optimistic resume |
| `PROVIDER_AUTH`, `PROVIDER_AUTHZ` | `RUNTIME_AUTH_EXPIRED` / `RUNTIME_FORBIDDEN` | Explicit credential/authority resolution |
| `RUNTIME_FORBIDDEN` | `RUNTIME_FORBIDDEN` | Preserve denial; never infer success from stdout |
| `PROVIDER_QUOTA` | `QUOTA_EXHAUSTED`, reset-aware retry policy | `WAITING_BUDGET_RESET`; retryable provider waits also have `WAITING_PROVIDER` with bounded deadline |
| `MODEL_UNAVAILABLE` | `MODEL_UNAVAILABLE` | Capability/owner resolution |
| `TIMEOUT` | `RUNTIME_TIMEOUT` | Typed retry/escalation with actual/unknown usage settlement |
| `DISK_LOW` | `DISK_LOW`; host prepare/check runtime error then escalation | Space/owner resolution |
| `CONDUCTOR_CRASHED` | Command `INTERNAL_ERROR`; transactional mutation rolls back | No invented successful result; replay committed receipt or retry only uncommitted command |
| `REGISTER_REPORT_INVALID` | `RESULT_INVALID` for registrar result | Same-role form retry/escalation; no separate report-fixer |
| `OPTIONS_INVALID`, `POLICY_UNKNOWN`, `MODEL_CATALOG_UNAVAILABLE` | `CONFIG_INVALID` / `RESOURCE_QUARANTINED` / `CAPABILITY_UNAVAILABLE` according to the failing boundary | Explicit config/resource/capability correction |
| `POLICY_STAGE_UNSUPPORTED` | `SCHEMA_INVALID` when installing workflow resource | Refuse resource; do not silently skip a stage |
| `OPTIONS_UNTRUSTED` | `CONFIG_NARROWING_VIOLATION` | Refuse authority widening |
| `OPTIONS_UNSAFE_PATH` | `REPOSITORY_UNSAFE` / `SCHEMA_INVALID` | Refuse unsafe repository/policy path |
| `STUBS_INVALID` | `RESOURCE_QUARANTINED` | Prompt blocks are versioned resources |
| `WORKTREE_DIRTY` | Legacy stop retired; `existing_checkout` uses `CHECKOUT_MISMATCH` for invalid baseline conditions | Preserve owned dirty baseline via explicit capture; no blanket discard |
| `DETACH_FAILED`, `AUTOPILOT_LAUNCH_CANCELLED` | DROP detach-child protocol | Long-lived services; autopilot lifecycle proof belongs to P08.12 |
| `RUN_BUSY`, `WORKTREE_BUSY`, `QUESTIONS_LOCKED` | DROP file-lock stops | DB serialization and attempt environments; a busy existing checkout is still protected |
| `STAGE_RECOVERY_UNKNOWN` | DROP legacy step-prefix dispatch | Closed StageType recovery, conservative unknown/reconcile or owner path |
| `QUESTIONS_OPEN`, `NOT_WAITING`, `QUESTION_ANSWERED_NOT_RETRIED` | DROP manual continue protocol | Answer drives persisted continuation/advance; unresolved question still waits |
| `GROUP_UNKNOWN`, `GROUP_FOLLOWUP_MISMATCH`, `GROUP_FOLLOWUP_NOT_DONE` | DROP ad hoc group bookkeeping | Typed followup tasks and graph invariants |
| `CURRENT_INPUT_RECEIPT_UNSUPPORTED`, `BRIEF_INVALID` | DROP external brief protocol | Published revision and draft/final context digests |
| `CLAIM_BLOCKED`, `BRIEF_REFUSED`, `PREPARE_REFUSED`, `REGISTER_REFUSED`, `COMMIT_REFUSED`, `WORK_SOURCE_*` | DROP external work-source protocol | Planning and execution share DB/UoW; typed admission/effect refusals remain |
| `STATE_CORRUPT`, `RUN_INVALID`, `STATE_INVALID`, `QUESTIONS_INVALID`, `RECORD_INVALID` | DROP JSON-file state authority | Typed writes, schema validation, DB constraints; recovery does not trust malformed records |

Manual checks, approvals, material waits, recovery and stalls also have explicit
v2 states: `WAITING_MANUAL_CHECK`, `WAITING_APPROVAL`, `BLOCKED_BY_MATERIAL`,
`RECOVERING`, `SUSPECTED_STALL`. `MANUAL_PENDING` is an acceptance reason;
`WAITING_MANUAL_CHECK` is the task wait. `RUN_PAUSED` is a run state, not a task
blocking code. `POLICY_DENIES` is an acceptance reason, while the task policy wait
is `BLOCKED_BY_POLICY`.

The narrower implemented `LEGACY_BLOCKING_CODES` conversion in
[blocking_reason.py](../../src/skm/modules/execution/domain/blocking_reason.py)
maps `WAITING_DEPENDENCIES`, `PREREQUISITE_FAILED`, `WAITING_GROUP_REVIEW` to
`BLOCKED_BY_DEPENDENCY`; `WAITING_ESCALATION`, `REWORK_LIMIT_REACHED` to
`WAITING_OWNER`; `WAITING_INTEGRATION_TASK` to `BLOCKED_BY_INTEGRATION`;
`WAITING_HOST`, `WAITING_CAPABILITY` to `BLOCKED_BY_CAPABILITY`;
`BUDGET_EXHAUSTED` to `BLOCKED_BY_BUDGET`; and `RUN_PAUSED` to no task code.
[test_blocking_reasons.py](../../tests/unit/execution/domain/test_blocking_reasons.py)
checks the closed catalog and migration behavior. This helper is not evidence
that every donor stop above has an automatic persisted-history importer.

Beacons retain diagnostic semantics: `RESULT_HEALED`, `PROVIDER_WAIT`,
`ROUTE_FALLBACK`, budget warnings and triage reproduction diagnostics do not
become fatal task errors. `RUN_ORPHANED` becomes health information; repeated
silence is suspicion, not OS reap proof. `HEARTBEAT_NOT_WRITTEN` and
`CONCURRENT_RUN` retire with the file-heartbeat/single-conductor assumptions.
`RESULT_REPAIRED` / `REPAIR_FAILED` retire with the report-fixer; v2 uses
`RESULT_INVALID`, bounded `result_retry` and semantic-drift rejection.

## Retirement log and remaining owners

| Retired donor mechanism | Replacement / reason | Owner and evidence boundary |
|---|---|---|
| Wide `Conductor.self` and dynamic stage bindings | Pure decision engine plus explicit application/host stages | P07.04/P07.07; [workflow tests](../../tests/unit/execution/domain/test_advance_table.py) |
| `state.json`, `run.json`, `progress.jsonl` as authoritative state; mtime recovery fences | Atomic state/events/receipts, DB lease generations and server-private continuation; event-only history reconstruction | P07.05/P07.06/P07.10; [command crash](../../tests/recovery/test_command_crash.py), [M3 history](../../tests/e2e/test_m3_execution.py) |
| WorkSource registration/commit bridge and receipt fallback based only on Git trailers | In-process planning facade and exact protected effect journal/receipt; no blind replay | P07.05/P07.08; [effect recovery](../../tests/recovery/test_effect_unknown.py), [slot recovery](../../tests/recovery/test_integration_slot.py) |
| One checkout/run lock as permission to write after a crash | Per-attempt environments, current assignment/slot fences, containment/reap proof before reuse | P07.06/P07.07/P07.10; [worker kill](../../tests/recovery/test_worker_kill.py), [environment tests](../../tests/integration/git/test_environments.py) |
| LLM `report-fixer`, last-JSON-block-wins extraction, optimistic repair | Total deterministic extraction/healing, `Ambiguous`, no semantic drift, same-role retry | P07.03.b/P08.06; [extract tests](../../tests/unit/execution/domain/test_extract_result.py), [repair tests](../../tests/unit/execution/domain/test_repair.py) |
| Parallel hand-merged option layers and untrusted argv/config widening | Central settings registry and monotonic policy ceilings; frozen context/resource bindings | P04/P07.01/P07.09; [context handoff tests](../../tests/unit/execution/application/test_context_two_phase.py) |
| Ad hoc group bookkeeping and accepted-output mutation for findings | Immutable members; gate ranges, own-scope followups and coverage | P07.11; [gate flow tests](../../tests/unit/execution/application/test_gates_flow.py) |
| Detach acknowledgement/nonce files, restart-as-counter-reset | Service lifecycle; explicit session/counter/deadline semantics | P08.12 future acceptance; not certified by the P07.10 service restart test |
| Donor provider catalog and monolithic role process/usage/session stack | Runtime facade and per-provider adapters | P08.03/P08.04/P08.06; M3 fake subprocess is not live-provider certification |
| Silent runtime treated as stalled/killable; speculative cleanup | Suspicion/unknown observation, separately authorized recovery, actual containment proof | P08.08 full intervention; P07.10 proves negative containment cases only when its tests execute |

Retirement means “not carried into the v2 authority model”; this leaf performs no
code removal or mass port. Legacy execution history remains unverified imported
data under P14, not new live runs/leases/acceptance. The previous collection and
formatting findings were repaired by their owners; the final requested chain
passed under the authorized incremental procedure. The
[verification findings](../architecture/execution.md#findings-and-owners) retain
historical skip/test-typing evidence and the G5/J3 interpretation boundary.
Neither this map nor passing executor checks constitute independent review;
independent review of P07.Z documentation remains `not_requested`.
