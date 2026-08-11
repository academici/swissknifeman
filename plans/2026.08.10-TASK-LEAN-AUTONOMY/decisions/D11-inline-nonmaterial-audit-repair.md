---
id: D11
date: 2026-08-11
status: accepted
item: P0.2
items: [P0.2, P1.1, P1.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via explicit field feedback during final design audit)
model: gpt-5.6-sol/xhigh (semantic plan-audit route; effort self-attested)
evidence: RAG:— brief/01-refinements.md + findings/05-inline-audit-repair-friction.md
---

## Решение

Non-material deterministic plan-bookkeeping defect, найденный design/audit root внутри разрешённых
plan carriers, исправляется inline в том же attempt. После одной regeneration + deterministic gate
rerun этот attempt может завершиться `GREEN`; defect не создаёт `ATTENTION`, новый design/audit
pass, новую root-сессию или reopen.

Envelope ограничен freshness/navigation typo и generated-view drift без изменения product/spec/
acceptance/authority semantics. Sealed item scope, material finding, model judgement, security,
необратимость или owner authority остаются обычным finding/gate и inline не маскируются.

## Почему

Остановка исполнения из-за одношаговой bookkeeping-мелочи воспроизводит ритуальный цикл, который
этот план удаляет. Детерминированная repair + rerun даёт более сильное evidence с меньшей задержкой,
не ослабляя material boundaries. RAG:— (repo-grounded: `brief/01-refinements.md`,
`findings/05-inline-audit-repair-friction.md`, D2/D3).
