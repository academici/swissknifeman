# Contract inventory, part 8

P07.05.b adds the following execution implementation files and generated declarations.
Generated files remain owned by their schemas and `tools/gen.py`; this inventory records the implementation leaf.

## Execution application and domain helpers

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/application/_action_effects.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_admission.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_control.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_events.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_manual_report.py` | Manual verdict report artifact registration | P07.05.b |
| `src/skm/modules/execution/application/_json_report.py` | Generated JSON report retention bound to the attempt | P07.05.b |
| `src/skm/modules/execution/application/_plain.py` | plain (JSON-plain rendering of application values) | P07.05.b |
| `src/skm/modules/execution/application/_primitives.py` | save_attempt, move, attempts_for_run, server_context, budget_accounts, attempt_effect_ids (shared unit-of-work primitives) | P07.05.b |
| `src/skm/modules/execution/application/_json_reads.py` | obj, objects, texts, text, optional_text, integer (typed reads of execution-written JSON) | P07.05.b |
| `src/skm/modules/execution/application/_preview_facts.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_resolutions.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_start_inputs.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/_state.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/apply_action.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/accept_deviation.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/answer_decision_request.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/cancel_run.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/carry_forward_result.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/pause_run.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/reconfigure_run.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/record_manual_verdict.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/restart_task.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/resume_run.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/skip_task.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/approve_revision.py` | Human revision visa issuance | P07.05.b → I-11.1 |
| `src/skm/modules/execution/application/queries/get_revision_visa.py` | Latest revision signature query | P07.05.b → I-11.4 |
| `src/skm/modules/execution/application/commands/start_run.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/commands/validate_for_execution.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/stages/acceptance_gate.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/application/stages/human_gate.py` | Execution control-plane implementation | P07.05.b |
| `src/skm/modules/execution/domain/_reconfiguration.py` | Execution control-plane implementation | P07.05.b |

## Generated command declarations

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/generated/_commands_accept_deviation.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_acquire_integration_slot.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_acquire_integration_slot_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_answer_decision_request.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_answer_decision_request_answer.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_answer_decision_request_defs_json_value.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_autopilot_tick.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_begin_stage.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_begin_stage_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_cancel_run.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_carry_forward_result.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_defs_isolation_profile.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_defs_process_identity.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_defs_process_owner.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_defs_process_ownership.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_defs_staged_blob_ref.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_offer.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_claim_assignment_reaped_steps_item.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_detect_stalls.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_drain_autopilot.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_enforce_timeouts.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_expire_leases.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_mark_environments_removed.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_pause_autopilot.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_pause_run.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_reconcile_external_effect.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_reconfigure_run.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_reconfigure_run_defs_json_value.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_external_effect.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_external_effect_defs_git_commit_receipt.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_external_effect_defs_git_commit_request.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_external_effect_defs_json_value.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_external_effect_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_external_effect_result_variant1.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_manual_verdict.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_evidence_item.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_json_value.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_nullable_counter.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_nullable_digest.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_nullable_utc.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_nullable_version.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_staged_blob_ref.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_observations_item.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_runtime_observation_dto.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_runtime_observation_dto_binding.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_runtime_observation_dto_capture.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_runtime_observation_dto_timing.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_runtime_observation_dto_tools.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_urn_skm_runtimes_runtime_observation_v1_defs_nullable_counter.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_urn_skm_runtimes_runtime_observation_v1_defs_nullable_digest.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_urn_skm_runtimes_runtime_observation_v1_defs_nullable_utc.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_urn_skm_runtimes_runtime_observation_v1_defs_nullable_version.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_usage_report_dto.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_stage_result_usage_report_dto_subagents.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_step_note.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_record_step_note_options_item.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_release_assignment.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_release_assignment_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_release_integration_slot.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_release_integration_slot_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_process_identity.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_process_owner.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_process_ownership.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_staged_blob_ref.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_staged_file.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_progress.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_usage_report_dto.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_renew_lease_usage_report_dto_subagents.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_report_attempt_failure.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_report_attempt_failure_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_report_attempt_failure_usage_report_dto.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_report_attempt_failure_usage_report_dto_subagents.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_request_review.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_request_review_target_variant1.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_request_review_target_variant2.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_restart_task.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_resume_run.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_schedule_ready_tasks.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_changed_path.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_output_manifest.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_output_manifest_diff_stats.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_output_mount.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_staged_blob_ref.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_staged_file.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_seal_output_defs_worker_claim.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_skip_task.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_start_autopilot.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_start_autopilot_limits_variant1.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_approve_revision.py` | Generated revision visa command | P07.05.b → I-11.1 |
| `src/skm/modules/execution/generated/_results_approve_revision_result.py` | Generated revision visa result | P07.05.b → I-11.1 |
| `src/skm/modules/execution/generated/_views_revision_visa_status.py` | Generated revision visa status | P07.05.b → I-11.4 |
| `src/skm/modules/execution/generated/_views_review_roi_view.py` | Generated review analytics view | P07.05.b → I-12.3 |
| `src/skm/modules/execution/generated/_commands_start_run.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_start_run_defs_json_value.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_start_run_selection_variant1.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_stop_autopilot.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_validate_for_execution.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_validate_for_execution_defs_json_value.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_validate_for_execution_scope.py` | Generated execution command declaration | P07.05.b |
| `src/skm/modules/execution/generated/_commands_validate_for_execution_selection_variant1.py` | Generated execution command declaration | P07.05.b |

