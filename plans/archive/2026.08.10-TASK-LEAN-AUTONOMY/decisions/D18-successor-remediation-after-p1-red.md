---
id: D18
date: 2026-08-11
status: accepted
item: P2.1
items: [P2.1, P2.2, P2.3]
supersedes: []
superseded_by: null
actor: repository-owner (explicit autonomy and quality directive)
model: gpt-5.6-sol/high (semantic plan-design route; effective selector/effort not independently attested)
evidence: RAG:— brief/01-refinements.md + phases/P1/P1.md + findings/10-p1-final-audit-root-causes.md + research/09-p2-quality-remediation-design.md
---

## Решение

Финальный RED P1 не принимается как допустимый долг и не переоткрывается. D17 остаётся
неизменным: audit attempt 2 и семь Major findings являются terminal historical evidence, третьего
P1 repair/audit/design-loop нет. Исправления получают новый стабильный контракт successor-фазы P2:

1. P2.1 исправляет только Task-owned command/schema/verifier/docs-sync defects и тесты.
2. P2.2 после green P2.1 исправляет Harness-owned v2 driver и cross-package fixtures.
3. P2.3 без product writes повторяет live canary на новом кодовом anchor и принимает только
   полностью green package/root validation с классификацией каждого observed stop.

Исторические scope drift P1.1/P1.2 не переписываются задним числом. P2 объявляет полные Files,
release ledger owner и generated outputs заранее; отклонение становится material trigger, а не
скрытой Completion Note.

## Consequences

План остаётся честным: P1 сохраняет RED provenance, а продукт может стать green только через
новые item commits и независимую requalification. Цена — дополнительная фаза и повтор полного
canary, но ни один Major finding не маскируется как принятый долг.

## Почему

Владелец явно поставил качество и agent fitness выше стоимости и делегировал разрешение
репозиторных конфликтов. Root-cause loop показал, что проблемы устранимы внутри существующих
Task/Harness boundaries и не требуют изменения public/frozen intent. Successor-фаза — штатный
выход owner-autonomy после исчерпанного audit cap; мутация P1 нарушила бы D17 и evidence integrity.
RAG:— (repo-grounded).
