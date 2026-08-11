---
id: D14
date: 2026-08-11
status: superseded
item: P1.1
items: [P1.1]
supersedes: []
superseded_by: D17
actor: repository-owner (explicit lifecycle correction directive)
model: gpt-5.6-terra/high (actual plan-amendment session; semantic plan-design route unavailable in this session)
evidence: repo-grounded: findings/07-preclose-audit-lifecycle.md
---

## Решение

Фаза не становится закрытой сразу после terminal state её items. Она становится **кандидатом
фазы**; свежий audit кандидата предшествует единственному phase-close:

`terminal items → phase candidate → task:plan-audit <PLAN-ID> Pn → GREEN → task:plan-close <PLAN-ID> Pn`

- audit записывает fingerprint кандидата: relevant scope, terminal item heads и material risk;
- `plan-close Pn` отказывает при отсутствующем, RED, unresolved `ATTENTION` либо устаревшем
  audit; material scope/SHA/risk change инвалидирует старый verdict;
- RED или `ATTENTION` исправляются в owning item и только затем кандидат проходит повторный
  audit; audit не пишет phase `closed-*` event;
- `plan-close Pn.m` остаётся только recovery reconciliation для legacy/incomplete item journal
  или evidence mismatch. Обычная terminalization item происходит его run/exec owner, а normal
  Next не предлагает item close;
- deterministic non-material bookkeeping defect остаётся inline repair D11, но phase нельзя
  закрыть, пока итоговый audit не GREEN.

## Почему

Существующий путь сначала предлагал `plan-close Pn`, а затем `plan-audit Pn`; найденное аудитом
требовало повторного close/design/audit круга. В Agelto P2.7 это прямо выражено как close P2,
then fresh audit P2, а Task command surface описывает audit закрытой фазы. Такой порядок скрывает
реальный acceptance gate и делает `plan-close Pn.m` похожим на обычный следующий шаг.

P1.1 меняет protocol source, lint, provider projections, tests и canonical documentation. Agelto
сейчас служит consumer fixture/evidence, а не write target: его существующее dirty дерево не
трогается этой коррекцией.