## Generated event declarations

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/generated/_events_acceptance_decided_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_acceptance_decided_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_acceptance_decided_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_assignment_leased_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_assignment_leased_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_assignment_leased_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_attempt_ownership_lost_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_attempt_ownership_lost_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_attempt_started_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_attempt_started_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_attempt_started_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_autopilot_state_changed_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_autopilot_state_changed_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_autopilot_state_changed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_budget_exhausted_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_budget_exhausted_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_budget_exhausted_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_check_completed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_decision_answered_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_decision_answered_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_decision_answered_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_decision_requested_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_decision_requested_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_decision_requested_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_deviation_accepted_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_deviation_accepted_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_deviation_accepted_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_external_effect_outcome_unknown_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_external_effect_outcome_unknown_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_external_effect_outcome_unknown_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_external_effect_recorded_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_followups_created_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_integration_completed_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_integration_completed_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_integration_completed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_lease_expired_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_lease_expired_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_lease_expired_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_manual_verdict_recorded_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_manual_verdict_recorded_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_manual_verdict_recorded_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_monitor_evaluated_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_monitor_evaluated_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_monitor_evaluated_thresholds_item.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_output_sealed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_readiness_reported_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_readiness_reported_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_readiness_reported_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_recovery_circuit_opened_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_recovery_circuit_opened_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_recovery_circuit_opened_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_review_completed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_review_requested_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_review_requested_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_review_requested_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_cancelled_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_cancelled_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_cancelled_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_created_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_finished_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_finished_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_finished_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_paused_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_paused_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_paused_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_reconfigured_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_reconfigured_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_reconfigured_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_resumed_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_resumed_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_resumed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_started_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_started_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_started_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_waiting_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_waiting_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_run_waiting_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_runtime_start_admitted_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_runtime_start_admitted_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_runtime_start_admitted_step_bindings_item.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_stage_completed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_stage_recovered_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_stage_recovered_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_stage_recovered_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_stage_started_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_defs_nullable_counter.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_defs_nullable_digest.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_defs_nullable_utc.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_defs_nullable_version.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_runtime_observation_dto.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_runtime_observation_dto_binding.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_runtime_observation_dto_capture.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_runtime_observation_dto_timing.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_runtime_observation_dto_tools.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_urn_skm_runtimes_runtime_observation_v1_defs_nullable_counter.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_urn_skm_runtimes_runtime_observation_v1_defs_nullable_digest.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_urn_skm_runtimes_runtime_observation_v1_defs_nullable_utc.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_step_observation_recorded_urn_skm_runtimes_runtime_observation_v1_defs_nullable_version.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_accepted_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_accepted_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_accepted_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_assigned_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_created_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_created_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_created_origin_variant2.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_failed_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_failed_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_failed_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_ready_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_rework_required_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_skipped_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_skipped_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_skipped_defs_json_value.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_wait_changed_defs_cause.py` | Generated execution event declaration | P07.05.b |
| `src/skm/modules/execution/generated/_events_task_wait_changed_defs_entity_ref.py` | Generated execution event declaration | P07.05.b |

## Generated result declarations

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/generated/_results_accept_deviation_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_acquire_integration_slot_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_answer_decision_request_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_autopilot_tick_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_autopilot_tick_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_begin_stage_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_begin_stage_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_begin_stage_result_defs_stage_instruction.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_cancel_run_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_carry_forward_result_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_claim_assignment_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_claim_assignment_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_claim_assignment_result_defs_stage_instruction.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_claim_assignment_result_variant1.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_claim_assignment_result_variant2.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_detect_stalls_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_detect_stalls_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_drain_autopilot_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_enforce_timeouts_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_enforce_timeouts_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_expire_leases_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_expire_leases_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_mark_environments_removed_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_pause_autopilot_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_pause_run_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_reconcile_external_effect_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_reconcile_external_effect_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_reconfigure_run_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_external_effect_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_external_effect_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_manual_verdict_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_stage_result_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_stage_result_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_stage_result_result_defs_stage_instruction.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_record_step_note_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_release_assignment_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_release_assignment_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_release_integration_slot_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_release_integration_slot_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_renew_lease_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_renew_lease_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_renew_lease_result_defs_stage_instruction.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_renew_lease_result_refusal.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_report_attempt_failure_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_report_attempt_failure_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_request_review_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_restart_task_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_resume_run_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_schedule_ready_tasks_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_schedule_ready_tasks_result_scheduled_item.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_seal_output_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_skip_task_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_start_autopilot_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_start_run_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_stop_autopilot_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_validate_for_execution_result.py` | Generated execution result declaration | P07.05.b |
| `src/skm/modules/execution/generated/_results_validate_for_execution_result_defs_json_value.py` | Generated execution result declaration | P07.05.b |

