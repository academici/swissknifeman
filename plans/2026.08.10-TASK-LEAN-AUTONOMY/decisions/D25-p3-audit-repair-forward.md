---
id: D25
date: 2026-08-11
status: accepted
item: P3.4
items: [P3.1, P3.2, P3.3, P3.4]
supersedes: []
superseded_by: null
actor: repository-owner (explicit bounded audit repair-forward directive)
model: gpt-5.6-sol/high (current semantic plan-design route)
evidence: RAG:— phases/P3/P3.md Audit P3 + journal.jsonl:51-57 + git refs ddc19647/d8214950/57a922b3/ec5c71bc
---

## Решение

Первый RED audit P3 разрешает ровно один bounded repair-forward по D17. P1/P2, их RED
provenance и прежние journal-строки не изменяются. P3 реопенится только для
следующей последовательности:

1. Plan-only amendment коммитит D25, P3.4, исправленные P3.1/P3.2/P3.3,
   bundles, roadmap и handoff до любого нового journal start.
2. P3.4 на этом committed anchor делает focused unittest исполнимым через
   explicit `PYTHONPATH=tests`, не меняя test/product code. Он append-only корректирует
   P3.1/P3.3 в `closed-deviations`: P3.1 честно хранит historical full-validator red,
   P3.3 — undeclared `test_provider_command_parity.py` и post-factum spec/decision provenance.
   Каждый числовой claim несёт форму `<count> (на <40-hex git-ref>)`.
3. P3.3 `Files` включает фактически изменённый parity test, но это не стирает
   historical scope deviation коммита `57a922b3`.
4. После terminal P3.4 его report/journal/generated views/handoff коммитятся как
   predecessor bookkeeping anchor. P3.2 attempt 2 стартует из отдельного native
   Codex process с `-m gpt-5.6-terra -c 'model_reasoning_effort="high"'`; его
   `session_id` обязан отличаться от P3.4 и historical `019ff1c3-afd4-7531-8b05-908d1b12552f`.
   Новый report не переписывает прежний P3.2 report.
5. Следующий P3 audit — финальный attempt 2; третьего repair/audit нет.

## Consequences

Historical green P3.1/P3.3/P3.2 больше не используется как qualification evidence:
append-only state покажет deviations, а release qualification даст только fresh P3.2
attempt 2. Цена — один новый report-only item, один отдельный native rerun и точные
plan-only commit boundaries. Product semantics и frozen P1/P2 не меняются.

## Почему

Audit воспроизвёл два import failure, undeclared product path, shared P3.3/P3.2 session,
post-factum P3.3 spec и unanchored counts. Узкий повтор доказал, что `PYTHONPATH=tests`
делает исходные module sets green без product write: 144 и 63 tests. Остальные
находки требуют append-only provenance и fresh-session boundary, а не новой telemetry
или product implementation. RAG:— (repo-grounded: `phases/P3/P3.md`, `journal.jsonl:51-57`,
`packages/task/tests/fixtures.py`, commits `ddc19647`, `57a922b3`, `ec5c71bc`).
