---
id: D3
date: 2026-09-20
status: superseded
item: P1.1
items: [P1.1, P2.1, P3.1, P4.1, P5.1]
supersedes: [D1]
superseded_by: D8
---
# D3 — Detail every phase, audit the whole design, then execute

**Actor:** gpt-5.6-sol/high
**Evidence:** RAG:— owner lifecycle correction, 2026-09-20

## Решение

P1–P5 детализируются полностью до любого execution. Затем один сквозной
design audit проверяет межфазные контракты и запечатывает execution routing: состав и
порядок батчей, точную модель `Grok 4.6` или `Composer 2.5`, effort/review и профильные
и provider-specific исправления. Audit findings применяются в owning contracts одним bounded
fix pass; execution открывается только после GREEN focused re-check и регенерации projections/bundles.

## Почему

Владелец выбрал полную сквозную детализацию до исполнения, чтобы модели и батчи
опирались на целый план, а не на частичную rolling-wave картину. Недостающие runtime
outputs можно описать как typed predecessor inputs и execution DoR-gates, не выдумывая их значения.

## Consequences

D1 заменён в части rolling-wave order и phase-local model gate; его пятифазная декомпозиция
сохраняется. D2 не изменён. P1.1 остаётся detailed, но не запускается; следующий шаг —
детализация P2, затем P3, P4, P5, global design audit/fixes и только после них P1.1 execution.
