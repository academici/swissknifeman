---
id: D3
date: 2026-08-14
status: accepted
item: P1.2
items: [P1.1, P1.2]
supersedes: []
superseded_by: null
---
## Решение

Latest normalized phase audit проверяется до unaudited admission. Его matching GREEN
разрешает close; stale/ATTENTION/RED/invalid отказывает. Без audit direct close
разрешён только valid `isolated` + empty seams + `no` + `direct-close-eligible`
при полном objective green evidence. `Review` и item count не являются blockers.

Валидный canonical assurance payload входит в fingerprint только при наличии;
missing/invalid legacy input не добавляет key/sentinel.

## Почему

Такой порядок не даёт declaration скрыть negative audit, а conditional canonical
digest одновременно ловит semantic assurance edits и сохраняет historical P1 fingerprint.

**Evidence:** RAG:— (`research/01-slice-a-design.md`, `findings/04-adversarial-verification.md`).
**Actor:** design/gpt-5.6-sol/high.

## Consequences

`auto`, named internal seams, public/security/live, missing/invalid assurance, non-green/material
evidence остаются audit-required. Slice B/C machinery не реализуется.
