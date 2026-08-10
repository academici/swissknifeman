---
id: D142
date: 2026-08-08
status: accepted
item: P4
items: [P4, P4.2, P4.4, P4.6]
supersedes: []
superseded_by: null
---

## Решение

**Реоткрыть P4 и реконсилировать RED-аудит теми же producer-items P4.2, P4.4 и P4.6.** P4.2
выводит plan-local `return_event_id` как `journal.jsonl:<physical-line>` вне frozen fingerprint
tuple/namespace и коммитит durable v2 fixture; P4.4 объявляет фактический integration write-site
`packages/task/lib/task/plan_lint_checks/engine.py` и доказывает его вызов; P4.6 выбирает первую
schema-valid независимую запись по точному event id, использует для текущего gate только judgement
текущего event, собирает все принятые event-scoped judgements в owner packet и коммитит acceptance
artifacts до bookkeeping. RAG:— (repo-grounded: `phases/P4/P4.md` audit, frozen
`return-loop-v1.md:24-35,66-72`, `return-judgement-v1.md:56-104`, git trees `f3b21406`,
`8f2cacd2`, `df6d098b`, `22e2dc98`; синтез `research/21-p4-audit-reopen-2026-08-08.md`).

## Почему

Так закрываются все пять findings без нового carrier и без переписывания истории. Event identity
уже обязательна frozen judgement schema, а physical journal line стабилен в append-only carrier;
он связывает запись с событием, не меняя группирующую идентичность. Возврат ownership к исходным
items делает producer→consumer карту честной и позволяет новому terminal state назвать старые
commit-boundary deviations.

## Consequences

**Consequences:** D140 остаётся неизменяемым историческим решением о первом fixture diff в P4.4;
D142 корректирует ownership только для нового remediation slice: P4.2 обязан произвести собственный
committed fixture и event identity, а исторический `8f2cacd2` не переписывается. Цена — три
последовательных rework-коммита и повторное закрытие P4. P4.1/P4.3/P4.5, frozen contracts,
`same_return_max=2`, journal schema/старые строки, P5/P6, `packages/artifex`, corpus и baseline не
меняются.
