# advance() — таблица решений

Копия `spec/modules/execution.md` §5.1 для ревью (нормативен текст spec; при расхождении правится этот файл).
Порядок: сначала глобальные защиты G1–G7 (первая сработавшая решает), затем строка по последней записи истории
попытки (стадия × исход × условие). «Следующая стадия по workflow» — первая стадия после текущей, применимая к виду
задачи (`for_kinds`), с истинным `when` и ложным `skip_when`. Work-задачи: `unit`, `item`, `integration`, `followup`;
gate-задачи: `item_gate`, `phase_gate`, `plan_acceptance`, `group_review`, `plan_audit`.

Каждая строка — отдельный параметризованный случай `tests/unit/execution/domain/test_advance_table.py`.

Evaluator обрабатывает только ещё не применённые trusted triggers из `Attempt.continuation.kind=advance`
(execution §4.6.1). При G1/pause cursor сохраняется для последующей обработки. Уже применённый `kind=stage`
dispatch/materialize без повторного evaluator: C1 не повторяет task transition, D6 не увеличивает counter
и не создаёт второй FixBrief после pause/release/expiry. Initial A1 выбирается один раз с новой Attempt,
сохраняет task assigned/attempt preparing; actual Begin выполняет T3/AttemptStarted и consume cursor атомарно.
Claim связывает template с текущим config/input digest, а не исполняет заново эту таблицу. Manual/decision/
policy/timer triggers сохраняются через тот же bounded helper; observations источником action не являются.

