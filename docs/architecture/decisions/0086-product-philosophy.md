# ADR 0086: Product philosophy is a normative document and a pinned root instruction

## Status

Accepted

## Context

Swiss Knife Man had no normative statement of purpose that every module, plan and review could follow.
Root common instructions are projected on demand, so a philosophy section that lived only in a hand-written
`CLAUDE.md` disappeared when projections became generated (verify-k10 K10-N1). Identity documents disagreed
about the module set, the planner CLI and where machine state lives.

## Decision

`docs/philosophy.md` is the canon for purpose and principles. A change to its meaning is an owner-visible
commit. The harness catalog gains `root.product-philosophy` (catalog 1.9.0) and pins it, with
`root.module-folders`, in `ROOT_PINNED_COMMON_IDS`, so every provider's root projection carries the same
short statement and a pointer to the canon.

## Alternatives considered

- Leave the philosophy only in `docs/philosophy.md`: rejected, agents that do not open that file never see it.
- Project every root common section: rejected, it inflates the first-turn context (ADR 0026).

## Consequences

- The first-turn budget still gates the root projections (`skiller budget --first-turn`, target 16K, stop above 23K).
- Philosophy changes only through an owner-visible commit that updates the canon first.
- Outdated root sections (module list, planner CLI, router groups, machine home) are corrected in the same catalog bump.

## Supersedes

None. Refines ADR 0026 by adding a second pinned id.
