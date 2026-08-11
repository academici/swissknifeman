---
id: D22
date: 2026-08-11
status: accepted
item: P2.3
items: [P2.3, P2.4]
supersedes: []
superseded_by: null
actor: repository-owner (delegated conflict resolution via D18 and owner quality directive)
model: gpt-5.6-sol/high (semantic plan-design route; effective selector/effort not independently attested)
evidence: RAG:— findings/P2.2-harness-driver-integrity.md + packages/task/lib/task/plan_status.py + packages/task/tests/test_plan_status.py
---

## Решение

Вставить перед live requalification отдельный Task-owned item P2.3, который исправляет
owner-facing status aggregation и закрепляет её red-first regression. Смесь terminal children и
`⬜ Not started` означает уже начатый aggregate и обязана проецироваться как `🟡 In progress`;
`⬜ Not started` остаётся только для пустого либо полностью не начатого набора. Текущие приоритеты
`🔴 Blocked`, полностью `🟢 Done` и полностью terminal `🟢`/`🟠` сохраняются.

Прежний P2.3 live requalification перенумеровывается в P2.4 и получает terminal P2.3 как явный
input/read gate. Это безопасная forward-only смена адреса: прежний item не имеет journal events,
его generated state показывает `⬜ Not started`, а product execution ещё не начиналось. D18 не
переписывается: его successor-смысл сохраняется, а D22 фиксирует новый порядок и актуальные адреса.

## Consequences

P2 состоит из четырёх последовательных items. До исправления generated `status.md` честно остаётся
известно неверным и не используется как доказательство readiness; после P2.3 текущий план и P2
должны показывать `🟡 In progress`, затем только P2.4 вправе выдать GO/ADJUST. Цена — один
дополнительный Task commit и повтор docs/validator gates; P1 и terminal P2.1/P2.2 остаются
byte-immutable evidence.

## Почему

`status.md` после P2.2 показывает весь план и P2 как `⬜ Not started`, хотя P2.1/P2.2 terminal
green. Source trace воспроизводится в общей fallback-ветке `task.plan_status._phase_status`, а
полный Task validator не содержит mixed-state case. Исправление принадлежит Task package,
материально влияет на agent lifecycle truth и поэтому должно предшествовать field acceptance, а
не скрываться внутри product-free canary. RAG:— (repo-grounded).
