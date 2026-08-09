---
id: D153
date: 2026-08-09
status: accepted
item: P6.7
items: [P6.7, P6.8]
supersedes: []
superseded_by: null
actor: gpt-5.6-sol/high
---

## Решение

Выпустить `acceptance-protocol` v1.1.1 как identity-only successor: threshold, unit,
scope manifest, admission reducer, arms, anti-displacement, roles/confounds и session canary
байтово-семантически равны v1.1.0, а measurement получает только pinned implementation
provenance `c0ee730c` и SHA-256 production module/launcher. `prior_results` сохраняет v1.0.0
RED и v1.1.0 NOT-RUN: последний нельзя считать acceptance attempt, потому что preflight доказал
несоответствие вызываемой реализации declared scope до arm A. RAG:— (owner/repo-grounded: D152;
`findings/P2.10-five-slot-measurement-repair-2026-08-09.md`).

## Почему

Frozen v1.1.0 нельзя молча перепривязать к другой реализации после обнаруженного дефекта.
Patch version делает repair identity проверяемой и сохраняет весь observed history, не меняя
ни одного acceptance predicate. Новая field snapshot уже прогнозирует fail, но P6.7 не
адъюдицирует его: результат появляется только из отдельного retained arm-A artifact P6.8.

## Consequences

P6.8 обязан сверить v1.1.1 hashes и `measurement.implementation`, затем выполнить command
дословно. v1.0.0 остаётся RED; v1.1.0 остаётся NOT-RUN с прежними hashes/commit. Любой ready
failure в новом raw output немедленно даёт `fail` и запрещает arm B, canary и P6.9. Версия
не разрешает править terminal specs, admission states или числа ради прохождения.
