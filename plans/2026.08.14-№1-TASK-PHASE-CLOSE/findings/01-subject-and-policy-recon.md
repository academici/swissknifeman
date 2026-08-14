# Recon — audit subject and current close policy

**Источник:** read-only repository research, 2026-08-14.
**Evidence:** RAG:— (repo-grounded).

## Subject identity

- SSOT normalizer уже есть: `packages/task/lib/task/review_policy.py::phase_audit_subject()`.
  Он принимает `Pn` и `Pn — режим фазы`, возвращая `Pn`.
- Уже нормализуют: `journal.py` terminal validation, `plan_delivery.py`,
  `plan_lint_checks/common.py`, `review_policy.phase_audit_terminal_policy()`.
- Literal comparison ещё осталось в `plan_gates.py::phase_close_gate()` и
  `task_contract.py::_count_audit_rounds()`.
- Canonical `commands/plan-audit.md` пока велит writer'у писать legacy subject.

## Existing candidate/policy

- `phase_candidate_fingerprint()` binds phase id, scope, terminal item heads, material risks,
  declared files и product-tree digest.
- `phase_audit_policy()` сейчас считает `Review: full` и multi-item `Review: light`
  самостоятельными audit blockers.
- Текущий `terminal-evidence/v1` уже валидирует spec digest, Validation rows,
  green statuses и deviation repair record; Slice A не нужен новый receipt format.

## Minimal boundary

Переиспользовать existing subject normalizer, канонизировать new phase-audit writes
до idempotency/persistence, убрать Review/volume из first-audit admission и оставить
`audit-impact/v1`, repeat-full и receipt v2 вне Slice A.
