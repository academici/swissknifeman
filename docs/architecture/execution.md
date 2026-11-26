# Execution

Runs, tasks, attempts and acceptance are implemented in
[`modules/execution/`](../../src/skm/modules/execution/).
[ADR 0013](../adr/0013-deterministic-engine-workflows-as-data.md) and
[ADR 0014](../adr/0014-leases-fencing-environments.md) record the engine and fencing
decisions. This page states the behavior those modules must keep.

## Autopilot interventions and observation

The task live-control view exposes the last 50 incident receipts. Branch A records
technical recovery such as retry or cooldown. Branch B runs a bounded repair through
the task's executor with its frozen policy, write scope, check definitions and
review requirement. The server verifies `REPAIR_ACTION_DIGEST` before admission.
A required review must be independent and green for the current output.
A changed repair against the same failed stage, or a third repair for the same incident,
opens a Branch C owner decision. Restarting the campaign preserves the receipts.

`skm autopilot pause --stop-after STEP_ID` pauses campaign dispatch immediately.
The named step finishes under its current fence before the run pauses. Human
holds require human release. A coordinator may release its own technical hold.
Command and shell checks run in task binding order. Their optional integer
`expected_exit` defaults to zero.

`skm autopilot follow --cursor-file campaign.json --seconds 60 --lock` records
the workspace event sequence after each rendered event. A new file starts at
the current head. Reusing the file resumes that project and workspace. The lock
defaults to `campaign.json.lock`. An interrupted write can replay the last event.
`skm doctor --autopilot` reports campaign stop conditions and queue problems.
`skm run export RUN --summary` renders the same report as `skm export run RUN --summary`.

Python callers can use an HTTP profile or pass an existing embedded client to
application code. The public operations use the same authorization and idempotency
contracts as the CLI.

```python
from skm.sdk import GetAutopilotStatus, connect

with connect(profile="hub") as client:
    status = client.ask(GetAutopilotStatus(project_id=project_id))
```

## Objects and states

```text
Run → pinned ExecutionBundle → Task → Attempt → StageRecord → Step
                                      └─ Output → CheckExecution / Review → AcceptanceDecision
Assignment + fenced lease deliver work; DecisionRequest waits for an answer.
```

| Object | States / boundary |
|---|---|
| Run | `created`, `ready`, `running`, `waiting`, `paused`; terminal `succeeded`, `failed`, `cancelled` |
| Task | `blocked`, `ready`, `assigned`, `executing`, `checking`, `manual_pending`, `reviewing`, `rework_required`, `awaiting_decision`, `integrating`; terminal outcomes include `accepted`, `failed`, `cancelled`, `superseded`, `skipped` |
| Attempt | `preparing`, `running`, `waiting`, `submitted`, `completed`, `ownership_lost`, `abandoned` |
| Assignment | `available → leased → completed / expired / cancelled` |

Rework creates a new output within the same attempt/environment. A new attempt
gets a distinct environment; old outputs and attempts remain immutable history.
`manual_pending` spends no rework round. Failed checks trigger rework; error,
unknown and waiting require their own retry/escalation behavior.

## Deterministic workflow

Workflows are versioned data with a closed predicate set. Agents propose results;
code performs transitions. The compatible public entry is:

```python
def advance(task: TaskState, history: StageHistory, workflow: WorkflowDefinition,
            policy: ExecutionPolicy) -> NextAction: ...
```

`decide_advance(...) -> ActionDecision` is the single evaluator for action and cause;
`advance` returns its action. The application persists that cause rather than
recomputing an explanation from changed state (E53).

| Stage type | Execution side | Result |
|---|---|---|
| `prepare_environment` | Host worker | Attempt environment and materialized inputs |
| `agent_step` | Host worker | Validated role result |
| `run_checks` | Host worker | Check executions and evidence for the output |
| `agent_review` | Host worker | Review verdict and findings for the output |
| `human_gate` | Control plane | Decision request and wait |
| `acceptance_gate` | Control plane | Acceptance decision |
| `integrate` | Host worker | Serialized Git effect and receipt |
| `advisor_consult` | Host worker | Bounded advice within delegated authority |