## Generated view declarations

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/generated/_views_attempt_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_attempt_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_autopilot_explain_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_autopilot_explain_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_autopilot_status_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_autopilot_status_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_decision_requests_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_decision_requests_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_execution_environments_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_execution_environments_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_fix_brief_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_fix_brief_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_history_page.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_readiness_report_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_readiness_report_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_review_receipt.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_review_receipt_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_budget_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_budget_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_health.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_timeline_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_timeline_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_run_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_runs_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_runs_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_step_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_step_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_task_attempts_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_task_attempts_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_task_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_task_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_tasks_view.py` | Generated execution view declaration | P07.05.b |
| `src/skm/modules/execution/generated/_views_tasks_view_defs_json_value.py` | Generated execution view declaration | P07.05.b |

## Integrations hook subscription routing and contracts

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/integrations/application/commands/record_hook_delivery_failure.py` | Internal hook delivery failure recording command | P10.08.a |
| `src/skm/modules/integrations/application/commands/retry_hook_deliveries.py` | Dead hook delivery replay command | P10.08.a |
| `src/skm/modules/integrations/application/commands/test_hook_subscription.py` | Control-plane hook subscription test command | P10.08.a |
| `src/skm/modules/integrations/application/queries/list_hook_deliveries.py` | Outbox hook delivery listing query | P10.08.a |
| `src/skm/modules/integrations/application/queries/list_hook_subscriptions.py` | Hook subscription listing query | P10.08.a |
| `src/skm/schemas/integrations/results/list-hook-subscriptions.v1.json` | ListHookSubscriptionsResult contract schema | P10.08.a |
## Fenced worker application

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/application/_stage_agent_helpers.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_stage_preparation.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_worker_budget.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_worker_dtos.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_worker_events.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_worker_evidence.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_worker_host_stages.py` | Server-owned check and review stage facts | P07.05.c |
| `src/skm/modules/execution/application/_worker_inputs.py` | Pinned agent admission and execution context inputs | P07.05.c |
| `src/skm/modules/execution/application/_worker_integration.py` | Validated Git integration receipts and effect settlement | P07.05.c |
| `src/skm/modules/execution/application/_worker_protocol.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/_worker_result.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/begin_stage.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/claim_assignment.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/record_stage_result.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/record_step_note.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/release_assignment.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/renew_lease.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/report_attempt_failure.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |
| `src/skm/modules/execution/application/commands/seal_output.py` | Fenced worker protocol and atomic runtime-start | P07.05.c |

| File | Contract | Owner |
|---|---|---|
| `src/skm/modules/execution/application/commands/schedule_ready_tasks.py` | Background command and bus codec | P07.06 |
| `src/skm/modules/execution/application/commands/expire_leases.py` | Background command and bus codec | P07.06 |
| `src/skm/modules/execution/application/commands/enforce_timeouts.py` | Background command and bus codec | P07.06 |
| `src/skm/modules/execution/application/commands/detect_stalls.py` | Persisted supervisor recovery and internal bus command | P08.08 |

