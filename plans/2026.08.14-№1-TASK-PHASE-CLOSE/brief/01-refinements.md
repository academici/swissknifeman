# Refinements

## 2026-08-14 — research synthesis

- Выход текущего `$ task:design` — только durable design artifacts; production-код
  пишет отдельный routed execution root.
- Текущий normalizer `review_policy.phase_audit_subject()` остаётся единственным
  владельцем audit subject; новая параллельная identity не создаётся.
- Валидный assurance участвует в candidate fingerprint как optional канонический
  payload. Missing legacy assurance не добавляет sentinel/key и поэтому сохраняет P1
  fingerprint `7ce1e79c9c9ed40e325b7489ea01cf5dc0ee607f3425b91f674f7ac853c40b92`.
- Latest normalized phase audit имеет приоритет над unaudited direct-close policy:
  matching GREEN разрешает close; stale/ATTENTION/RED/invalid запрещает его.
- Две фазы разделяют public Task policy implementation и cross-plan recovery; это
  реальная commit/audit boundary, а не микродекомпозиция.
- Current `plan-lint` запрещает `Version`, `Update Log` и `## Обсуждение` в layout-v2
  `plan.md`, хотя installed authoring projection их требует. Machine gate соблюдён;
  provenance остался в Meta/journal, а trade-off — в research/D3.
