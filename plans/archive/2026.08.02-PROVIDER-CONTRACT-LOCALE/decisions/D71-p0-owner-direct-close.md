---
id: D71
date: 2026-08-14
status: accepted
item: P0
items: [P0]
supersedes: [D70]
superseded_by: null
actor: repository-owner (explicit phase-close directive)
model: n/a (owner decision)
evidence: RAG:— terminal P0.1–P0.10 state, three completed P0 audit passes, finding 20, and owner cost/quality decision
---

## Решение

Владелец разрешает немедленно закрыть P0 вручную через
`phase-close: direct-green-validation`, не запуская четвёртый полный аудит. Уже выполненные
item-validation и полный audit baseline переиспользуются: P0.1–P0.10 терминальны, P0.9/P0.10
закрыли последний material delta, а audit attempt 3 остановился на self-invalidating shared Task
bookkeeping seam, не на новом P0 product defect.

Повторный full audit для текущего material lineage не авторизован. Shared subject/fingerprint и
экономный `full|delta|gate-rebind` runtime остаются в roadmap; они не блокируют практическую
разработку P1. P1.1 перед первой mutation обязан повторить только объявленный P0.10 live admission
gate. RAG:— (repo-grounded: `phases/P0/P0.md`,
`findings/20-p0-audit-terminal-binding-2026-08-14.md`, P0 item states and
`roadmap/2026.08.14-repeat-audit-evidence-reuse-budget.md`).

## Почему

Три полных прохода уже дали достаточную bounded confidence, а следующий полный проход повторил бы
неизменённый продукт из-за дефекта самого audit protocol. Стоимость такого повтора выше
практического риска: P0 разбита на десять independently validated items, material correction уже
проверена, live security evidence имеет отдельный use-site gate, а оставшийся runtime-долг
локализован и не меняет provider/fleet product semantics.

## Consequences

D70 superseded только в требовании ещё одного финального GREEN P0 audit перед close. Его P0.9/P0.10
product semantics, frozen D67 boundary и обязательный P1 live admission сохраняются. P0 закрывается
как `🟠 Done with deviations` из-за исторического material deviation P0.1; P1 открывается без
повторного product audit. Finding 20 и audit-economy roadmap остаются открытым Task runtime долгом,
но не превращаются в новый phase loop.
