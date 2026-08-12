---
id: D12
date: 2026-08-11
status: accepted
item: P0.2
items: [P0.2, P1.1, P1.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via explicit cross-project telemetry and flexibility directive)
model: gpt-5.6-sol/xhigh (semantic plan-audit/research route; effort self-attested)
evidence: RAG:✅ 2026-08-11 findings/06-cross-project-execution-telemetry.md + research/07-adaptive-failure-and-telemetry-synthesis.md
---

## Решение

Любой failure сначала проходит `observe → minimal reproduce → classify → act → verify`.
Неизолированный tool/status/audit signal сам по себе не меняет product status.

Закрытая классификация:

- `procedural`, `transient`, `dependency-not-ready`, `unrelated-pre-existing` — nonterminal;
  owning-agent применяет safe fallback/local repair/bounded wait либо продолжает независимую
  работу в том же attempt;
- `acceptance`, `safety`, `authority` — terminal для затронутого item'а после воспроизведения;
  unknown outcome необратимой/non-idempotent операции временно считается `safety`, пока actual
  state не reconciled.

Future carrier не существует → `dependency-not-ready/unknown`, не RED текущего producer.
Routing mismatch исправляет dispatch до journal start и не создаёт `blocked` product outcome.
Inherited/unrelated failure сравнивается с baseline delta. Перед terminalization внешнего
процесса проверяются PID/output/state. Один повтор fingerprint требует смены тактики; следующий
тот же fingerprint открывает один scoped breaker/review, не глобальный stop.

## Почему

В двух проектах tool failures массово сосуществовали с полезными изменениями, тогда как
процедурные routing/future/literal/status signals дали десятки block/escalation и повторных
циклов. Stop по фактическому impact сохраняет safety/authority/acceptance и убирает panic по
низкоуровневой причине. RAG:✅ 2026-08-11 (`findings/06-cross-project-execution-telemetry.md`,
`research/07-adaptive-failure-and-telemetry-synthesis.md`).
