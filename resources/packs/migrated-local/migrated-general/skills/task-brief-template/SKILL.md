---
name: task-brief-template
description: "Brief template for complex tasks: goal, scope, invariants, assumptions, out of scope, acceptance criteria, definition of done, loop fields."
---

# Task Brief Template

Machine form: `orch/schemas/exec/v1/execution-input.schema.json` (`replaced_by`); this template stays the human brief.

Activate when the task is ambiguous or spans multiple subsystems.

## Brief template

```text
Context:
- Briefly: where is the problem/initiative and why it matters.

Target:
- What result should the user get/business.

Boundaries:
- What is included in the task.

Out of Scope (do not touch without an explicit request):
- Files/modules are out of task, even if «can be improved».
- New dependencies (composer/npm) — by explicit request only.
- Refactoring of adjacent code.

Explicit assumptions:
- The agent MUST verify each item before the start;
  if there is a discrepancy - stop, clarifying question.
- [ ] Assumption 1: ...
- [ ] Assumption 2: ...

Invariants:
- What rules and contracts cannot be broken.

Layers affected:
- backend / frontend / policies / routes / docs / tests.

Expected behavior:
- Before change:
- After change:

Acceptance criteria:
- [ ] ...
- [ ] ...

Minimum verification:
- What tests/checks must be run.

Loop (fill in if the task involves >1 meaningful iteration):
- Loop verifier: command/check between circles (test, lint, `git log`).
- Exit condition: objective state = task completed (by check output,
  not as stated by the agent).
- Hard stop trigger: signal at which the agent stops and requests
  approval (see circuit breaker in `anti-drift`).

Definition of Done:
- [ ] All acceptance criteria are closed.
- [ ] Tests and lint are green.
- [ ] git diff contains no changes outside Scope.
- [ ] Documentation/CHANGELOG updated (if the task changes public behavior).

Limitations:
- Duration, risks, legacy-restrictions, backward compatibility.
```

## Brief-quality checklist

- Goal describes the result, not just actions.
- Explicit non-goals (out of scope) + ban on edits outside scope.
- Assumptions written out explicitly, not made silently.
- Domain + security invariants listed.
- Minimal test-gate specified.
- Definition of Done distinct from acceptance criteria: process conditions (tests, lint, diff within scope), not feature behavior.
- Final task-report format fixed.
- For iterative tasks Loop fields filled: loop does not start without Exit condition.

To fill the template from a fuzzy idea use skill `spec-interview` (bucket general): one-question-at-a-time interview before any code.

## Plan → Clear → Execute

For large tasks split brief and execution across sessions:

1. **Plan session**: discuss via template above, save the finished brief/plan to file (`.claude/plans/<task>.md`). Plan is self-contained: the executor will not see the current discussion.
2. `/clear` — intermediate planning attempts must not bleed into execution context.
3. **Execution session**: load only the plan file and execute step by step.

Ready `/plan` and `/execute` command templates + rest of context-saving discipline — in skill `context-economy` (bucket general).

## Iterative (loop) execution

If the task needs several rounds with intermediate checks — fill the Loop fields in the template and run via built-in `/loop` (self-paced) or `/schedule` (cron). Round stop-controller — `anti-drift` (circuit breaker); between-rounds verifier — `cross-layer-change-checklist`. Ready starter template — `snippets/loop-kickoff.md` (copy into project `.claude/commands/`). Full model and why there is no separate `loops/` registry — guide [Loop semantics](https://github.com/org/project/blob/main/docs/guide/loop-semantics.md).

## Related skills

- `spec-interview` (general) — fill this template from a fuzzy idea via interview.
- `complex-task-orchestrator` (general) — decompose a finished brief into per-layer subtasks.
- `plan-protocol` (general) — multi-phase work longer than one session is a master plan
  in `plans/<ID>/`; this brief is for a single task within one session.
- `cross-layer-change-checklist` (general) — sync layers during execution.
- `context-economy` (general) — Plan→Clear→Execute and `/plan`, `/execute` commands.
- `anti-drift` (general) — iteration discipline, relies on fixed scope.
