---
id: D32
date: 2026-08-13
status: accepted
item: P7
items: [P7, P7.0, P7.1, P7.2, P7.3, P7.4, P7.5]
supersedes: []
superseded_by: null
---

## Решение

Возобновить архивный план в active-path только для P7: принять pinned working-tree candidate и
`artifacts/roadmap-snapshots`, исполнить шесть отдельных fresh-session items, затем провести phase
audit/close и снова архивировать план.

## Почему

После прежнего archive появились уже измеренные Task lifecycle follow-ups и подготовленный
working-tree diff. Новый независимый план потерял бы решения/incident evidence P0–P6, а
переисполнение закрытых фаз исказило бы immutable release history. P7 продолжает тот же предмет,
но сначала восстанавливает backward-compatible lint admission, затем отделяет runtime, delivery, audit safety, generated canon и closeout по проверяемым commit
границам. RAG:— (owner-grounded: `brief/01-refinements.md`; repo-grounded:
`findings/29-P7-postarchive-working-tree-inventory.md`,
`research/11-P7-postarchive-continuation-design.md`).

## Consequences

P0–P6, `v0.13.0`/`v0.13.1`/`v0.13.2`, push/GitHub release и completed rollout остаются
immutable/out of scope. P7 не выпускает новый tag: результат остаётся в `[Unreleased]`.
`plans/ACTIVE.md` указывает на этот plan до terminal P7 + GREEN audit + close; затем отдельный
`task:plan-close archive` возвращает каталог в `plans/archive/`.