The seven roles are scout, executor, reviewer, triager, advisor, researcher and
registrar. Profile variants do not introduce roles (E15). Result healing repairs
form only: it cannot drop blockers, questions or findings, lower severity or raise
status. Ambiguous extraction is an error. Result-form retry is bounded and uses
resume only when session admission permits it (E29/E41).

## Acceptance and integration

Acceptance requires a current owned output for the correct task/run/revision,
all required checks passed, manual verdicts passed, required review on that exact
output, explicit handling of deviations/blockers, available evidence, live policy
permission and budget compliance. Self and waived reviews need their declared
evidence/reasons. The evaluator returns every unmet condition.

`AcceptanceDecided` precedes integration. Terminal `TaskAccepted`, dependent-task
release and attempt completion occur only after integration and required
`rerun_after_integration` checks (E26). Rechecks use an SKM-owned detached worktree,
including for `existing_checkout` (E40). Integration serializes repository/branch
writes with host pinning, fencing and conditional ref updates. Default strategy
is squash, default commit mode is `final_only`. Exact immutable Git requests,
journals and receipts govern reconciliation; trailers are cross-checks (E44).
Push and PR remain separate approved effects.

## Worker, budgets and recovery

Claim → renew lease → persist BeginStage before work → run → record result/evidence
with fencing → settle budget. Every worker mutation checks assignment, attempt,
worker and fencing token in the same transaction. Stale results return `LEASE_LOST`.

| Condition | Required behavior |
|---|---|
| No runtime start before lease loss | Reassign the same attempt on its environment host |
| Runtime started; same host proves reap | Resume the same attempt/environment |
| Reap/ownership cannot be established | Lose ownership; create a new attempt with explicit patch handoff |
| External effect outcome unknown | Reconcile journal/receipt and observed fact; never blindly repeat |
| Runtime started before interruption | Settle partial or unknown usage; do not release its reservation |
| Manual wait | Persist request and continuation; do not consume rework |
| Silence or unknown telemetry | Notify/snapshot; no destructive recovery without separate authority/proof |

Budget reservation is atomic before admission. Settlement records actual usage
even if it exceeds the limit; later admission blocks and pauses according to policy
(E10/E27). Missing usage is unknown, never zero. Checks receive closed stdin.

E57 persists a bounded server-private continuation atomically with semantic
changes. Claim delivers the selected stage without applying rework/counters again;
stage creation consumes it atomically. Pause, release and receipt expiry do not
erase pending work. E55 limits reconfiguration to a drained checkpoint and fixed
allowlist. Autopilot restart preserves counters/deadline unless a new session is
explicitly requested; owner pauses are never automatically resumed (E24).

## Readiness and proof

Start requires fresh readiness inputs, pinned configuration/resources and typed
work policies. A selected subset includes its required dependency closure;
plan acceptance belongs only to a full run (E25). Structural declarations in P00
are not proof of these behaviors. M3 includes recovery, causal history,
continuation interleavings and end-to-end execution through P07.10/P07.Z.

## P07.Z verification record

M3 executor validation is **complete under the owner's incremental validation
procedure**, on branch `p07z-impl`, final checked revision
`a1162f16bfc5f20e786833748f1e49b6056f7393`. The former blocked status is cleared.
Only this document and the [porting log](../porting/execution.md) are changed by
P07.Z. Product repairs were integrated by their owners before the worktree was
rebased. P07.09 and P07.10 are recorded as
implemented with upstream review; independent review of this documentation is
still `not_requested`.

The owner explicitly authorized retaining earlier checks and rerunning repaired
files plus the remaining gates. This is cumulative evidence across revisions,
not a claim that a single full `make check test-pg e2e` invocation passed on the
final revision. Commands ran in the foreground without shell background jobs,
`sleep`, or log-following loops. PostgreSQL checks used `SKM_REQUIRE_PG=1` and
`SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test`.

