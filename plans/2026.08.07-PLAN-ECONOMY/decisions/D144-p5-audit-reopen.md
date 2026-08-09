---
id: D144
date: 2026-08-09
status: accepted
item: P5
items: [P5, P5.4, P5.5]
supersedes: []
superseded_by: null
---

## Решение

**Реоткрыть P5 и реконсилировать RED-аудит существующими producer-items P5.4 → P5.5.** P5.4
принуждает frozen request/response/auto-answer schema на каждом ingress, применяет выбранный option
по outcome и регенерирует subject state/status после каждого перехода; только `apply` возобновляет
root. P5.5 заменяет статическую acceptance исполняемым producer-based прогоном policy auto-answer и
owner `continue`/`park`/`reject`, коммитит validator/results/report в item tree и воспроизводит их из
detached tree. RAG:— (repo-grounded: `phases/P5/P5.md` Audit P5, синтез
`research/22-p5-audit-reopen-2026-08-09.md`).

## Почему

Frozen contracts P5.1/P5.2 достаточны и audit-verified; дефекты находятся в runtime consumer и
доказательстве. Новый successor-item создал бы второго владельца `plan_requests.py`, а расфриз
контрактов лечил бы не тот слой. Последовательный rework сохраняет producer→consumer карту и даёт
P5.5 честный вход после исправленного P5.4.

## Consequences

**Consequences:** версия плана поднимается до 0.29.0, фаза и P5.4/P5.5 возвращаются в `🟡`; старый
Phase Handoff инвалидируется, прежние item commits/state остаются историей. Цена — два новых
item-коммита, повторная closure/audit P5 и расширенная negative/e2e матрица. Frozen
`decision-request` v1, `authority-frame` v1, owner hash D143, P4 contracts/cap, reader-contract paths,
P6 и `packages/artifex` не меняются. Audit finding 6 о write-scope команды остаётся отдельным
owning-protocol долгом и не считается закрытым D144.
