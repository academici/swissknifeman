---
name: project-map
bucket: general
version: 0.1.0
description: "Project structure map methodology: zone directories by responsibility for safe change routing (where to edit, which layer logic belongs in). Activate when you need to quickly find where to put a change, or build/update a structure map for a project; language-agnostic."
risk: read
persona: oss-dev
tags: [conventions, navigation, architecture, structure, routing]
requires: []
produces_for: [cross-layer-change-checklist]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Project structure map (methodology)

Methodology to build a map for **any** stack; the concrete project map lives in its docs/`.ai`, not in the registry.

## When to activate

- Quickly orient where to edit in an unfamiliar or large project.
- Build/update a structure map (onboarding, layout refactor).
- Before a cross-cutting change — check which layers are touched (→ `cross-layer-change-checklist`).

## Map-building algorithm

1. **Find entry points** — where the app starts (routes/CLI/handlers/main) and where requests arrive.
2. **Identify layers by responsibility** (typical set, adapt to stack):
   - transport/entry (HTTP/CLI/UI) — only intake, validation, delegation;
   - business operations/use-case — state change, transactional boundary;
   - domain logic/services — computation, orchestration, no transport;
   - data access (repositories/ORM) — read/write;
   - access/policies — authorization rules;
   - models/types/enum — data and invariants;
   - config, tests, docs.
3. **Map layer → project directory** (one responsibility — one place).
4. **Fix placement rule**: for each change type — which layer it lands in (new state-changing operation → use-case layer, not transport).
5. **Save the map** in project docs (`docs/`/`.ai/`), next to code — not in the shared registry.

## Change-routing principle

- State change/business operation → use-case layer (Action/Command/Service operation).
- Pure computation, no side effects → domain service/function.
- Request intake only → transport layer (controller/handler), no mutation orchestration.
- Access rule → policy/authorization layer, in sync with tests.

## Checklist

- [ ] Entry points found and responsibility layers listed.
- [ ] Each layer mapped to a concrete directory (one zone — one place).
- [ ] "Change type → layer" rule fixed.
- [ ] Map lives in project docs, no concrete project names in the shared skill.

## Related skills

- `cross-layer-change-checklist` (general) — when a change touches several layers at once.
- `php/laravel-structure`, `python/ml-project-structure` — stack-specific layout canons.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: fac8d8a2b0c47b5a489acc2d455b2ded6052d90a9521c13429a58bfb1a3f8aff -->
