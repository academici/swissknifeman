---
name: cross-layer-change-checklist
bucket: general
version: 0.1.0
description: "Use when a change spans multiple layers: code, authorization, UI, docs, tests."
risk: read
persona: oss-dev
tags: [checklist, workflow, validation]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Cross-layer Change Checklist

Use for changes spanning multiple system layers.

## Mandatory verification chain

1. **Domain & contracts**
   - Enum/DTO/signatures synced.
   - No hidden meaning changes in names.

2. **Authorization**
   - Permission enum ↔ policy method ↔ gate definition aligned.
   - Negative access cases covered.

3. **HTTP/API**
   - Route → Controller → Action/Service chain intact.
   - Controller stays thin.

4. **Frontend**
   - UI triggers updated.
   - No hardcoded URLs when route/action helpers exist.
   - Error and access-denied states handled.

5. **Data/migrations**
   - Schema and model contracts aligned.
   - Renames/moves don't break existing relations.

6. **Docs & agent context**
   - Update relevant docs (`docs/workflow/*`, `docs/dev/*`, glossary, etc.) if behavior or terms change.
   - If architectural agreements or AI rules change: edit `.ai/guidelines/` and, on narrow context, `.ai/skills/*` (incl. `description` triggers), then `php artisan boost:update`.

7. **Tests**
   - Happy path.
   - Forbidden/validation path.
   - Contract tests for changed transitions/rules.

## Final self-check format

```text
[x] Domain
[x] Authorization
[x] HTTP/API
[x] Frontend
[x] Data/Migrations
[x] Docs
[x] Tests
Остаточные риски:
```

## Related skills

- `complex-task-orchestrator` (general) — decomposition & DoD; this checklist = final layer sync before closing.
- `quality/code-review` — final per-layer change review.

<!-- ru-source-sha256: 6c20bb9c52e68cc8475df52c12df41f1c7f3f9584807af8faa9b7f79d72376f1 -->