## P07.11 product phase and plan gates

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/domain/gate_range.py` | Immutable receipt bounds and pure Git object proof verification | P07.11 |
| `src/skm/modules/execution/domain/workflow/engine_review.py` | Review, triage, integration and gate decision-table rows extracted to respect the file size ceiling | P07.11 |
| `src/skm/modules/execution/application/stages/phase_gate.py` | GA1-GA6 facts, range validation and control-plane acceptance persistence | P07.11 |
| `src/skm/modules/execution/application/stages/plan_acceptance.py` | PA1-PA2 coverage and retained coverage artifacts | P07.11 |
| `src/skm/modules/execution/application/stages/gate_facts.py` | Read-only gate members, required checks and check definitions | P07.11 |
| `src/skm/modules/execution/application/stages/gate_dispatch.py` | Gate readiness, scheduler and worker boundary facts | P07.11 |
| `src/skm/modules/execution/application/stages/gate_lifecycle.py` | Independent followups, T28/T29 and uncharged gate re-review attempts | P07.11 |
| `tests/unit/execution/application/test_gates_flow.py` | Gate UoW, coverage and re-review regressions | P07.11 |

Executor validation and independent manual review are separate. P07.11 manual review: **changes_requested**
(review session `01a1e37c-a12b-7492-ad4c-59edf2d03e5e`). The executor fixed the three Major findings
(manual-failure transition, required followup review, no-op range bounds); independent re-review is pending.

| File | Responsibility | Owner |
|---|---|---|
| `tests/unit/execution/application/_gates_support.py` | Shared immutable gate/check fixtures for application gate regression tests | P07.11 |
| `src/skm/adapters/checks/registry.py` | Execution environment/check host adapter | P07.07.a |
| `src/skm/adapters/git/environments/existing_checkout.py` | Execution environment/check host adapter | P07.07.a |
| `src/skm/adapters/git/environments/managed_clone.py` | Execution environment/check host adapter | P07.07.a |
| `src/skm/adapters/git/fingerprint.py` | Execution environment/check host adapter | P07.07.a |
| `src/skm/adapters/git/scope_match.py` | Execution environment/check host adapter | P07.07.a |
| `src/skm/adapters/git/status.py` | Execution environment/check host adapter | P07.07.a |
| `src/skm/modules/execution/application/commands/mark_environments_removed.py` | Execution environment/check host adapter | P07.07.a |

## P07.07.b worker host lifecycle

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/host/worker_loop.py` | Capacity slots, fenced stage lifecycle and stop-mode admission | P07.07.b |
| `src/skm/modules/execution/host/heartbeat.py` | Assignment renewal thread, cumulative progress and latched cancellation | P07.07.b |
| `src/skm/modules/execution/host/context_inputs.py` | Two-phase context assembly and pre-spawn manifest finalization | P07.07.b |
| `src/skm/modules/execution/host/stage_client.py` | Assignment-bound narrow worker operations | P07.07.b |
| `src/skm/modules/execution/host/context.py` | Narrow dependencies, budgeted uploads and durable environment locators | P07.07.b |
| `src/skm/modules/execution/host/stages/base.py` | Stage values and bounded local recovery capture | P07.07.b |
| `src/skm/modules/execution/host/stages/registry.py` | Registry of implemented host handlers | P07.07.b |
| `src/skm/modules/execution/host/stages/agent_step.py` | Shared runtime, cancellation and result repair for seven roles | P07.07.b |
| `src/skm/modules/execution/host/stages/agent_review.py` | Review results through the shared agent pipeline | P07.07.b |
| `src/skm/modules/execution/host/reproduce.py` | Read-only triage rejection reproduction runner | P08.06 |
| `src/skm/entrypoints/worker/main.py` | Independent contexts per slot and SIGTERM cancellation | P07.07.b |
| `src/skm/entrypoints/worker/token_rotation.py` | Hourly token checks and atomic client handover | P07.07.b |
| `src/skm/bootstrap/host_services.py` | Host storage ledger, owned reaping and worker factories | P07.07.b |
| `src/skm/bootstrap/worker.py` | Production worker host composition and durable credential rotation | P07.09 |
| `src/skm/bootstrap/worker_runtimes.py` | Worker-local runtime, plugin and account composition | P07.09 · SKM 0.1.0 W01 |
| `src/skm/bootstrap/worker_credentials.py` | Worker SecretRef credential resolution | P07.09 |
| `src/skm/bootstrap/worker_entrypoint.py` | Production worker entrypoint lifecycle wiring | P07.09 |
| `src/skm/bootstrap/worker_rotation.py` | Worker token rotation client wrapper | P07.09 |
| `src/skm/bootstrap/worker_stages.py` | Built-in HTTP worker stages and host-local Git bindings | P11.04.b |
| `src/skm/entrypoints/cli/_run_io.py` | Execution CLI DTO dispatch and identifier helpers | P07.09 |
| `src/skm/entrypoints/cli/_run_logs.py` | Execution CLI attempt and step log rendering | P07.09 |
| `src/skm/entrypoints/cli/_run_worker.py` | Production CLI worker start and lifecycle adapter | P07.09 |
| `src/skm/entrypoints/cli/commands/events.py` | Operator CLI `skm events` dead/retry outbox commands | P07.09 |
| `src/skm/entrypoints/cli/commands/inbox.py` | Operator CLI `skm inbox` decision/approval/verdict commands | P07.09 |
| `src/skm/entrypoints/cli/commands/policy.py` | Operator CLI `skm policy` show/check commands | P07.09 |
| `src/skm/entrypoints/cli/commands/run.py` | Operator CLI `skm run` lifecycle, inspection, and host-local ephemeral sessions | P07.09 → I-08.1 |
| `src/skm/entrypoints/cli/follow.py` | Isolated run event stream follower (`skm run follow`) | P07.09 |
| `src/skm/modules/execution/generated/_documents_stage_outcome_integrate_effect_request.py` | Generated model for integrate `effect_request` schema | P07.09 |
| `src/skm/platform/process/markers.py` | Process ownership marker helpers | P07.09 |
| `src/skm/bootstrap/worker_permissions.py` | Worker admitted policy to runtime path rules translation | P07.10 |
| `src/skm/modules/execution/application/_scheduler_materials.py` | Scheduler material availability assessment helper | P07.10 |
| `src/skm/modules/context/application/prompt_artifact.py` | Atomic guarded staged-prompt publication | P07.07.b |
| `src/skm/modules/context/application/query_dtos.py` | Bus identities for context JSON-mode query/view DTOs | P07.07.b |