| Check | Evidence and provenance |
|---|---|
| `uv sync --frozen` | Exit 0 during initial P07.Z environment setup |
| `make fmt-check` | Exit 0; 1,901 files already formatted; retained from the earlier checks, including revision `8b348a9c7a41057a15762c869e0697e863994c13` |
| `make lint`, `make docs-check`, `make schema-check` | Each passed in the earlier authorized checks; retained after owner-integrated repairs |
| `make arch` | 376 passed in 134.14 s on `93210a40503a0c36cf9f75e8be54a06f299e912e`; 29 file-size warnings; no skipped architecture tests |
| `make test` / non-PG closure | On `93210a405`: 16,185 passed, 3 failed, 1,096 deselected, 282 subtests passed in 2,363.58 s. The only remaining failures were malformed-hook-URL cases; the repaired file subsequently passed 11 tests, 11 deselected in 15.16 s on `8b348a9c7`. The owner reports 16,188+ non-PG tests passing and authorized carrying this evidence forward; no new complete non-PG run is claimed here |
| Full `make test-pg`, prior revision | On `bd0c1efb0d41eea6071611ccae2f3aade252fe05`: 1,086 passed, 2 failed, 1 skipped, 16,571 deselected in 2,769.48 s; this invocation exited 2 and is retained as historical evidence, not relabelled as passing |
| Repaired PG/recovery and janitor files | Final requested chain on `a1162f16b`: exit 0 for `pytest -q tests/recovery/test_concurrency.py tests/unit/background/test_janitor_outbox_gc.py`; a separate narrow confirmation retained the exact summary: **39 passed in 108.57 s**, exit 0, no skips |
| `make e2e` | Final chain: exit 0; **25 passed, 17,635 deselected in 874.68 s**, no skips; includes the real M3 DAG/history test |
| `uv run --frozen pyright src/skm` | Final chain: exit 0; 0 errors, 0 warnings, 0 informations |
| `uv run --frozen pyright --project tools/pyrightconfig.json` | Final chain: exit 0; 0 errors, 0 warnings, 0 informations |
| Earlier `uv run --frozen pyright tests/ --outputjson` | Historical diagnostic: 706 errors, 0 warnings across 576 files on the original baseline; not rerun or declared repaired by source/tools typing. Test typing was not part of the final requested chain |

The final requested `pytest ... && make e2e && pyright src/skm && pyright --project
tools/pyrightconfig.json` chain returned **exit 0**. The additional narrow run
above was solely to recover an exact retained test count; passing e2e and typing
checks were not repeated.

### Findings and owners

The previous full PG run's single skip remains explicit:
`tests/contracts/extensions/test_repositories.py:291`, reason
`the triggers of 0018 exist only in PostgreSQL`. It is not counted as a passed
check. No skip was reported in the final targeted or e2e runs. The full PG suite
was not repeated, as instructed by the owner; its historical skipped branch is
not retroactively certified by the targeted checks. Owner: P09.01.a.

Earlier collection, formatting, worker disk-admission, hook logging, execution
receipt, race and janitor findings were returned to their owners. The last two
PG failures were the publication/trash race's rejection-code set (P07.10) and the
janitor's transaction-count expectation (P03.05.b); their files now pass the
39-test confirmation. The M3 DAG now passes in e2e. Test typing remains a historical
follow-up for the respective test owners, not a source/tools typecheck success.

The G5/J3 interpretation boundary remains: exhausted lease recovery can fail with
`LEASE_LOST`, while an owner answer requesting an unavailable new attempt
escalates `ATTEMPTS_EXHAUSTED`. These distinct paths must not be described as a
uniform pause-plus-decision outcome. Owners: P07.04.b / P07.06 / P07.10.

No product source or test file was modified by this documentation update.
Executor self-review is separate from independent review (`not_requested`);
passing executor checks do not constitute an independent review verdict.

## Acceptance invariant map: A1–A12

This index maps implementation and test assertions to the cumulative validation
evidence above; it does not imply a fresh full-suite rerun on the final revision.
The normative definitions are the acceptance rules in
[`domain/acceptance.py`](../../src/skm/modules/execution/domain/acceptance.py)
and the rows below. Every A-row below has a
case in [test_acceptance.py](../../tests/unit/execution/domain/test_acceptance.py),
`test_each_condition_blocks_on_its_own[<ID>]`; the combined case is
`test_all_conditions_together_report_every_reason_in_order`.

