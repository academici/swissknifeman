---
id: D12
date: 2026-08-12
status: accepted
item: P0.3
items: [P0.1, P0.2, P0.3]
supersedes: []
superseded_by: null
---
## Решение

Не принимать P0 с долгами финального RED-аудита. Исправить resolution plan-relative и
repo-relative `Files` в `phase_candidate_fingerprint()`, покрыть оба класса regression test,
реконсилировать полную карту material deviations и generated evidence carriers.

AUDIT-CAP: третьего Audit P0 нет; после этой remediation фаза закрывается штатным `task:plan-close`
только при `allow` deterministic gates. RAG:— (owner-grounded: решение владельца
2026-08-12; repo-grounded: последний Audit P0 и commit `28f2d2b2`).

## Почему

RED затронул stale-audit safety: четыре существующих product carrier не входили в byte-bound
fingerprint. Принятие P0 с этим долгом сохранило бы ложный current-runtime verdict; третий audit
запрещён исчерпанным AUDIT-CAP.

## Consequences

P0 сохраняет `🟠 Done with deviations` из-за material runtime changes вне read-only scope, но
закрытие разрешено только после полного перечисления этих changes, регенерации owner views и
успешного owner-decision close gate с D12. P1 не открывается до terminal receipt закрытого P0.
