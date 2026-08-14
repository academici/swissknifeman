---
id: D4
date: 2026-08-14
status: accepted
item: P2.1
items: [P2.1]
supersedes: []
superseded_by: null
---
## Решение

Recovery закрывает только `2026.08.02-PROVIDER-CONTRACT-LOCALE P1` через
штатный phase-close после exact preflight fingerprint `7ce1…` и reuse journal line 97.
Второй audit, P1.1–P1.3 Validation и любое изменение P1 product carriers запрещены.

## Почему

Целевой GREEN audit уже полностью совпадает с current candidate; единственный
воспроизведённый blocker — legacy subject literal comparison.

**Evidence:** RAG:— (`findings/03-p1-recovery-recon.md`).
**Actor:** design/gpt-5.6-sol/high.

## Consequences

P2.1 имеет hard precondition на exact fingerprint/gate/journal identity и делает отдельный
cross-plan closure commit, не смешанный с Task policy implementation.