Executor validation is recorded separately in the implementation commit. Independent manual review:
**changes_requested** by session `01a1e419-50cc-72d1-81e8-91f962453f2d`: three reproduced Major findings
on runtime ReadOutcome availability, configured host-read limits and transient renewal handling.
Re-review confirmed ReadOutcome and transient renewal fixes, and reproduced a remaining Major: work-chain
limits were read through host-chain config. BeginStage now supplies frozen run limits pinned in step
admission. Executor regressions use real host-chain EffectiveConfig; independent re-review remains pending.

The public facade owns the P09.04.c Phase-B collector, outside bus handlers; the host compatibility export
remains available. The worker supplies attempt-scoped GitCheckoutReader, then uploads the exact
rendered prompt through SkmClient staging. FinalizeManifest checks live ownership before consuming and
registering the staged prompt in the same transaction. Exact replay does not consume the blob again;
revoked claims, foreign workspaces, digest mismatches and altered selections cannot publish a final prompt.
Public WORKER file mutations remain forbidden.

Minimal M3 triage confirms the exact primary findings of the current reviewed output in RecordStageResult.
Rejection and reproduction are outside this minimal path. A later independent review resolves absent,
confirmed findings only when their candidate file bytes changed. Dual-backend integration tests cover
red → confirm → fix → green, actual fake subprocesses and Git snapshots, manual check verdicts, terminal
replay, and invalid triage targets. Admission setup is a test fixture; continuation and persistence are real.
The rebased context query registrations use explicit bus identities for their generated JSON-mode records,
so the actual application registry can start without replacing context or execution handlers. The server
also emits schema-valid review-completed facts with reviewer/output identity and finding counts.

The supplied execution registry also has no handlers for `record_external_effect`,
`acquire_integration_slot` or `release_integration_slot`. The narrow client exposes these wire operations;
no unfinished integration handler is registered by this leaf. Their server registration belongs to P07.08.a.

