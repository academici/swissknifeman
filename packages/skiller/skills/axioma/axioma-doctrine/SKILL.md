---
name: axioma-doctrine
bucket: axioma
version: 0.1.0
description: "Axioma ecosystem development doctrine: five imperative pillars (horizontal core → verticals, vendor-vs-build discipline, AI-native/MCP-first, offline-first+RU compliance, RegHub distribution). Read when designing ANY new Axioma-ecosystem project/package — before architectural decisions."
risk: read
persona: architect
tags: [axioma, doctrine, architecture, ecosystem]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Axioma Doctrine

Five principles recurring across every Axioma-ecosystem product and package
(distilled from the `ECOSYSTEM` P0/P1 audit and `02-Knowledge` patterns). Not a
stack rundown — the stack and concrete packages/vendors live in
`axioma/axioma-stack`. This skill carries the principle and when to apply it.

## Context

Every new Axioma project/package re-derives the same architectural decisions
unless the methodology is captured as an inheritable source. Read the doctrine
ONCE at the start of design — before stack selection (`axioma-stack` /
`ecosystem-reuse-gate`) — so default decisions stay aligned with the rest of
the ecosystem instead of being reinvented.

## Inputs

- Domain and runtime of the product being designed (PHP/Laravel, Dart/Flutter,
  or another cluster).
- Presence of regulatory constraints (fiscalization, personal data, financial
  ledgers).
- Plans for third-party extensibility (marketplace/plugins).

## Five Pillars

1. **Horizontal core → verticals.** Don't build a "universal SaaS": a narrow
   vertical product on top of a shared infra core (PHP cluster `CoreX`, Dart
   cluster `AxiomaErpSdk`). The core owns infra (auth/data/billing/AI); the
   vertical owns the domain (workflow/regulation/nomenclature). Starting a new
   vertical product → follow the vertical launch checklist, don't fork the
   core. See `Vertical_SaaS_Pattern` (02-Knowledge).
2. **Vendor-vs-build — reuse by default.** Rule-of-3: a mature vendor with a
   compatible license and self-host option covers an infra function — reuse
   it, don't rewrite it. `build-new` is allowed only as a thin adapter OVER a
   vendor (domain contract/DSL) or when no suitable vendor exists. Designing a
   new functional unit → run `ecosystem-reuse-gate` against the live radar
   before writing code from scratch.
3. **AI-native / MCP-first.** AI capability is not an add-on bolted onto a
   finished product — it's part of the contract from day one: an MCP
   server/tool-registry as the standard agent-integration point, LLM access
   only through a provider abstraction (never a direct call to one vendor).
   Designing an AI feature → expose it as an MCP tool with an explicit stake
   level, not a hidden direct model call.
4. **Offline-first + RU compliance as first-class constraints.** Where the
   product runs at a physical point of presence (register, restaurant,
   warehouse) — offline-first is architecturally mandatory (not "we'll add
   sync later"); fiscalization (54-FZ/274-FZ) and data localization are not
   optional features but constraints fixed in the architecture from the first
   ADR. Designing a product with a physical presence point/payments in Russia
   → lock in the offline loop and fiscal driver before picking the rest of the
   stack.
5. **Extension distribution via RegHub.** Third parties (and internal teams)
   extend the platform through a single marketplace channel for
   submission/review/distribution of modules (`RegHub`), not private forks or
   scattered install points. Designing plugin extensibility → the publish
   channel is `RegHub`, not a bespoke store. See
   `Marketplace_Extensions_Pattern` (02-Knowledge).

## Outputs

No file is produced — the doctrine is applied as a checklist during design
conversations (read before `axioma-stack`/`ecosystem-reuse-gate` and before
`tech-stack-selection`/`new-project`).

## Quality Checklist

- [ ] Each pillar is ≤3 lines, states an explicit "when to apply", and links
      to the `02-Knowledge` pattern where one exists.
- [ ] The doctrine does NOT duplicate the tech-radar package/vendor table —
      principle only (data lives in `axioma-stack`).
- [ ] No essay/marketing tone — actionable rules only.
- [ ] Cross-links to `ecosystem-reuse-gate` and `axioma-stack` are present.

## References

- `architect/ecosystem-reuse-gate` — universal mechanism for checking against
  the ecosystem radar before `build-new` (pillar 2).
- `axioma/axioma-stack` — binding to the live `Ecosystem_Tech_Radar.md`:
  concrete packages/vendors per task (data, not principle).
- `Vertical_SaaS_Pattern`, `Marketplace_Extensions_Pattern` — `02-Knowledge`
  vault patterns detailing pillars 1 and 5.
