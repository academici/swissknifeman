---
id: D10
date: 2026-08-11
status: accepted
item: P1.2
items: [P1.1, P1.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via explicit design-finish remediation instruction)
model: gpt-5.6-sol/high (semantic plan-design route; effort self-attested)
evidence: RAG:— findings/03-design-audit-2026-08-10.md F17/F18 + research/06-design-finish-remediation-f16-f19.md
---

## Решение

Единственный real post-P1.1 canary — фактический запуск
`task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2` от pre-mutation admission до pre-final,
journal/state regeneration и handoff. Для двух условных событий scorecard использует закрытые
значения:

- `local_repair: observed` либо
  `local_repair: not-observed (no eligible local failure fingerprint in the P1.2 live run)`;
- `material_review: observed` либо
  `material_review: not-observed (no D3 material trigger: scope/SHA/risk remained stable)`.

Оба `not-observed` совместимы с GO, если соответствующее событие действительно не возникло и все
остальные acceptance predicates green; replay не подменяет этот live window.

P1.1 до возможного D9 waiting добавляет одну factual root `CHANGELOG.md` запись в `[Unreleased]`
про уже реализованные release-visible instruction/command/docs изменения. Запись не утверждает
GO и не удаляется при ADJUST. Если owning-package remediation после ADJUST меняет опубликованный
смысл, её owner обновляет ту же root ledger запись до своего handoff.

## Почему

Условное событие нельзя сделать обязательным, не провоцируя искусственный дефект или второй
ритуальный loop. Точный `not-observed` сохраняет наблюдаемость отсутствия trigger. Release ledger
описывает shipped change, а не исход canary, поэтому не может зависеть от независимого D9 gate или
GO/ADJUST. RAG:— (repo-grounded: audit F17/F18, D3/D5/D8/D9, root
`development-validation`).