## P09.10 review requests

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/modules/execution/application/commands/request_review.py` | REQUIRED idempotency, project guards, atomic service revision and review run creation | P09.10 |
| `src/skm/modules/execution/application/queries/get_review_receipt.py` | Project-authorized receipt lookup by run, request, or project/mount/tree | P09.10 |
| `src/skm/adapters/memory/execution/review_requests.py` | Receipt findings and the output actually reviewed | P09.10 |
| `src/skm/entrypoints/cli/commands/review.py` | Thin review request host dispatch and review show query | P09.10 |

`execution.request_review` requires `run.start` on the project and an idempotency key.
Its single UoW publishes a planning-owned service revision and persists the request,
review-only run, frozen bundle, one read-only task and budget accounts, with run events.
Service plans retain purpose `review_requests` and alias `review-requests`; ordinary
plan lists and standard-run/autopilot selectors exclude them.
`execution.get_review_receipt` requires project `run.read`, chooses the newest matching
reviewed tree before the newest stale receipt, and retains finding keys, locations and states.
`ReviewReceipt.fresh_for` compares the stored reviewed tree digest with the supplied digest.
The CLI routes are `execution.host.request_review` and `execution.get_review_receipt`;
the reference generator currently labels dynamic manifest-based dispatch as local.

Executor validation is separate from manual review; independent review requested changes.
All six reported findings have regression coverage; independent re-review is pending.
The original P09.10 write set excludes the downstream Git adapter, begin-stage review
inputs and acceptance-gate run-kind wiring. Those gaps are not covered by request/receipt
creation tests: a production worker reaching report acceptance still requires that wiring.
Review follow-up: RepositoryInspector resolves named commits and merge bases. GatewayTable.named
resolves the registered gateway identity with the same marker validation as get(), keeping host imports
away from foreign repository ports. Patch artifacts are reused by request key and patch digest;
review-request agent stages consume task.review_profile. Working-tree receipts use sealed mount heads.

## Hook subscription delivery

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/adapters/event_sinks/_pinned_http.py` | Bounded pinned HTTP transport and SSRF admission | P10.08.b |
| `src/skm/adapters/event_sinks/webhook.py` | Signed built-in webhook sink | P10.08.b |
| `src/skm/adapters/event_sinks/webhook_signing.py` | Exact-byte HMAC signing and verification | P10.08.b |
| `src/skm/modules/integrations/application/hook_delivery.py` | Two-phase outbox hook delivery | P10.08.b |
| `src/skm/modules/integrations/host/host_subscriptions.py` | Host command trust and outcome orchestration | P10.08.b |
| `src/skm/entrypoints/cli/commands/hooks.py` | Hook subscription operator CLI | P10.08.b |

## Hook subscription wiring and generated partitions

| File | Responsibility | Owner |
|---|---|---|
| `src/skm/bootstrap/composition_resources.py` | Subscription bootstrap and resource composition | P10.08.b |
| `src/skm/bootstrap/hook_subscriptions.py` | Subscription bootstrap and resource composition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_check_result.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_check_result_defs_check_result.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_command_input.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_command_input_event.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_command_output.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_doctor_report.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_doctor_report_checks_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_hook_decision.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_hook_decision_client_output.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_hook_decision_defs_json_value.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_decisions_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_decisions_item_boundary.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_decisions_item_boundary_owned_keys_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_defs_json_value.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_writes_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_writes_item_boundary.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_host_projection_plan_writes_item_boundary_owned_keys_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_integration_bundle_manifest.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_integration_bundle_manifest_agents_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_integration_bundle_manifest_assets_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_integration_bundle_manifest_skills_item.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_integrations_definitions.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_documents_webhook_delivery.py` | Generated integration document partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_adopt_file.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_apply_projection.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_defs.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_detect_drift.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_drain_hook_spool.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_evaluate_hook.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_first_turn_budget.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_plan_projection.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_remove_projection.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_run_doctor.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_sync_projections.py` | Generated integration host contract partition | P10.01.c → I-09.1 |
| `src/skm/modules/integrations/generated/_host_untrack_service_files.py` | Generated integration host contract partition | P10.01.c → I-09.1 |
| `src/skm/modules/integrations/generated/_host_test_host_subscription.py` | Generated integration host contract partition | P10.08.b |
| `src/skm/modules/integrations/generated/_host_trust_hook_subscription.py` | Generated integration host contract partition | P10.08.b |

