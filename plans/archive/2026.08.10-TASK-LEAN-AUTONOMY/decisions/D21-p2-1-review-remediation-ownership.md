---
id: D21
date: 2026-08-11
status: accepted
item: P2.1
items: [P2.1]
supersedes: []
superseded_by: null
actor: repository-owner (delegated conflict resolution via D18)
model: gpt-5.6-terra/high (session route; effective effort self-attested)
evidence: RAG:— isolated P2.1 review of f3c0da6f + scripts/docs-sync.sh + packages/task/lib/task/plan_layout.py
---

## Решение

Принять обе находки изолированного review P2.1 как terminal-blocking для item'а и
расширить exact Files только их владельцами:

1. Зафиксировать сгенерированный `docs/task/reference/provider-commands.md` через
   `scripts/docs-sync.sh`, потому что этот destination отслеживается Git и в clean checkout
   должен byte-for-byte совпадать с package source.
2. Перенести fail-closed проверку неполной v2 phase directory в канонический
   `task.plan_layout.phase_paths()`: каждый `phases/Pn/` обязан иметь readable regular
   `Pn.md`. Citation verifier по-прежнему не владеет topology glob и получает ошибку
   от canonical resolver.

## Consequences

P2.1 получает второй code commit после `f3c0da6f`; terminal review повторяется на
всём item diff. Generated aggregate не редактируется вручную. Все consumers `phase_paths()`
получают одинаковый fail-closed layout contract вместо verifier-only костыля.

## Почему

`git archive f3c0da6f` содержит stale tracked aggregate, поэтому semantics «отсутствующий
cache допустим» не закрывает clean-checkout acceptance. А дублирование
`phases/Pn/` glob в citation verifier нарушило бы owner boundary, ради которой P2.1 уже
перешёл на `task.plan_layout`. RAG:— (repo-grounded).
