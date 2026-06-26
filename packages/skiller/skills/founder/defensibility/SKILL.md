---
name: defensibility
bucket: founder
version: 0.1.0
description: Moat analysis for Scale stage — accumulated depth, data flywheel, workflow lock-in, domain-as-context, moat narrative one-pager
risk: draft
persona: founder
tags: [market, validation]
requires: []
produces_for: [pitch-deck, go-to-market]
outputs: ["docs/01_Business/Defensibility_Moat.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Defensibility / Moat

Use when: product found PMF and is scaling; build defensible moat via accumulated depth. Scale stage.
Litmus (Founder's Playbook): *"If a well-funded incumbent copied the product today — would users stay?"*
AI-era shift: functionality alone is no longer a moat. Moat = what compounds over time and can't be bought.

## Do NOT use when

- No PMF (idea/mvp stage) — premature; do `pmf-diagnostics` first. Moat without retention = fantasy.
- One-off competitive overview needed — that's `competitive-analysis`, not moat strategy.

## 4 moat sources (audit each)

1. **Accumulated depth** — depth built into product: integration with tools/platforms users rely on; proprietary system data and workflows. Built consistently in one direction on consistent infra → structurally hard to replicate.
2. **Data flywheel (compounding user data)** — users generate behavioral signals (accepted/rejected) → feeds roadmap. Over time you learn your base's specific patterns, preferences, edge cases. Each improvement → more usage → more feedback → more improvements. Data is time-locked, context-specific, non-reproducible by a copycat: can't buy the behavioral fingerprint of thousands of users who refined workflows inside the product.
3. **Workflow lock-in** — compounding data makes product harder to replicate; lock-in makes it harder to leave. Longer in daily ops → deeper embedded: automations on top, trained people, connected data sources, tuned prompts/workflows/outputs. Switching → from "product decision" to "full-scale operational project". **Audit integration depth:** per top-N clients — workflows built on top, integrations depended on, switching-cost estimate. Where stuck vs surface → what to build/enable to deepen.
4. **Domain expertise → AI context** — externalize founder knowledge (industry jargon, regulatory gotchas, edge cases, why "obvious" solutions fail) into structured, searchable context. Skills codify recurring workflows into reusable routines. Over months → proprietary knowledge substrate a generalist AI can't replicate. Example: "medical billing breaks on 340B claims" → dedicated test case in product.

## Output: moat narrative

One-pager for product marketing / investors:

```markdown
---
project: [ProjectName]
stage: scale
created: YYYY-MM-DD
---

# Defensibility / Moat — [ProjectName]

## Accumulated depth
What was built consistently, what's hard to replicate: …

## Data flywheel
Signals collected, for how long, the 3 highest-signal patterns → how they feed improvement: …

## Workflow lock-in (integration depth)
| Client | Workflow on top | Dependent integrations | Switching cost |
|---|---|---|---|
What to build to deepen: …

## Domain moat
Edge cases / regulatory gotchas encoded into product (absent in generic competitor): …

## Moat narrative (for GTM/investors)
Data-flywheel story: how it works, how long it's been spinning, why a well-resourced competitor starting today can't replicate it in <2 years.

## Litmus
"Incumbent copied today — would users stay?" → answer + why.
```

## Agent adds

- **Moat realism.** If "moat" = just features — say so directly: it doesn't defend.
- **Link to portfolio domain projects.** Agelto (EIS edge cases), CoreX (integration lock-in), AxiomaErpSdk (domain depth) — candidates where domain→context is especially strong.
- **Time-to-replicate estimate.** How long it'd really take a competitor — honest, not marketing.

## Related skills

- `founder/startup-lifecycle` — Scale stage; defensibility is its core work
- `founder/competitive-analysis` — supplies landscape; defensibility answers "why we hold"
- `pm/go-to-market` — consumer: moat narrative feeds investor/enterprise messaging
- `founder/pitch-deck` — consumer: moat slide
- `pm/pmf-diagnostics` — precondition: moat only meaningful after PMF

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: a9660c7b7094de46daec335b6e05969d0df701806bd693c1a1b5b105b5b70088 -->