| # | Статус задачи | Последняя стадия / исход | Условие | NextAction | Новый статус |
|---|---|---|---|---|---|
| G1 | любой | — | `run.status ∉ {running}` | `Noop` | без изменений |
| G2 | терминальный | — | — | `Done` | — |
| G3 | любой нетерминальный | — | `execution.kill_switch` | `WaitFor(BLOCKED_BY_POLICY{reason=kill_switch}, release=true)` + run R6 (`pause_reason = "kill switch"`) | без изменений |
| G4 | любой | — | `attempt.state = ownership_lost` и `task.attempt_count < attempts_max` | `NewAttempt("LEASE_LOST")`; новая попытка получает handoff: блок контекста `previous_attempt` (сводка стадий/outputs прежней попытки и ссылка на patch-артефакт её среды, если он загружен — правило L3, не автоприменение) | `ready` |
| G5 | любой | — | `attempt.state = ownership_lost` и лимит попыток исчерпан | `Fail(LEASE_LOST)` | `failed` |
| G6 | любой | — | есть открытый **blocking** decision request задачи | `WaitFor(<код по kind: question → WAITING_ANSWER, approval → WAITING_APPROVAL, budget → BLOCKED_BY_BUDGET, escalation → WAITING_OWNER>, release=true)` | `awaiting_decision` |
| G7 | любой нетерминальный | — | оценка следующей стадии не помещается в бюджет (§5.6) | `Escalate(budget, BUDGET_EXHAUSTED, blocking=BLOCKED_BY_BUDGET)` | `awaiting_decision` (+ run `paused`) |
| L2i | `integrating` | последняя стадия `integrate` `interrupted` (любая фаза) | — | `RunStage(integrate, reconcile)` — сверка exact effect request/journal/receipt до повтора (§5.13); проверяется раньше L1 | `integrating` |
| L1 | рабочий нетерминальный | последняя стадия `interrupted`, `runtime_started_at` нет (правило L1, §7.4) | стадия ≠ `integrate`; у попытки нет эффекта `executing\|outcome_unknown` | `RunStage(<та же стадия>, <тот же mode>, <тот же round_no>)` — повтор безопасен, runtime не стартовал | без изменений |
| L2 | рабочий нетерминальный | последняя стадия `interrupted` после `runtime_started_at`, reap подтверждён на хосте среды (правило L2) | пишущая agent-стадия (executor) | `RunStage(<та же стадия>, resume_interrupted, feedback={interrupted_stage_record_id})` — та же попытка и среда, блок контекста `resume_note` с отметкой о прерывании | без изменений |
| L2b | рабочий нетерминальный | как L2 | не пишущая стадия (scout/reviewer/triager/advisor/`run_checks`) | `RunStage(<та же стадия>, retry)` (без расхода `step_max_infra_retries`; checks — как D11) | без изменений |
| A1 | `assigned`/`executing` | нет записей | новая Attempt: initial selection один раз; T3 только при Begin | `RunStage(prepare, prepare_environment, normal)` | `assigned` до actual Begin; затем `executing` |
| A2 | `executing` | `prepare_environment`/`success` | work-задача; следующая применимая — `scout` (`when` истинен) | `RunStage(scout, agent_step, normal)` (`apply_action` переиспользует результат scout при совпадении `scout_reuse_key` — §5.2, диагностика `SCOUT_REUSED`) | `executing` |
| A3 | `executing` | `prepare_environment`/`success` | work-задача; scout неприменим | `RunStage(<следующая применимая: execute, research или review для review-only>, normal)` | `executing` (`reviewing` для review) |
| A4 | `executing` | `prepare_environment`/`runtime_error` | `decide_retry` → `retry` | `RunStage(prepare, retry)` | `executing` |
| A5 | `executing` | `prepare_environment`/`runtime_error` | `decide_retry` → `stop` | `Escalate(escalation, <код класса>, WAITING_OWNER)` | `awaiting_decision` |
| A6 | `executing` | `prepare_environment`/`success` | gate-задача (range-output запечатан) | `RunStage(<следующая применимая: gate_checks или review>, normal)` | `checking` / `reviewing` |
| B1 | `executing` | `scout`/`success` | — | `RunStage(execute, agent_step, normal)` | `executing` |
| B2 | `executing` | `scout`/`result_invalid` или `runtime_error` | scout необязателен (`stage.optional=true`, по умолчанию true) | `RunStage(execute, normal)` + диагностика `SCOUT_SKIPPED` | `executing` |
| B3 | `executing` | `scout`/`runtime_error` | `optional=false`, `decide_retry` → `retry`/`retry_after`/`fallback_route` | `RunStage(scout, retry, not_before/route_override)` | `executing` |
| C1 | `executing` | `execute`/`success` | нет blocking-вопросов, нет нарушений scope (или `scope_outside_policy=deviation`) | `RunStage(checks, run_checks, normal)` | `checking` |
| C2 | `executing` | `execute`/`question` | `decide_audience` = `owner` по правилу owner-only (kind `approval`/`credential`, gate category, категория с аудиторией owner, лимит вопросов) | `Escalate(question → audience owner, WAITING_ANSWER)` | `awaiting_decision` |
| C3 | `executing` | `execute`/`question` | `decide_audience` = `advisor`, `advisor_rounds_used < advisor_max_rounds` | `RunStage(advise, advisor_consult, normal, params={problem_ref: "question:<id>@<rev>"})` (blocking `WAITING_ADVISOR` до результата) | `executing` |
| C4 | `executing` | `execute`/`question` | `decide_audience` = `consilium` | `RunStage(advise, advisor_consult, normal, params={problem_ref, panel: true})` | `executing` |
| C5 | `executing` | `execute`/`question` | `decide_audience` = `policy_default` (policy `defaults`, есть `default`, не owner-only, не отвечен раньше) | ответ политикой в той же транзакции → `RunStage(execute, continue_with_answer)` | `executing` |
| C6 | `executing` | `execute`/`question` | `decide_audience` = `owner` (policy `queue` или advisor исчерпан) или `denied` | `owner` → `Escalate(question, WAITING_ANSWER)`; `denied` → вопрос `denied`, `Escalate(escalation, FORBIDDEN, text="QUESTION_DENIED: <id>", WAITING_OWNER)` | `awaiting_decision` |
| C7 | `executing` | `execute`/`question` | вопрос повторно использован (`question_key`+`digest` совпали с принятым решением) | ответ из решения (`answered_by=reuse`) → `RunStage(execute, continue_with_answer)` + диагностика `QUESTION_REUSED` | `executing` |
| C8 | `executing` | `execute`/`blocked` (escalation в отчёте) | — | `Escalate(escalation, ITEM_BLOCKED, WAITING_OWNER)` | `awaiting_decision` |
| C9 | `executing` | `execute`/`write_scope_violation` | `scope_outside_policy = block` | `Escalate(escalation, WRITE_SCOPE_VIOLATION, WAITING_OWNER)` | `awaiting_decision` |
| C10 | `executing` | `execute`/`result_invalid` | повторов роли после repair `< step_max_result_retries` (считаются записи этой стадии с `result_invalid` с последнего `success`) | `RunStage(execute, retry, feedback={schema_errors_step_id})` — **та же роль** с подсказкой об ошибке схемы (§5.8) | `executing` |
| C10b | `executing` | `execute`/`result_invalid` | повторы исчерпаны | `Escalate(escalation, RESULT_INVALID, WAITING_OWNER)` (варианты ответа: `retry_stage`, `new_attempt`, `fail`) | `awaiting_decision` |
| C11 | `executing` | `execute`/`runtime_error` | `decide_retry` → `retry` / `retry_after` / `fallback_route` | `RunStage(execute, retry, not_before, route_override)`; при `not_before` — blocking `WAITING_PROVIDER` (`next_check_at = not_before`) | `executing` |
| C12 | `executing` | `execute`/`runtime_error` | `decide_retry` → `reconcile` (запись + грязный worktree) | `RunStage(execute, resume_interrupted)` (исполнитель продолжает с пометкой о прерывании) | `executing` |
| C13 | `executing` | `execute`/`runtime_error` | `decide_retry` → `replan` (context_limit) | `Escalate(escalation, CONTEXT_OVER_BUDGET, WAITING_OWNER)` (варианты: `split_task` → `fail` с пометкой, `raise_budget`, `retry_stage`) | `awaiting_decision` |
| C14 | `executing` | `execute`/`runtime_error` | `decide_retry` → `stop` (класс `quota` с известным `reset_at` → blocking `WAITING_BUDGET_RESET`) | `Escalate(escalation, <код класса §5.5>, WAITING_OWNER \| WAITING_BUDGET_RESET)` | `awaiting_decision` |
| D1 | `checking` | `run_checks`/`success` | все обязательные `passed`, review_mode `required` | `RunStage(review, agent_review, normal, round_no=task.review_rounds+1)` | `reviewing` |
| D2 | `checking` | `run_checks`/`success` | review_mode `self`, `review_strategy = risk_scored`, `risk.score ≥ risk_threshold` или `risk.critical ≠ ∅` | `RunStage(review, agent_review, normal)` + диагностика `DYNAMIC_REVIEW_ADDED` | `reviewing` |
| D3 | `checking` | `run_checks`/`success` | review_mode `self` (self-check в отчёте есть), риск ниже порога или `review_strategy = per_task` | `Accept(output, clearance=self)` → `Integrate` | `integrating` |
| D4 | `checking` | `run_checks`/`success` | review_mode `waived` | `Accept(output, clearance=waived)` → `Integrate` | `integrating` |
| D5 | `checking` | `run_checks`/`manual_pending` | есть manual check без verdict | `WaitFor(WAITING_MANUAL_CHECK, release=true)` | `manual_pending` |
| D6 | `checking` | `run_checks`/`checks_failed` | work-задача, обязательный `failed`, `task.check_fix_rounds < rework_max_rounds` | `Rework(checks_failed, fix_brief)` → `RunStage(execute, rework)` | `rework_required` → `executing` |
| D6g | `checking` | `run_checks`/`checks_failed` | gate-задача, `task.review_rounds < review_max_rounds` | `CreateFollowups(checks_failed, check_execution_ids)` | `blocked` (`BLOCKED_BY_DEPENDENCY` на followups) |
| D7 | `checking` | `run_checks`/`checks_failed` | лимит исчерпан, `advisor_enabled`, раунды advisor есть | `RunStage(advise, advisor_consult, params={problem_ref: "checks:<round>"})` | `checking` |
| D8 | `checking` | `run_checks`/`checks_failed` | лимит исчерпан, advisor недоступен/исчерпан | `Escalate(escalation, REWORK_LIMIT_REACHED, WAITING_OWNER)` | `awaiting_decision` |
| D9 | `checking` | `run_checks`/`checks_error` | использовано ретраев ошибок `< checks_error_retries` | `RunStage(checks, retry)` | `checking` |
| D10 | `checking` | `run_checks`/`checks_error` | ретраи исчерпаны | `Escalate(escalation, <error_code check-а>, WAITING_OWNER)` (не rework) | `awaiting_decision` |
| D11 | `checking` | `run_checks`/`checks_unknown` (прервано) | — | `RunStage(checks, retry)` (без расхода `checks_error_retries`) | `checking` |
| D12 | `checking` | `run_checks`/`tree_changed` | первое изменение дерева проверками в этом раунде | `RunStage(checks, retry)` + диагностика `CHECK_CHANGED_TREE` | `checking` |
| D13 | `checking` | `run_checks`/`tree_changed` | повторное изменение | `Escalate(escalation, CHECKS_MUTATED, WAITING_OWNER)` | `awaiting_decision` |
| D14 | `checking` | `run_checks`/`success` | упали только необязательные checks | как D1–D4 + диагностика `ADVISORY_CHECK_FAILED` | по D1–D4 |
| D15 | `checking` | `run_checks`/`success` | gate-задача | review_mode `required` → D1; иначе → `RunStage(<phase_gate \| plan_acceptance>)` (control plane, K11/K12) | `reviewing` / `integrating` |
| E1 | `manual_pending` | verdict записан | все manual `pass`, остальные passed | как D1–D4 (D15 для gate) | по D1–D4 |
| E2 | `manual_pending` | verdict записан | какой-то manual `fail`, rework раунды есть | work: `Rework(manual_failed)`; gate: `CreateFollowups(checks_failed)` | `rework_required` / `blocked` |
| E3 | `manual_pending` | verdict записан | `fail`, раундов нет | `Escalate(escalation, REWORK_LIMIT_REACHED, WAITING_OWNER)` | `awaiting_decision` |
| F1 | `reviewing` | `agent_review`/`verdict_green` | нет открытых findings `≥ major` | work: `Accept(output, clearance=green)` → `Integrate`; gate: `RunStage(<phase_gate \| plan_acceptance>)` | `integrating` |
| F2 | `reviewing` | `agent_review`/`verdict_attention` | `attention_policy = triage` | `RunStage(triage, agent_step role=triager)` | `reviewing` |
| F3 | `reviewing` | `agent_review`/`verdict_attention` | `attention_policy = ask_owner` | `Escalate(escalation, NOT_ACCEPTABLE, options=[accept_deviation, rework, fail], WAITING_OWNER)` | `awaiting_decision` |
| F4 | `reviewing` | `agent_review`/`verdict_red` | — | `RunStage(triage, agent_step role=triager)` | `reviewing` |
| F5 | `reviewing` | `agent_review`/`result_invalid` или `runtime_error` | ретрай стадии ещё не использован (`step_max_result_retries` / `decide_retry`) | `RunStage(review, retry, feedback={schema_errors_step_id})` | `reviewing` |
| F6 | `reviewing` | `agent_review`/`result_invalid` или `runtime_error` | ретрай использован | `Escalate(escalation, RESULT_INVALID, WAITING_OWNER)` | `awaiting_decision` |
| F7 | `reviewing` | `agent_review`/`verdict_*` | задача ревью по запросу (`run.kind = review_request`) | `Accept(range-output, clearance=report)` → `Done` (verdict — содержимое receipt, не условие приёмки; rework нет) | `accepted` |
| F8 | `reviewing` | `agent_review`/`verdict_*` | reviewer sealed a fix as a new output | Run task checks on the fix, then request a new read-only review. Escalate if the workflow has no task checks stage. | `checking` / `awaiting_decision` |
| H0 | `reviewing` | `triage`/`result_invalid` или `runtime_error` | как F5/F6 | `RunStage(triage, retry, feedback)` / `Escalate(RESULT_INVALID)` | `reviewing` / `awaiting_decision` |
| H1 | `reviewing` | `triage`/`success` | work-задача, confirmed ≠ ∅, `task.review_rounds < review_max_rounds` | `Rework(review_findings, fix_brief)` → `RunStage(execute, rework)` | `rework_required` → `executing` |
| H1g | `reviewing` | `triage`/`success` | gate-задача, confirmed `≥ major` ≠ ∅, `task.review_rounds < review_max_rounds` | `CreateFollowups(review_findings, finding_ids)` (≤ `execution.review.followups_max`) | `blocked` (`BLOCKED_BY_DEPENDENCY`) |
| H2 | `reviewing` | `triage`/`success` | work-задача, confirmed ≠ ∅, раунды исчерпаны, нет confirmed blocker, `review_final_correction` | `RunStage(execute, final_correction)` (после checks — H7/H8) | `rework_required` → `executing` |
| H3 | `reviewing` | `triage`/`success` | confirmed blocker и раунды исчерпаны | `Escalate(escalation, REWORK_LIMIT_REACHED, WAITING_OWNER)` | `awaiting_decision` |
| H4 | `reviewing` | `triage`/`success` | confirmed = ∅, rejected содержит `≥ major`, advisor доступен | `RunStage(advise, advisor_consult, params={problem_ref: "findings:<round>"})` | `reviewing` |
| H5 | `reviewing` | `triage`/`success` | confirmed = ∅, rejected `≥ major`, advisor недоступен | `Escalate(escalation, NOT_ACCEPTABLE, options=[accept_rejection, rework, fail], WAITING_OWNER)` | `awaiting_decision` |
| H6 | `reviewing` | `triage`/`success` | confirmed = ∅ (или для gate — confirmed только `minor`/`nit`), rejected только `minor`/`nit` | work: `Accept(output, clearance=cleared_by_triage)` → `Integrate`; gate: `RunStage(<phase_gate \| plan_acceptance>)` | `integrating` |
| H7 | `checking` | `run_checks`/`success` после `final_correction` | `review_accept_findings_only` и изменения output ⊆ locations confirmed findings ∪ тесты write scope ∪ docs | `Accept(output, clearance=findings_only)` → `Integrate` + диагностика `REVIEW_DEBT` | `integrating` |
| H8 | `checking` | `run_checks`/`success` после `final_correction` | изменения шире локаций findings | `Escalate(escalation, NOT_ACCEPTABLE, payload={review_debt}, WAITING_OWNER)` | `awaiting_decision` |
| I1 | `executing`/`checking`/`reviewing` | `advisor_consult`/`success` | совет не удержан (§5.10), problem `question:*` | ответ записан (`answered_by=advisor\|consilium`) + `DecisionRecord` → `RunStage(execute, continue_with_answer)` | `executing` |
| I2 | `checking` | `advisor_consult`/`success` | не удержан, problem `checks:*` | `RunStage(execute, rework, feedback={advice})` (сверх лимита rework ровно на 1 раунд) | `executing` |
| I3 | `reviewing` | `advisor_consult`/`success` | не удержан, problem `findings:*` | `RunStage(triage, retriage_with_advice)` | `reviewing` |
| I4 | любой | `advisor_consult`/`held` | `needs_owner`, gate, confidence ниже min, рекомендация вне опций | `Escalate(question/escalation → owner, payload includes advice, WAITING_ANSWER)` + диагностика `ADVICE_HELD` | `awaiting_decision` |
| I5 | любой | `advisor_consult`/`runtime_error` или `result_invalid` | — | как будто advisor нет: соответствующая строка «advisor недоступен» (C6/D8/H5) + диагностика `ADVISOR_FAILED` | по строке |
| I6 | `executing` | `advisor_consult`/`success` или `held` | `plan_audit` (problem `readiness:<report_id>`) | `Done` — результат записан в новый readiness report (§5.12) | `accepted` |
| J1 | `awaiting_decision` | ответ на вопрос исполнителя | среда жива, задача на том же хосте | `RunStage(execute, continue_with_answer)` (через новый assignment с `required_host_id`) | `executing` |
| J2 | `awaiting_decision` | ответ `retry_stage` | — | `RunStage(<последняя стадия>, retry)` | статус стадии |
| J3 | `awaiting_decision` | ответ `new_attempt` | `attempt_count < attempts_max` (или ответ содержит `raise_limit`) | `NewAttempt("OWNER_DECISION")` | `ready` |
| J4 | `awaiting_decision` | ответ `accept_deviation` / `accept_rejection` | записана `DeviationAcceptance` | `Accept(output, clearance=deviation)` → `Integrate` | `integrating` |
| J5 | `awaiting_decision` | ответ `skip` | право `run.control` | `Done` (задача `skipped`, решение записано) | `skipped` |
| J6 | `awaiting_decision` | ответ `fail` | — | `Fail(<код эскалации>)` | `failed` |
| J7 | `awaiting_decision` | ответ `raise_budget` | `reconfigure_run` выполнен | повтор строки, вызвавшей G7 | по строке |
| K1 | `integrating` | `acceptance_gate` → `NotAcceptable(reasons)` | все причины — ожидания (manual, approval) | `WaitFor(...)` | `manual_pending`/`awaiting_decision` |
| K2 | `integrating` | `acceptance_gate` → `NotAcceptable(reasons)` | есть причины-нарушения | `Escalate(escalation, NOT_ACCEPTABLE, payload={reasons}, WAITING_OWNER)` | `awaiting_decision` |
| K3 | `integrating` | `acceptance_gate` → `Accepted` | workflow имеет `integrate`, `output.source = executor` | `RunStage(integrate, integrate, normal)` | `integrating` |
| K4 | `integrating` | `acceptance_gate` → `Accepted` | workflow без `integrate` (research-only, review-only) | `Done` | `accepted` |
| K5 | `integrating` | `integrate`/`success` | commit в целевой ветке, receipts закрыты; нет применимой стадии recheck (`execution.integration.rerun_checks = false` или нет checks с `rerun_after_integration`) | `Done` | `accepted` |
| K5a | `integrating` | `integrate`/`success` | есть применимая стадия recheck (`run_checks(scope=rerun_after_integration)` по workflow или неявная при `rerun_checks`) | `RunStage(recheck, run_checks, normal, params={scope: rerun_after_integration, recheck_commits: {mount: commit_shas[-1]}})` в той же попытке: checks выполняются в отдельном owned detached worktree `commit_sha` (§5.13; adapters §3.8), в том числе при среде попытки `existing_checkout` (не в пользовательском checkout и не в integration worktree; slot не удерживается), переиспользование результатов запрещено | `integrating` |
| K5b | `integrating` | `run_checks(rerun_after_integration)`/`success` | все такие checks `passed` | `Done` | `accepted` |
| K5c | `integrating` | `run_checks(rerun_after_integration)`/`checks_failed` или `checks_error` с исчерпанными `checks_error_retries` (manual checks с `rerun_after_integration` запрещены валидатором planning) | — | `Escalate(escalation, INTEGRATION_RECHECK_FAILED, options=[retry_stage, fail], WAITING_OWNER)`; автоматического revert нет (коммит уже в ветке; владелец исправляет ветку и отвечает `retry_stage` с явно одобренными SHA текущего tip по mounts (§5.13), либо `fail`) | `awaiting_decision` |
| K5d | `integrating` | `run_checks(rerun_after_integration)`/`checks_error` (ретраи есть) или `checks_unknown` | — | `RunStage(recheck, retry)` (как D9/D11) | `integrating` |
| K6 | `integrating` | `integrate`/`conflict` | — | создать задачу `integration` → `WaitFor(BLOCKED_BY_INTEGRATION, release=true)` | `integrating` |
| K7 | `integrating` | `integrate`/`outcome_unknown` | — | `RunStage(integrate, reconcile)` | `integrating` |
| K8 | `integrating` | `integrate`/`approval_required` | `record_stage_result` создал intent и эффект (K7, §5.13); intent `proposed` (`needs_approval`) | `DecisionRequest(kind=approval, refs={intent_id, effect_id})` + `WaitFor(WAITING_APPROVAL{intent_id, decision_request_id}, release=true)` | `awaiting_decision` |
| K8a | `integrating` | `integrate`/`approval_required` | intent сразу `approved` (авто-одобрение policy) | `RunStage(integrate, normal, params={effect_id})` — исполнение эффекта тем же worker-ом | `integrating` |
| K9 | `integrating` | `integrate`/`runtime_error` | `decide_retry` → retry | `RunStage(integrate, retry)` | `integrating` |
| K10 | `integrating` | `integrate`/`runtime_error` | stop | `Escalate(escalation, INTEGRATION_CONFLICT или код, WAITING_OWNER)` | `awaiting_decision` |
| K13 | `integrating` | `integrate`/`runtime_error` с `INTEGRATION_HOST_MISMATCH` (среда попытки не на хосте интеграции пары `(run, repository)`, K6) | — | `Escalate(escalation, INTEGRATION_HOST_MISMATCH, options=[new_attempt, fail], WAITING_OWNER)`; новая попытка получает `required_host_id` хоста интеграции | `awaiting_decision` |
| K11 | `integrating` | `phase_gate` → `Accepted` / `NotAcceptable` | gate-задача `item_gate`/`phase_gate`/`group_review` | `Accepted` → `Done`; `NotAcceptable` → как K1/K2 | `accepted` / по K1/K2 |
| K12 | `integrating` | `plan_acceptance` → `Accepted` / `NotAcceptable` | задача `plan_acceptance` | `Accepted` → `Done`; непокрытые критерии / провалы → `CreateFollowups` (если раунды есть) иначе `Escalate(NOT_ACCEPTABLE, payload={coverage}, WAITING_OWNER)` | `accepted` / `blocked` / `awaiting_decision` |

`ReviewClearance` (сохраняется в `acceptance_decisions.basis.clearance`): `green` | `findings_only` |
`cleared_by_triage` | `deviation` | `self` | `waived` | `report` (ревью по запросу: принят отчёт, не изменения).

Дополнительные переходы для gate-задач: `checking`/`reviewing` → `blocked` (D6g, E2, H1g, K12 — `CreateFollowups`)
и `blocked` → `ready` (T29, когда все followups `accepted`/`skipped`); gate получает **новую** попытку (новый
range-output от `prepare_environment`), `review_rounds` продолжает счёт задачи; попытки gate-задач по причине
`GATE_REREVIEW` не расходуют `budgets.task.max_attempts` (лимит — `review_max_rounds`). Строки — в `TASK_TRANSITIONS`
как T28 (`checking|reviewing|integrating → blocked`, `CreateFollowups`) и T29 (`blocked → ready`, followups готовы).
