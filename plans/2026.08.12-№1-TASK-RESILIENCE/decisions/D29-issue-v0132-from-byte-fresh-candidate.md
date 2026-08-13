---
id: D29
date: 2026-08-13
status: accepted
item: P6.2
items: [P6.2]
supersedes: [D27]
superseded_by: null
---

## Решение

Применён owner-option `repair-and-patch-release-v0.13.2` из DecisionRequest
`P6-audit-v0131-validation-boundary-2026-08-13`. P6.2 строит новый exact committed candidate
с byte-fresh plan carriers, повторяет полную release-gate matrix в clean detached worktree без
overlay и только после зелёного результата создаёт новый локальный annotated `v0.13.2`.
`v0.13.0` и `v0.13.1` остаются на прежних tag object/peeled commit. RAG:—
(owner/repo-grounded: `decisions/queue.jsonl`, `findings/25-P6-v0131-exact-validation-audit.md`,
`research/10-P6.2-v0132-exact-candidate-design.md`).

## Почему

Exact `v0.13.1` не прошёл обязательный Task validator: зелёное утверждение зависело от позднего
bookkeeping overlay. Перемещение старого tag уничтожило бы immutable release evidence, а принятие
известного validation gap оставило бы машинно ложный release verdict. Forward patch с точным
candidate SHA сохраняет историю и даёт воспроизводимую границу qualification.

## Consequences

D29 supersedes D27 только как активный recovery target: исторический `v0.13.1`, D27 и его
исправленный красный capsule сохраняются без переписывания. Цена решения — ещё один patch tag,
новый capsule/finding и полный повтор всех release gates. P6.3/P6.4 evidence, push, GitHub release,
registered rollout и P0–P5 остаются вне scope.
