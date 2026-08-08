---
id: D140
date: 2026-08-08
status: accepted
item: P4.4
items: [P4.4]
supersedes: []
superseded_by: null
---

## Решение

`packages/task/tests/data/plan-v2/journal.jsonl` и существующая
`findings/P1.1-fixture.md` становятся явными test carriers P4.4: journal содержит три
одинаковых provisional return, а finding намеренно не несёт достаточного seam, чтобы
обязательный CLI smoke-test
воспроизводимо печатал owner packet. RAG:— (repo-grounded: P4.4 Validation требует
непустой blocking gate именно на этом fixture, тогда как прежний journal не содержал
ни одного return event).

## Почему

P4.4 `Files` прежде не перечислял fixture, но его собственный executable validation
адресует его и утверждает наличие owner packet. Без изменения входа теста это
неисполнимое противоречие, а создание synthetic packet в runtime нарушило бы frozen
ladder. Fixture меняется минимально и остаётся выключенным для lint без Meta opt-in.

## Consequences

P4.4 обновляет journal fixture, а также регенерирует его обязательные state/status/closure
projections, и добавляет их в точный Files item'а; finding остаётся его read-only неполным
seam carrier. Другие test fixtures и планы флота не меняются; `plan-lint` на fixture по-прежнему
имеет 0 errors, потому что Return Loop Gate не добавляется.
