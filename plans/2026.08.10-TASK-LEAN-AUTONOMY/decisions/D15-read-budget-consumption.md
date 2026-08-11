---
id: D15
date: 2026-08-11
status: accepted
item: P1.2
items: [P1.1, P1.2]
supersedes: []
superseded_by: null
actor: plan-designer
model: gpt-5.6-sol/high (semantic plan-design route; actual selector/effort not independently attested)
evidence: RAG:— plans/2026.08.10-TASK-LEAN-AUTONOMY/handoff.md + packages/task/lib/task/plan_admission.py + plans/archive/2026.08.07-PLAN-ECONOMY/root/contracts/read-budget-v1.md
---

## Решение

План потребляет frozen `read-budget` v1.1.0 без изменения threshold, qualified unit,
single-read limits, anti-displacement или stage-aware admission. План-владелец хранит точную
копию в `root/contracts/read-budget-v1.md`; P1.2 читает её через digest-qualified bundle, а
pre-mutation admission проверяет P1.1/P1.2 до canary.

Обозначения `D2(a)`/`D2(b)` внутри frozen contract относятся к donor contract
`2026.08.07-PLAN-ECONOMY`, а не заменяют и не supersede локальное решение D2 этого плана про
repair envelope. P1.1 остаётся терминальным `🟠 Done with deviations`: carrier добавляется
plan-designer'ом вне sealed Files пункта и не переписывает его историю.

## Почему

Task admission не имеет числового fallback и fail-closed загружает ровно plan-owned
`root/contracts/read-budget-v1.md`. Handoff P1.1 зафиксировал отсутствие carrier как material
deviation, которое обязано быть снято до активации P1.2. RAG:— (repo-grounded:
`packages/task/lib/task/plan_admission.py`, `packages/task/docs/reference/plan-read-admission.md`,
`findings/P1.1-runtime-alignment.md`).
