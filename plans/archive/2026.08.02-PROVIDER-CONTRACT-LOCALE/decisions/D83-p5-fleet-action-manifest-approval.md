---
id: D83
date: 2026-08-15
status: accepted
item: P5.1
items: [P5.1, P5.2, P5.3, P5.4]
supersedes: []
superseded_by: null
---
## Решение

Владелец утверждает immutable fleet action manifest
`sha256:8c134c75214cff8dc4193f3b251e1afaf5c3041135a942976571068ad527bae4`
и связанные action-set IDs:

- P5.2: `action-set-7fc7d9fa6332f7d4613a8408`;
- P5.3: `action-set-ea341e09394d4234f5d8f5ab`;
- P5.4: `action-set-09bca52acb3e6631c2b30907`.

Manifest содержит 13 421 строку `no-op-unresolved` для 23 protected projects и разрешает
ровно ноль consumer/provider writes. DecisionRequest
`P5.1-fleet-action-manifest-owner-approval` закрыт выбором `approve`; response привязан к
`action_digest=f24299dba95bf10c7bf5b038f779ba0086eb41bff425d892f122d6a13977640d`.

## Почему

Terminal P0 classification не доказала ни одной строки, которую допустимо автоматически
перевести в preserve/relink/refresh/quarantine. Замороженный no-write manifest сохраняет exact-set
coverage и честно оставляет все строки unresolved, не выводя authority из live drift.
RAG:— (repo-grounded: P0 classification, frozen manifest and owner response carrier).

## Consequences

P5.1 может быть закрыт после зелёной проверки carrier'ов. P5.2–P5.4 обязаны принимать только
указанные action-set IDs; их пустые множества не разрешают consumer/provider mutation. Любое
изменение manifest hash, source identity или action-set ID требует новой owner decision.