## Ad hoc execution and context surfaces

| File | Contract | Owner |
| --- | --- | --- |
| `src/skm/entrypoints/cli/commands/_adhoc.py` | Ad hoc command DTO and client dispatch shared by exec and pipe | P11.02.e → I-08.2 |
| `src/skm/entrypoints/cli/commands/context.py` | CLI standalone context assembly, explanation and comparison | P11.02.e → I-08.2 |
| `src/skm/entrypoints/cli/commands/exec.py` | CLI entry point for an ad hoc task | P11.02.e → I-08.2 |
| `src/skm/entrypoints/cli/commands/session.py` | Local interactive session start, list, attach and stop | P11.02.e → I-08.3 |
| `src/skm/entrypoints/cli/commands/pipe.py` | CLI entry point for per-run workflows | P11.02.e → I-08.2 |
| `src/skm/entrypoints/cli/commands/route.py` | CLI runtime routing query | P11.02.f → I-08.2 |
| `src/skm/entrypoints/mcp/tools/adhoc.py` | Project-bound ad hoc run and standalone context MCP tools | P11.05.a → I-08.2 |
| `src/skm/modules/context/application/commands/assemble_context.py` | Project-scoped standalone context command | P09.04.d → I-08.2 |
| `src/skm/modules/execution/application/_adhoc_spec.py` | Read immutable ad hoc instructions and workflows through the artifact facade | P07.05.b → I-08.2 |
| `src/skm/modules/execution/application/commands/run_adhoc.py` | Project-scoped ad hoc run admission and artifact retention | P07.05.b → I-08.2 |
| `src/skm/modules/execution/domain/workflow/adhoc.py` | Closed-stage validation for per-run workflows | P07.04.a → I-08.2 |
| `src/skm/modules/execution/generated/_commands_run_adhoc.py` | Generated RunAdhoc command DTO | P07.05.b → I-08.2 |
| `src/skm/schemas/context/commands/assemble-context.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P09.04.d → I-08.2 |
| `src/skm/schemas/context/results/assemble-context.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P09.04.d → I-08.2 |
| `src/skm/schemas/execution/commands/run-adhoc.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P07.05.b → I-08.2 |
| `src/skm/schemas/mcp/tool-input-context-assemble.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P11.05.a → I-08.2 |
| `src/skm/schemas/mcp/tool-input-run-adhoc.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P11.05.a → I-08.2 |
| `src/skm/schemas/mcp/tool-output-context-assemble.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P11.05.a → I-08.2 |
| `src/skm/schemas/mcp/tool-output-run-adhoc.v1.json` | JSON Schema for the ad hoc execution and context surfaces | P11.05.a → I-08.2 |

### I-12.2 Live control and tool-call metering

| File | Contract | Owner |
|---|---|---|
| `src/skm/modules/execution/application/_incident_gate.py` | Fenced step boundary and policy-bound repair authorization | P07.05.b → I-12.4 |
| `src/skm/modules/execution/generated/_views_task_live_control_view_incidents_item.py` | Incident journal projection | P07.05.b → I-12.4 |
| `src/skm/modules/execution/application/_live_control.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/application/_tool_calls.py` | Execution live-control and tool-call metering | P07.05.d → I-12.2 |
| `src/skm/modules/execution/application/_operator_control.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/application/commands/reroute_task.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/application/commands/override_actor.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/application/commands/steer_task.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/application/commands/abort_step.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/application/queries/get_task_live_control.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/domain/live_control.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_commands_abort_step.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_commands_override_actor.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_tool_call.py` | Execution live-control and tool-call metering | P07.05.d → I-12.2 |
| `src/skm/modules/execution/generated/_commands_renew_lease_defs_tool_call_batch.py` | Execution live-control and tool-call metering | P07.05.d → I-12.2 |
| `src/skm/modules/execution/generated/_commands_reroute_task.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_commands_steer_task.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_results_live_control_result.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_views_task_live_control_view.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_views_task_live_control_view_steps_item.py` | Execution live-control and tool-call metering | P07.05.b → I-12.2 |
| `src/skm/modules/execution/generated/_views_task_live_control_view_tool_calls_item.py` | Execution live-control and tool-call metering | P07.05.d → I-12.2 |
