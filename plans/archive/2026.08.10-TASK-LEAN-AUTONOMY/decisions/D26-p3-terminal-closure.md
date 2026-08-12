---
id: D26
date: 2026-08-11
status: accepted
item: P3
items: [P3, P3.2]
supersedes: [D25]
superseded_by: null
actor: repository-owner (explicit terminal-closure directive)
model: gpt-5.6-sol/high (semantic plan-design route)
evidence: RAG:— brief/01-refinements.md Owner terminal-closure directive + phases/P3/P3.md + packages/task/lib/task/plan_gates.py + installed Codex task cache
---

## Решение

Для P3 эта запись заменяет terminal audit-loop D17 и D25. Единственный допустимый путь:

`reproduce → owning-source repair → deterministic validation → P3.2 requalification → task:plan-close P3`

`phase-close: direct-green-validation`

- любой воспроизводимый дефект P3 исправляется в owning source в том же ходе; canonical
  `plan-close`, regression tests и generated provider surfaces принадлежат Task, установленный
  Codex cache обновляется только штатным plugin installer;
- P3.2 стартует только после source/provider/cache parity и fresh native model-route verification;
  повторный non-GREEN возвращается к причине и тем же проверкам, а не создаёт audit, repair item,
  formal handoff или новый lifecycle loop;
- после полного green P3.2 очищает текущие P3.1/P3.3 deviations append-only terminal events,
  сохраняет historical rows неизменными и немедленно передаёт тот же root в
  `task:plan-close 2026.08.10-TASK-LEAN-AUTONOMY P3`;
- terminal P3 обязан иметь четыре `🟢 Done`, пустые `Known Deviations`, `Pending Work` и
  `Escalation Needed`, нулевые открытые риски и все заявленные checks green.

## Consequences

D25 и P3-ветка D17 больше не дают финальный audit attempt 2 или owner-incident continuation.
**Consequences:** Task получает узкий проверяемый phase-close override только по explicit accepted
phase-scoped owner decision с маркером `phase-close: direct-green-validation`; цена — canonical
command/runtime/provider docs и cache должны быть byte-current до закрытия. Historical audit и
journal evidence остаются append-only, но не являются текущим deviation state после полного repair.

## Почему

Owner directive запрещает закрывать P3 с известным долгом либо заменять исправление очередным
ритуалом. Current source показывает, что обычный `phase_close_gate()` принимает только audit GREEN,
а установленный Codex `task:plan-run` cache отстаёт от generated D24 adapter. Без D26 честный
`task:plan-close P3` недостижим, либо потребовал бы запрещённый synthetic audit. RAG:—
(repo-grounded: `brief/01-refinements.md`, `packages/task/lib/task/plan_gates.py`,
`packages/task/adapters/codex/skills/task-plan-run/command.md`).