| ID | Required fact / observed rejection code | Additional assertion in `test_acceptance.py` |
|---|---|---|
| A1 | Current attempt owns the output; lost/abandoned ownership rejects with `ATTEMPT_NOT_CURRENT` | `[A1]` |
| A2 | Output belongs to current attempt/task/run/revision: `OUTPUT_NOT_CURRENT` | `[A2]`; `test_checks_review_and_verdict_of_output_a_do_not_accept_output_b` |
| A3 | Every required check of this exact output passes: `REQUIRED_CHECK_NOT_PASSED` | `test_agent_said_done_without_checks_is_not_accepted`; `test_only_the_latest_round_of_a_check_counts` |
| A4 | Latest manual verdict passes; pending yields `MANUAL_PENDING`, failure `MANUAL_FAILED` | `[A4]`, `[A4-fail]`; `test_manual_pending_is_a_wait_not_a_failure`; `test_pass_then_fail_keeps_both_verdicts_and_fails_acceptance` |
| A5 | Required review is fresh, independent and of this output; self/waived modes carry their evidence | `[A5]` returns `REVIEW_MISSING`; `test_review_of_another_output_is_stale_and_of_another_task_is_missing` returns `REVIEW_STALE` for a stale output; `test_independence_of_the_reviewer`; `test_self_and_waived_clearances` |
| A6 | No unresolved blocker: `BLOCKER_OPEN` | `test_a_blocker_of_an_earlier_round_stays_open_until_resolved` |
| A7 | Attention/open major findings require the applicable human deviation: `DEVIATION_REQUIRED` | `test_attention_needs_a_human_deviation_of_this_task` |
| A8 | Required evidence is available: `EVIDENCE_MISSING` | `test_evidence_not_required_lifts_a8` checks the explicit exception |
| A9 | Live policy permits acceptance: `POLICY_DENIES` | `[A9]` |
| A10 | Budget permits acceptance: `BUDGET_EXHAUSTED` | `[A10]` |
| A11 | Task is current for its revision: `TASK_SUPERSEDED` | `[A11]` |
| A12 | Output stays inside declared write scope: `WRITE_SCOPE_VIOLATION` | `test_outside_write_scope_is_cleared_only_by_an_accepted_scope_finding` |

The context pack's `MANUAL_VERDICT_PENDING` label is not the implemented A4 code;
the assertions and canonical catalog use `MANUAL_PENDING`. A5 has more than one
rejection code; `REVIEW_STALE` alone is not the whole review contract. Acceptance
reasons, task blocking codes and command errors are separate namespaces.

## Phase and plan gates: GA1–GA6, PA1–PA2

Gate acceptance uses an immutable `source=range` output derived from protected
integration receipts, not member stdout or guessed Git trailers. Findings create
new followup tasks with their own scope, budget and acceptance; accepted member
outputs remain immutable. The following selectors are in
[test_gates.py](../../tests/unit/execution/domain/test_gates.py); their validation follows
the cumulative evidence and explicit rerun boundaries recorded above.

| ID | Invariant | Test selector |
|---|---|---|
| GA1 | Every member is accepted, or skipped with a recorded decision | `test_ga1_requires_terminal_members_and_recorded_skip` |
| GA2 | Required checks refer to this gate range and their latest rounds pass | `test_ga2_missing_stale_and_latest_required_checks` |
| GA3 | Manual verdicts belong to the exact check and pass | `test_ga3_manual_verdicts` |
| GA4 | Required review clears this exact range | `test_ga4_required_review_is_of_this_range` |
| GA5 | Confirmed major/blocker findings have closed followups or an applicable deviation | `test_ga5_confirmed_findings_require_closed_followups_or_own_deviation` |
| GA6 | Live policy allows acceptance and range identity is current | `test_ga6_live_policy_and_range_identity` |
| PA1 | Every criterion has evidence from its accepted output: check, review or deviation | `test_pa1_exact_accepted_output_evidence` |
| PA2 | Every requirement is implemented by accepted work; required gaps block | `test_pa1_pa2_block_missing_verification_and_advisory_preserves_gaps` (`REQUIREMENT_UNCOVERED`; PA1 uses `CRITERION_UNVERIFIED`) |

Advisory coverage retains its report and `COVERAGE_GAP`; it does not remove live
policy checks. `test_range_never_guesses_missing_or_inconsistent_receipt` and
`test_range_chain_covers_intervening_receipts_and_rejects_gaps` reject invented
ranges. `test_r13_required_gates_cannot_be_silently_empty` allows `GATE_EMPTY`
only when required checks/review are absent; missing runners otherwise produce
`GATE_UNSUPPORTED_BY_WORKFLOW`. Gates cannot run writable executors
(`test_gate_rejects_writable_executor`).

