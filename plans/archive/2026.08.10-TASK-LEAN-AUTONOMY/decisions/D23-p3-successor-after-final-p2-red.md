---
id: D23
date: 2026-08-11
status: accepted
item: P3.1
items: [P2.4, P3.1, P3.2]
supersedes: []
superseded_by: null
actor: repository-owner (explicit approval "Утверждаю D23")
model: gpt-5.6-sol/high (semantic plan-design route; effective selector/effort not independently attested)
evidence: RAG:— phases/P2/P2.md + research/10-p2-final-red-owner-outcome.md + brief/01-refinements.md
---

## Решение

Финальный RED P2 и findings F1–F6 принимаются как authoritative terminal evidence, но не как
допустимый итоговый долг. D17 остаётся неизменным: третьего P2 audit, repair или automatic
design-loop нет; стабильные ТЗ P2.1–P2.4, P1 carriers и оба P2 audit-блока заморожены.

P2 qualification остановлена. `🟢` в текущем generated P2.4/P2 view не является release-ready
verdict: штатный recovery Task Contract возвращает `block:LOOP_BUDGET_EXCEEDED`/`n/a`, поэтому
владелец запрещает обход compiler и ручную правку generated state. До появления канонического
owner-outcome projection D23 и rolling handoff являются owner authority для этого расхождения.

Исправления получают новую successor-фазу P3 с двумя стабильными контрактами:

1. P3.1 восстанавливает Task-owned fail-closed route evidence, убирает static config как actual
   route, исправляет duplicate D22 в bundle generator, синхронизирует provider/docs projections и
   принимает только green Task/Skiller/docs gates.
2. P3.2 без product writes квалифицирует полный новый anchor, включая post-P2.3 repair deltas и
   terminal P3.1, и выдаёт GO только при provider-bound route evidence, exact Files reconciliation,
   полном green Validation и write-site `allow/allow` в terminal journal/state.

F5 закрывается owner-reconciliation текущего handoff/roadmap на P3; прежний handoff на P2 audit
больше не исполняется. F6 не получает waiver: это minor debt с обязательным владельцем P3.1.

## Consequences

План остаётся активным и не архивируется. P2 сохраняет RED provenance без переписывания истории,
а release qualification возможна только через terminal P3.1 и новый product-free P3.2 canary.
Если Codex не предоставляет thread-bound model class и effort, P3.1/P3.2 остаются `⬜ Not started`
с waiting Next: config, selector, actor и текст launch-block не превращаются в actual evidence.

## Почему

F2 ломает fail-closed гарантию, F3 оставляет обязательную Validation красной, F1/F4 делают GO
непроверяемым по scope/write-site, а F5 направляет cold-start по ложному маршруту. F6 отдельно
доказывает deterministic generator debt. Новый контракт повторяет owner-authorized successor
pattern D18 и не расходует запрещённый третий цикл P2. RAG:— (repo-grounded:
`phases/P2/P2.md:150-262`, `commands/plan-run.md`, `lib/task/route_evidence.py`,
`lib/task/plan_bundle.py`, `handoff.md`).
