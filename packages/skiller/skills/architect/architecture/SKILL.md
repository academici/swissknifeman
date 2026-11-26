---
name: architecture
bucket: architect
version: 0.2.0
description: "Choose a consequential architecture or record a disputed design decision; scale artifacts to risk."
when_to_use: "Use when a consequential architecture decision needs design."
risk: draft
persona: architect
tags: [architecture, adr, c4, scalability, deployment]
requires: []
produces_for: [data-schema, api-design, security-design, agent-design, observability-design, legal-compliance]
outputs: ["docs/03_Dev/Architecture_[Name].md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Architecture Design

Use for a consequential system/component design decision. Start from the authorized outcome,
existing architecture, load and deployment constraints, and relevant recorded decisions. A BRD
is useful input when present; its absence does not block a bounded design or an authorized
local repair. Do not manufacture a design phase because several files are involved.

## Decide with enough evidence

1. Identify the boundary and the concrete problem: behavior, ownership, compatibility, load,
   reliability, or operating cost. State unknown constraints that affect the decision.
2. Inspect existing capabilities before adding a dependency or new layer. Compare viable
   alternatives when they meaningfully differ; each rationale explains how it serves the
   actual goal and constraints, rather than popularity or familiarity.
3. Choose the smallest sufficient design, name tradeoffs and accepted risks, and define
   observable acceptance. Verify changing external premises with current primary evidence.
4. Record the decision where the project owns architecture docs. A short explanation suffices
   for a local reversible choice; an ADR suits a consequential, disputed, or durable boundary.
5. When implementation is authorized, carry it through checks and delivery. A separately
   requested design ends with the reviewable design and concrete next action.

## Useful artifacts

For a full architecture document include context, alternatives/rationale, chosen components,
integrations, deployment, reliability/security constraints, and acceptance. Use a diagram when
it makes relationships clearer. Do not require a Mermaid diagram or a load/SLO estimate that
is irrelevant or unsupported; record unknowns honestly and resolve them when they become
load-bearing.

Use [ADR template](snippets/adr-template.md) for a significant decision,
[C4 context](snippets/c4-context.md) for system boundaries, and
[C4 containers](snippets/c4-container.md) for runtime components. Adapt paths to the existing
project layout; a particular vault or BRD file is not a universal prerequisite.

## Risk-specific navigation

Assess affected trust/data boundaries while choosing architecture. For changes to auth,
secrets, personal/financial data, or external exposure, use `architect/security-design` for
those boundaries; no automatic second full security document follows every local edit.
`architect/tech-stack-selection` applies to an actual stack decision, `architect/api-design`
to a public contract, and `architect/data-schema` to persistence modeling. Agent loop,
observability, and legal-compliance skills apply only when those decisions are in scope.
