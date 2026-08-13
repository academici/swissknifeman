---
id: D30
date: 2026-08-13
status: accepted
item: P6.2
items: [P6.2]
supersedes: []
superseded_by: null
---

## Решение

AUDIT-CAP: третьего Audit P6 нет. Владелец разрешает единственный forward
repair P6.2: повторить исходные Validation для P6.2 только в fresh native roots
с provider-attested route; новых terminal attempts после закрытия фазы не
допускается.

Это разрешение применяет уже accepted D29: построить exact committed
`v0.13.2` candidate с byte-fresh P6.2 carriers, выполнить всю release-gate
matrix в clean detached worktree без overlay и создать только новый локальный
annotated tag после всех нулевых exit-кодов. `v0.13.0` и `v0.13.1` immutable.

## Почему

Второй Audit P6 воспроизвёл ложный зелёный verdict для exact `v0.13.1`.
Остановка только по числу аудитов оставляла бы D29 неисполняемым, хотя его
owner response уже задаёт один ограниченный forward recovery и запрещает
третий аудит.

## Consequences

Разрешён ровно один выпускной recovery P6.2 в границах его stable Files и
plan-carve-out. Нового Audit P6, изменения старых tag, push, GitHub release и
registered-project rollout это решение не авторизует.