The corresponding application assertions are in
[test_gates_flow.py](../../tests/unit/execution/application/test_gates_flow.py):
`test_failed_check_blocks_gate_and_followup_has_own_scope_budget_and_identity`,
`test_phase_gate_acceptance_is_durable_and_releases_next_phase`,
`test_done_cannot_skip_required_plan_coverage`, and
`test_all_terminal_gates_finish_run_only_after_plan_acceptance`.
The compiler dependency barrier is independently asserted by
`test_compiler_gate_chain_has_no_orphan_or_cycle_and_failed_phase_holds_dependents`
in the domain gate tests.

## Worker authority and final prompt reservation

The shared [worker guard](../../src/skm/modules/execution/application/_worker_protocol.py)
locks current ownership, verifies registered worker and credential kind, assignment,
attempt and fencing token, and checks lease expiration using authoritative database
time after locks. [Lease tests](../../tests/unit/execution/domain/test_lease_fence.py)
cover each broken condition, token monotonicity and old-claim refusal.

| Boundary | Existing test assertions (see cumulative validation record) |
|---|---|
| Claim identity, BeginStage/renew expiration, release/reissue token | [test_claim_and_fence.py](../../tests/unit/execution/application/test_claim_and_fence.py): `test_claim_rejects_foreign_worker_registration`, `test_expired_lease_cannot_begin_or_renew`, `test_retry_later_reissue_increments_fence_and_old_claim_cannot_begin` |
| Result/seal/failure versus expiry/cancel; clock sampled after lock | [test_worker_protocol.py](../../tests/contracts/execution/test_worker_protocol.py): `test_waiting_command_checks_fresh_database_expiry`, `test_cancel_result_and_failure_settlement_are_serialized`, `test_worker_guard_samples_db_clock_after_run_lock_with_skewed_host` |
| Assignment token scope, per-step binding, revocation without revival | [test_assignment_tokens.py](../../tests/unit/access/application/test_assignment_tokens.py); [test_step_notes.py](../../tests/contracts/execution/test_step_notes.py) binds notes to the runtime step and rejects management credentials |
| Pinned input grants; release revokes access; extension never revives revoked grants | [test_assignment_grants.py](../../tests/unit/execution/application/test_assignment_grants.py): both tests |
| Crash/expiry invalidates the old worker | [test_lease_loss.py](../../tests/recovery/test_lease_loss.py): `test_l1_expiry_preserves_cursor_outputs_and_attempt_charge`; [test_stale_worker.py](../../tests/recovery/test_stale_worker.py): `test_expired_worker_result_is_refused_and_new_fence_records_result` |
| Final prompt reserve replaces draft estimate before runtime admission; refusal commits without starting IO | [test_context_two_phase.py](../../tests/unit/execution/application/test_context_two_phase.py): `test_draft_cannot_start_then_final_manifest_admits_once`, `test_final_prompt_growth_commits_budget_refusal_and_releases_draft`, `test_live_authority_narrowing_blocks_old_final_context` |
| Concurrent reserves and once-only settlement | [test_concurrency.py](../../tests/contracts/execution/test_concurrency.py): `test_reservation_contention_cannot_overspend_limit`; worker protocol: `test_parallel_reserves_and_repeat_settlement_cannot_double_spend` |

`BeginStage`, `RenewLease`, `RecordStageResult`, `SealOutput`,
`ReportAttemptFailure`, `ReleaseAssignment`, `AcquireIntegrationSlot` and
`ReleaseIntegrationSlot` use the shared guard. `RecordStepNote` derives its claim
from the assignment token. Administrative effect reconciliation has its own bound
assignment guard; an ordinary worker assignment cannot submit that result
([test_external_effects.py](../../tests/unit/execution/application/test_external_effects.py),
`test_ordinary_assignment_cannot_submit_admin_result`). Claim validates worker
registration before issuing a lease. This implementation trace is not a claim of
a separate negative regression for every command/credential combination.

