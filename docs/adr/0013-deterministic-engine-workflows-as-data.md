# ADR 0013: Deterministic orchestration engine; workflows as data

Status: proposed
Date: 2026-10-25

## Context
Legacy `Conductor` binds many functions to one facade with a wide shared `self`; roles, usage, repair, sessions
and isolation live in one module.

## Decision
Execution is a pure decision function `advance(task_state, history, workflow, policy) -> NextAction` plus
command handlers that apply actions transactionally. Workflows are versioned resources composed of stages from a
closed set of types (prepare_environment, agent_step, run_checks, agent_review, human_gate, acceptance_gate,
integrate, advisor_consult) with declarative parameters and a closed predicate set. New stage types are trusted
plugins implementing `StageHandler`.

### Ad hoc tasks

`TaskKind.ADHOC` (stored as `adhoc`) must be included in `WORK_KINDS` so the engine can execute it.
It is valid only for an `adhoc` run. It must have SQL `NULL` in `plan_id`, `revision_id`,
`spec_entity_id`, and `spec_entity_kind`, and its task key (`display_key`) must match `^ADHOC-[0-9]+$`.

In `0013_execution_runs.sql`, `run_tasks.run_kind` must be `NOT NULL`. A composite foreign key from
`run_tasks (run_id, run_kind)` to the unique key `runs (id, kind)` must enforce that the task's run
kind matches the owning run. SQL must enforce the `adhoc` task constraints as a distinct branch.
Existing task kinds must retain their workspace, plan and revision bindings, their typed spec entity
and origin rules, and their existing task key validation. The `ADHOC-` key format is exclusive to
`TaskKind.ADHOC`. See [ADR 0008](0008-plan-draft-revision-run.md#run-persistence).

## Alternatives considered
- LLM supervisor driving the workflow: rejected (principle 1).
- Arbitrary workflow scripts: rejected — unbounded authority and untestable.

## Consequences
Every transition is testable without IO.

## Compatibility
Behaviours kept from legacy: bounded rework rounds, MANUAL_PENDING without rework, started-before-execution
records, receipts and reconciliation.

## Verification
Domain tests per transition; e2e on the fake runtime.

Materialized: 2026-10-27. The decision date is preserved.

## Execution addenda

Names, layers and module boundaries follow [layers and modules](../architecture/layers-and-modules.md).

E53 uses one ActionDecision evaluator for action and cause. E55 pins workflow semantics; E57 persists selected/deferred continuation so claim never reapplies semantic counters. E58 pins typed work policies separately from emergency limits.
