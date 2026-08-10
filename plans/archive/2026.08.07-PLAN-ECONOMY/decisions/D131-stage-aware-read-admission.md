---
id: D131
date: 2026-08-08
status: accepted
item: P2.8
items: [P2.8, P2.9, P2.10, P3.3]
supersedes: []
superseded_by: null
---
## Решение

**Порог и единица `read-budget` не меняются; P2.8 разрезается на три последовательных
утверждения.** P2.8 закрывает корректность converter/migration и честный baseline всех отказов;
P2.9 замораживает stage-aware admission (`historical-pre-v2` · `pending-producer` · `ready`),
встраивает его в `plan_weight` и устраняет общий oversized hotspot пакета `task`; P2.10
пересобирает read graph этого плана и только затем выносит финальный self-host verdict. Ready-item
по-прежнему обязан hard-pass D2(a)+D2(b) до pre-mutation; warning-mode, threshold bump, path
allowlist и незамеренное удаление входов запрещены. RAG:— (repo-grounded:
`findings/21-p2.8-read-admission-diagnosis-2026-08-08.md`;
`research/20-p2.8-stage-aware-admission-redesign.md`).

## Почему

Первый P2.8 verdict проверил только четыре превышения D2(a), хотя фактический output несёт также
oversized/missing/unresolved D2(b). Требовать outputs P3–P6 до закрытия P2 создаёт phase-first
deadlock; считать их нулём или удалить из измерения нарушает fail-closed и D74. Владелец ранее
отклонил RED-долг и полностью делегировал технический способ закрытия (`brief/01-refinements.md`,
D126), а текущим вызовом `task:plan-design ... P2.8` открыл именно этот owner gate.
RAG:— (owner-grounded + repo-grounded: `brief/01-refinements.md`; `handoff.md`; machine output
`plan-weight`, 2026-08-08).

## Consequences

Фаза P2 растёт с 8 до 10 items и не закрывается на миграции: P3 остаётся недоступна до P2.10.
Публичный контракт получает minor revision без смены чисел/единицы; P3.3 реализует hard gate уже
по stage-aware semantics. Цена — два дополнительных последовательных исполнения и поддержка
producer edges; выигрыш — отсутствие ложного зелёного, deadlock и переписывания исторических ТЗ.