`revoke_authority` revokes assignment tokens and input grants together. Release
and lease expiry call this lifecycle; a crashed process loses authority when its
lease expires, not instantaneously at OS death. A bearer token never substitutes
for a current fence. OS reap proof is also required before reusing a writable
environment. Runtime admission checks the final manifest and live authority, then
atomically adjusts the reservation; only after the committed handoff may the host
call the runtime. Started runtimes settle actual/unknown usage; unstarted drafts
release reservations.

## Integration slot and reconciliation proofs

| Invariant | Existing assertions (see cumulative validation record) |
|---|---|
| One holder for `(repository_id, target_branch)`; assignment and slot fences; durable target/run host pins | [test_integration_slot.py](../../tests/unit/execution/application/test_integration_slot.py): `test_slot_lease_tracks_assignment_and_release_preserves_both_pins`, `test_stale_claim_is_rejected_before_slot_mutation`, `test_busy_slot_returns_waiting_code_without_stealing_holder`, `test_local_effect_admissions_are_fresh_and_slot_fenced` |
| Fresh admission precedes Git CAS; old generations and partial publication cannot authorize a successor | [recovery slot tests](../../tests/recovery/test_integration_slot.py): `test_successor_epoch_rejects_paused_old_candidate_before_admission`, `test_slot_change_between_intended_and_executing_refuses_io`, `test_partial_refs_remain_unknown_and_block_next_generation` |
| Protected request/journal/receipt binds effect, tree, parents, ref and generation; trailers alone cannot prove success | [test_push_receipts.py](../../tests/integration/git/test_push_receipts.py): `test_fake_identity_is_not_a_protected_commit_receipt`; recovery slot tests: `test_task_trailer_without_protected_receipt_never_proves_a_green_range`; [test_integration_rules.py](../../tests/unit/execution/domain/test_integration_rules.py) covers SKM identity trailers |
| Lost receipt invokes read-only reconciliation, with no second ref/push IO | Recovery slot tests: `test_db_receipt_loss_reconciles_without_second_ref_io`; push receipt tests: `test_receipt_loss_reconciles_same_push_and_never_repeats_it`; [test_effect_unknown.py](../../tests/recovery/test_effect_unknown.py): `test_unknown_observation_escalates_without_duplicate_effect_or_decision` |
| Acceptance decision precedes integration; dependent tasks wait for required rechecks and terminal acceptance | [test_acceptance_after_integration.py](../../tests/unit/execution/application/test_acceptance_after_integration.py): `test_acceptance_records_decision_then_done_unblocks_after_integration`; [test_recheck_retry.py](../../tests/unit/execution/application/test_recheck_retry.py) exercises retries against the approved tip |

The product commit identity (`SKM-Run`, `SKM-Plan`, `SKM-Revision`, `SKM-Task`,
`SKM-Attempt`, `SKM-Output`, `SKM-Effect`, plus optional review/findings) is separate from this repository's
development `Plan*` attribution trailers. Unknown effects keep their evidence and
block unsafe reuse until `ReconcileExternalEffect` establishes an outcome or
escalates. An observed target tip or a matching trailer alone is insufficient.

## Crash recovery and M3 proof index

The recovery behaviors below map to these real
tests. Recovery-file confirmation and the final e2e run supplement the earlier
PG evidence; the full recovery suite was not repeated on the final revision.

