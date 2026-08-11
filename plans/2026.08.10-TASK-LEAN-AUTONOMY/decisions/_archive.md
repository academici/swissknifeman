<!-- plan-projection
projection: decision-archive
projection_version: v1
source_scope: decisions/
through: 2026-08-10/D9
inputs_sha256: 2fc68aa139c0b03207f09aa21e0ba19db2768ed4134dfcc17b4783ff7128cabd
generated_by: task plan-views decisions
-->

# Архив решений

> Не править руками: это генерируемый вид.

| ID | Date | Status | Items | Решение |
|:--|:--|:--|:--|:--|
| D14 | 2026-08-11 | superseded | P1.1 | Фаза не становится закрытой сразу после terminal state её items. Она становится **кандидатом фазы**; свежий audit кандидата предшествует единственному phase-close: `terminal items → phase candidate → task:plan-audit <PLAN-ID> Pn → GREEN → task:plan-close <PLAN-ID> Pn` - audit записывает fingerprint кандидата: relevant scope, terminal item heads и material risk; - `plan-close Pn` отказывает при отсутствующем, RED, unresolved `ATTENTION` либо устаревшем audit; material scope/SHA/risk change инвалидирует старый verdict; - RED или `ATTENTION` исправляются в owning item и только затем кандидат проходит повторный audit; audit не пишет phase `closed-*` event; - `plan-close Pn.m` остаётся только recovery reconciliation для legacy/incomplete item journal или evidence mismatch. Обычная terminalization item происходит его run/exec owner, а normal Next не предлагает item close; - deterministic non-material bookkeeping defect остаётся inline repair D11, но phase нельзя закрыть, пока итоговый audit не GREEN. |
| D16 | 2026-08-11 | superseded | P1.2 | P1.2 GO переводит P1 в terminal-item candidate и направляет Next в `audit-phase: task:plan-audit 2026.08.10-TASK-LEAN-AUTONOMY P1`. Только fresh GREEN по candidate fingerprint разрешает `task:plan-close 2026.08.10-TASK-LEAN-AUTONOMY P1`. ADJUST остаётся nonterminal переходом D8: один durable DecisionRequest и structural waiting на exact owning continuation. Это решение supersedes D8 только в GO-ветке прямого phase close; owner-approved D14 является authoritative lifecycle boundary. |
| D8 | 2026-08-10 | superseded | P1.2 | GO означает: все P1.2 acceptance predicates green, item закрывается `🟢 Done`, а Next ведёт к `close: task:plan-close 2026.08.10-TASK-LEAN-AUTONOMY P1`. ADJUST означает: хотя бы один predicate red/unknown, P1.2 остаётся `🟡 In progress`, через owner tool создаётся ровно один durable DecisionRequest с exact owning-package continuation, а handoff объявляет структурный `waiting: <decision-id resolved> → run-items: task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2`. |
