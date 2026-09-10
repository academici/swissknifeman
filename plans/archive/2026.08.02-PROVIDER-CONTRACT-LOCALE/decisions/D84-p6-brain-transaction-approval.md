---
id: D84
date: 2026-08-16
status: accepted
item: P6.1
items: [P6.1]
supersedes: []
superseded_by: null
---
## Решение

Владелец утверждает immutable Brain repair plan
`sha256:7390e46109c27cf8a2e48c7935a761726356a2bd74f3088cc53eae8f4457ce70`
с action set `action-set-4f53cda18c2baa0c0354bb5f`, exact preimage
`sha256:533b051162af0568d7ad41d03608176817ce0ad94d6dd280b20ce6e7d5d83911`
и rollback `rollback-whole-brain-exact-preimage`.

Action set пуст и разрешает ровно ноль Brain/provider/credential/trust/dependency/profile/
channel/budget/P5 writes. DecisionRequest `P6.1-brain-empty-action-set` закрыт выбором
`approve`; response привязан к
`action_digest=f3434f64cdaf6a19ab7cdc3aa5a46a83a9996251a53364d47f68488a6c29dfae`.

## Почему

Свежие публичные read-only проверки не доказали ни одного допустимого автоматического
исправления. Пустая транзакция сохраняет frozen authority boundaries и даёт durable WAL/readback
carrier без маскировки оставшихся security, trust, dependency, profile, channel, budget и P5
диагностик.

## Consequences

P6.1 может выполнить только plan-local WAL и fresh readback для этого точного plan/action-set/
preimage. Любое изменение plan hash, preimage, action-set ID или rollback ID требует нового
owner decision; Brain и provider targets остаются read-only.
