### 4.19 BlockingReason (G9)

| `BlockingCode` | Статус задачи | `refs` | `resolver_role` | `allowed_actions` | `next_check_at` / `deadline_at` |
|---|---|---|---|---|---|
| `WAITING_OWNER` | `awaiting_decision` | `decision_request_id`, `stop_code` (`REWORK_LIMIT_REACHED`, `NOT_ACCEPTABLE`, `RESULT_INVALID`, `INTEGRATION_CONFLICT`, `INTEGRATION_RECHECK_FAILED`, `INTEGRATION_HOST_MISMATCH`, `ITEM_BLOCKED`, …) | `owner` | `decide_escalation`, `skip_task`, `cancel_run` | — / `deadline_at` запроса |
| `WAITING_ANSWER` | `awaiting_decision` | `decision_request_id`, `question_key` | `owner` (или роль из `answer_schema`) | `answer_question`, `skip_task` | — / `deadline_at` |
| `WAITING_ADVISOR` | `executing`/`checking`/`reviewing` | `decision_request_id`, `stage_record_id` | `advisor` | `wait`, `cancel_run` | — / — |
| `WAITING_MANUAL_CHECK` | `manual_pending` | `check_execution_id`, `check_key` | из check spec `actor_role` (default `member`) | `record_verdict` | — / — |
| `WAITING_APPROVAL` | `awaiting_decision` | `intent_id`, `decision_request_id` | `maintainer` | `approve_intent`, `cancel_run` | — / срок intent |
| `WAITING_PROVIDER` | рабочий статус | `stage_record_id`, `error_class` (`rate_limit`/`quota`), `route` | `system` | `wait`, `retry_now` | `not_before` / `now + execution.retry.provider_wait_max_seconds` |
| `WAITING_BUDGET_RESET` | `awaiting_decision` (run `paused`) | `stop_code = QUOTA_EXHAUSTED`, `reset_at` | `system` | `wait`, `raise_budget`, `cancel_run` | `reset_at` / `now + execution.autopilot.quota_wait_max_seconds` |
| `BLOCKED_BY_DEPENDENCY` | `blocked` | `prerequisite_task_ids[]`; при провале предка — `failed_task_ids[]` | `None` (ждёт) или `owner` (есть failed) | `wait`; при failed — `restart_task`, `skip_task` | — / — |
| `BLOCKED_BY_MATERIAL` | `blocked` | `material_ids[]`, `file_version_ids[]`, `required_for` | `member` | `provide_material`, `skip_task` | `now + execution.materials.recheck_seconds` / — |
| `BLOCKED_BY_BUDGET` | `awaiting_decision` | `decision_request_id`, `dimension`, `scope`, `limit`, `spent`, `reason?` (`unmetered` — §5.6) | `owner` | `raise_budget`, `cancel_run` | — / — |
| `BLOCKED_BY_CAPABILITY` | `ready` (assignment ждёт worker) | `capabilities[]`, `required_host_id?`, `required_labels[]`, `environment_kind`, `isolation_profiles[]` | `maintainer` | `start_worker`, `cancel_run` | `now + execution.scheduler.capability_wait_seconds` / — |
| `BLOCKED_BY_POLICY` | `awaiting_decision` | `reason` (`kill_switch`, `emergency_stop`, `policy_denies`), `decision_request_id?` | `owner` | `resume_run`, `cancel_run` | — / — |
| `BLOCKED_BY_INTEGRATION` | `integrating` | `integration_task_id` | `None` | `wait` | — / — |
| `SUSPECTED_STALL` | рабочий статус | `stage_record_id`, `step_id`, `silent_seconds`, `health_reason` | `system` | `wait`, `restart_task` | `now + grace` / — |
| `RECOVERING` | рабочий статус | `stage_record_id`, `recovery_record_id` \| `reap_stage_record_id` (+ agent-only `reap_step_id`, правило L2), `recovery_step` | `system` | `wait` | `now + execution.supervisor.grace_seconds` (L2 — `now + execution.lease.reap_wait_seconds`) / — |
