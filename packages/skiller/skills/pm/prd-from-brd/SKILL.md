---
name: prd-from-brd
bucket: pm
version: 0.1.0
description: Product Requirements Document — expands BRD into detailed user stories with acceptance criteria and prioritization
risk: draft
persona: pm
tags: [requirements, template]
requires: [brd]
produces_for: [architecture, product-roadmap, api-design]
outputs: ["docs/03_Dev/PRD.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: PRD from BRD

Use when: BRD written and approved; need next layer — detailed user stories with AC, UX questions, edge cases, ready to hand off to architecture/dev.

BRD ≠ PRD. BRD = WHAT + BUSINESS CONTEXT. PRD = WHAT + USER EXPERIENCE + QUALITY BOUNDARIES. Architecture = THIRD layer (HOW).

## Do NOT apply when
- BRD doesn't exist → refuse, send to `brd`.
- BRD exists but not user-approved → don't write PRD ahead.
- PRD exists, only point edits needed → edit, don't rewrite from scratch.
- OSS library without UX (BrainKit, AzGuard) → no PRD, go to `api-design`.

## What PRD adds to BRD

| Level | BRD | PRD |
|:---|:---|:---|
| User stories | skeleton ("as X, I want Y") | full with AC, edge cases, error states |
| UX | not described | flow, screen states, empty/loading/error |
| Prioritization | rough MoSCoW | RICE / MoSCoW + version (v1/v1.1/v2) |
| Feature success metric | business-level | per-feature success metric |
| Dependencies | between modules | between stories + external |
| Out-of-scope | brief | explicit "NOT doing in v1" list |

## PRD structure
Full per-section structure — [references/prd-structure.md](references/prd-structure.md).

## Intake questions BEFORE writing
Ask only what's not in BRD:
- Target platforms (web/mobile/desktop) — if not fixed in BRD
- Design system (own / Tailwind UI / Material / shadcn) — affects UX-spec
- Overall product success metric (north star metric)
- Who designs (designer or self) — sets UX-section detail level
- Launch version (v1 = MVP, or directly v1.1 with extension)

## Acceptance criteria — mandatory format
Every user story must have AC in Given/When/Then:
```
Given [precondition],
When [user action],
Then [expected result].
```
Minimum 1 happy path + 2 edge cases per story.

AC antipatterns:
- ❌ "Button works" (what does works mean?)
- ❌ "Form is pretty" (not verifiable)
- ❌ Implementation-detail in AC ("uses Redux store")
- ✅ "When user clicks Save with empty Email field, Then form shows error 'Email required' next to the field and Save button stays disabled."

## Prioritization — RICE
Per story compute:
- Reach — users/month affected (number)
- Impact — 0.25 / 0.5 / 1 / 2 / 3
- Confidence — 50% / 80% / 100%
- Effort — person-weeks

`RICE = (Reach × Impact × Confidence) / Effort`

Sort by RICE descending. Version (v1 / v1.1 / v2) = grouping by cutoff.

## Agent adds itself
- Default edge cases per story:
  - User offline?
  - Data invalid?
  - Parallel request changed state?
  - External integration unavailable?
- Empty / loading / error states per screen — even if user didn't mention.
- Accessibility minimum: keyboard navigation, focus management, ARIA labels (if web).
- BRD conflicts — name explicitly. If a PRD requirement contradicts BRD, stop and ask.

## Output file structure
`docs/03_Dev/PRD.md`:
```markdown
---
project: [ProjectName]
stage: prd
version: v1
based_on_brd: docs/03_Dev/BRD.md
requires_input_from: [docs/03_Dev/BRD.md]
produces_input_for: [Architecture, Product_Roadmap, API_Endpoints]
created: YYYY-MM-DD
---

# PRD — [ProjectName] v1

## TL;DR
[3–5 lines]

## In-scope / Out-of-scope
**In:** ...
**Out (v1):** ...

## Personas
[details on top of BRD]

## User flows
```mermaid
[flow diagrams]
```

## User stories

### US-001: [short title]
**Story:** As [role], I want [action], so that [goal].

**AC:**
- Given ..., When ..., Then ...
- Given ..., When ..., Then ...
- Given ..., When ..., Then ...

**Edge cases:**
- ...

**Success metric:** ...

**RICE:** R=___, I=___, C=___, E=___ → score=___
**Version:** v1

**Depends on:** US-XXX, external API X

---

[repeat per story]

## UX requirements
### Screen states (common checklist)
- empty / loading / success / error / partial — per screen

### Accessibility
- WCAG 2.1 AA minimum
- Keyboard nav: ...
- ARIA: ...

### Breakpoints (if web)
- mobile / tablet / desktop

## Launch metrics
- **North Star:** ...
- **Per-feature:** ...

## Open UX questions
- ...

## Out of scope for v1
- ...
```

## Hard prohibitions at PRD stage
NEVER:
- Choose stack, framework, DB — that's `architecture`
- Lay out SQL schema — that's `data-schema`
- Define REST endpoints — that's `api-design`
- Do visual design (colors, typography, components) — designer/Figma work
- Write code in AC

PRD stays a product document — hold boundary between **what's needed** and **how implemented** hard.

## Related skills
- `pm/brd` — mandatory input: PRD expands approved BRD (required BEFORE PRD).
- `pm/requirement-critic` — audit BRD before writing PRD, don't carry gaps forward.
- `pm/product-roadmap` — consumer: RICE prioritization and versions (v1/v1.1/v2) feed roadmap phases.
- `architect/architecture`, `architect/api-design` — third layer (HOW), consume PRD.
- `architect/data-schema` — entities from user stories feed data schema.