| Fault / boundary | Observable assertion and test |
|---|---|
| Before command commit; after commit before reply | [test_command_crash.py](../../tests/recovery/test_command_crash.py): rollback leaves no state/event/receipt; retry after response loss returns the committed result once |
| BeginStage create/consume and terminal semantic write/event atomicity | Same file: `test_execution_begin_cursor_and_stage_commit_together`, `test_output_seal_event_state_and_receipt_are_atomic`, `test_required_execution_event_failure_rolls_back_its_domain_mutation` (`acceptance-decided`, `external-effect-recorded`) |
| L1: claim/draft lost before runtime start | [test_lease_loss.py](../../tests/recovery/test_lease_loss.py): same attempt, retained outputs/cursor and attempt charge; old claim refused |
| Draft/final boundary, lost Begin response | [test_context_draft_crash.py](../../tests/recovery/test_context_draft_crash.py): replay retains stage, secret binding and draft; runtime not started |
| L2/L3: SIGKILL during real executor | [test_worker_kill.py](../../tests/recovery/test_worker_kill.py): `test_sigkill_worker_recovers_unsealed_bytes_and_reaches_succeeded[unconfirmed/same_host_reaped/different_host]`; same-host reap preserves attempt/environment and partial bytes; otherwise fresh environment, old bytes retained, no invented sealed patch; all branches assert `succeeded` and settled reservations |
| DB terminal state without containment proof | Same file: `test_dead_leader_and_escaped_descendant_never_produce_false_reaped`; PID/leader exit cannot prove descendants quiescent |
| Lost heartbeats and stale/cancelled result | [test_heartbeat_loss.py](../../tests/recovery/test_heartbeat_loss.py), [test_stale_worker.py](../../tests/recovery/test_stale_worker.py): stop admission, suppress late uploads/results, preserve only committed evidence |
| Evidence interrupted before promotion/registration | [test_evidence_upload.py](../../tests/recovery/test_evidence_upload.py): partial upload never becomes check evidence; retry through real blob/application paths |
| Serve restart around paused terminal continuation | [test_serve_restart.py](../../tests/recovery/test_serve_restart.py): persisted advance cursor survives repeated service restarts; resume creates one FixBrief/rework increment, completion one acceptance |
| Claim, publication, upload, cancel and checkpoint interleavings | [test_concurrency.py](../../tests/recovery/test_concurrency.py): numbered concurrency cases, expiry between stages, reconfiguration after drain and parallelism 2→1 without counter reset |
| M3 three-task DAG, fake subprocess, check failure/rework, red review/triage/rework/green, kill/reap and local integration | [test_m3_execution.py](../../tests/e2e/test_m3_execution.py): `test_three_task_dag_reworks_reviews_integrates_and_rebuilds_history`; fresh worker processes, causal dependency release, exact check feedback, different model, common budget, immutable event replay at fixed cutoff |
| Material loss before/after start | Same e2e file: pinned v1 is never replaced by latest v2; material block creates/charges no attempt |
| Manual wait and attempt exhaustion | [test_advance_rework_limits.py](../../tests/unit/execution/domain/test_advance_rework_limits.py): `test_a_manual_check_waits_without_spending_a_rework_round`, `test_a_new_attempt_answer_of_the_owner_needs_an_attempt_left_or_a_raised_limit`; [test_background_commands.py](../../tests/unit/execution/application/test_background_commands.py) covers expiry limits; [test_manual_and_answers.py](../../tests/unit/execution/application/test_manual_and_answers.py) covers durable verdict/answer transitions |

The M3 DAG fixture declares parallel-ready work and one dependent, but its test
drives replacement workers sequentially; concurrent claim/serialization evidence
belongs to the separate contract/recovery race tests. Manual wait and exhaustion
are separate assertions, not steps asserted by that single DAG test. The current
gate cannot certify their combined end-to-end success. Unsealed L3 crash bytes
are preserved as recovery evidence, not falsely advertised as a sealed patch.

All three environment adapters have concrete lifecycle assertions in
[test_environments.py](../../tests/integration/git/test_environments.py):
`test_worktree_prepare_reopen_recheck_remove`,
`test_existing_dirty_baseline_and_output_preserve_user_state`, and
`test_managed_clone_preserves_unpublished_local_tip`. This is a coverage index;
it does not grant production support to untested OS/isolation combinations.
M3 uses a fake external runtime; live provider adapters, full advisor/stall
intervention and autopilot proof remain with their P08 owners.

## Documentation validation and self-review

The final command
`uv run --frozen python tools/check_links.py docs/architecture/execution.md docs/porting/execution.md && git diff --check`
passed (exit 0). An earlier link check found the mistaken `domain/checks.py`
coordinate; it was corrected to `domain/check_execution.py` within this write set.
A read-only AST/source-coordinate audit resolved all 69 named test functions and
all fully qualified donor coordinates in the porting table. It verifies reference
existence, not test execution. The architecture and porting additions were reviewed
for current ownership/fence checks, receipt replay limits, immutable accepted
outputs, cleanup versus effect status, and zero/unknown-budget semantics. The
review retained the sequential-DAG, unsealed-L3 and G5/J3 proof limits explicitly.
This executor self-review is independent of the validation results and does not
change the external review status `not_requested`.
