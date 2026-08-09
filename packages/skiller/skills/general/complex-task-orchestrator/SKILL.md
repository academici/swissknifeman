---
name: complex-task-orchestrator
bucket: general
version: 0.2.0
description: "Complex-task orchestration: decomposition, context routing, risk, Definition of Done."
when_to_use: "Use when scoping a multi-step task before implementation."
risk: write
persona: oss-dev
tags: [workflow, orchestration, checklist, agents]
requires: []
produces_for: [cross-layer-change-checklist]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Complex Task Orchestrator

## Activate when task
- touches >1 layer (backend + frontend + policy + tests);
- involves rename/move/remove or refactor with regression risk;
- needs sequential multi-step delivery;
- has ambiguous spec + high misinterpretation risk.

## Forbidden
- No edits before fixing task boundaries and invariants.
- Do not edit generated/ignored artifacts instead of source paths.
- Do not close task without explicit checklist and remaining risks.

## Algorithm
1. Fix goal in one sentence: "what changes and for whom".
2. Define boundaries: in-scope vs out-of-scope.
3. Define invariants: what must not break.
4. Gather minimal context (1-2 files), then expand via `navigation.md`.
5. Split work into subtasks by layer.
6. Per subtask, record expected artifact (code, test, doc, migration).
7. Define minimal test-gate and run order.
8. After edits: check contracts, tests, risks, open questions.

## Decomposition template
```text
Цель:
Границы:
Инварианты:
Слои:
Подзадачи:
1) ...
2) ...
Проверки:
Риски/что осталось:
```

## Definition of Done
- Changes only in relevant source files.
- If project architecture line shifted — update relevant `docs/*` and if needed `.ai/*`, run `php artisan boost:update`.
- All touched layers synced (no "halfway").
- Tests added/updated for changed behavior.
- Minimal test-gate run, results recorded.
- Final report includes: what done, what verified, remaining constraints.

## Related skills
- `task-brief-template` (general) — spec template (goal, boundaries, invariants, DoD) where decomposition lands.
- `spec-interview` (general) — if spec unclear, interview first, then decompose.
- `plan-protocol` (general) — decomposing a large initiative is a master plan
  (`plans/<ID>/`, phases, statuses), not just the template below.
- `cross-layer-change-checklist` (general) — mandatory layer sync before finalize.
- `anti-drift` (general) — iteration discipline + circuit-breaker during execution.
- `laravel-architecture/laravel-subagents` — delegate subtasks to subagents on large Laravel tasks.
- `session-handoff` (general) — hand off unfinished task to next session.
