---
name: ecosystem-map
bucket: axioma
version: 0.1.0
description: "Where docs, plans, findings and vault links live in a project and how repo↔Brain sync. A locator, not canon — HOW planning works: plan-protocol."
risk: read
persona: architect
tags: [axioma, ecosystem, plans, docs, navigation]
level: ""
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Ecosystem Map

## Context

Pointer map of how a project wires: where `docs`/`docs-public` live and sync to the Brain vault,
where the plan lives (repo home) + its vault link, where `findings`/`artifacts` go. Portable everywhere.

A POINTER, not an encyclopedia — it does NOT copy the plan-system canon (an embedded copy drifts;
precedent `axioma-stack`). HOW plans/workflow are made — `plan-protocol`/`workflow-craft`.

## When to activate

- In any ecosystem project with `plans/` or `docs/`, to FIND where the plan, docs, or
  findings are, or how they sync to the vault.
- Cold start / onboarding in a repo (vault not open) — locate the plan and its vault link.
- Overlap check: this is WHERE things live; HOW planning/workflow works — `plan-protocol`/
  `workflow-craft`. Tempted to describe "how" — stop.

## Map (how it wires)

- **docs / docs-public** — docs in `docs/`; public subset in `docs-public/`; synced to
  the Brain vault by `brain sync` (frontmatter `repo:`).
- **Plan** — home defaults to the repo: `plans/<ID>/` (next to `docs/`); a program/
  cross-project plan stays in the vault `plans/`. In the vault, a control-tower link
  points to the repo plan.
- **findings / artifacts / root / workflows** — inside `plans/<ID>/`: `findings/` = RAG
  extracts & recon; `artifacts/` = phase working files (→ archive); `root/` = long-lived
  material (→ project `docs/`); `workflows/` = plan's workflow-script copies.
- **repo↔vault** — once exec starts, repo = SSOT; sync repo→Brain (mirroring); terminal
  plan → archive → `root/` migrates into docs.

## Not here (see the canon)

- Plan/phase/task schemas, 6 statuses, DoR gate, `/planner:plan-*`, two-homes lifecycle →
  **`plan-protocol`**.
- Workflow-script authoring (stages, slots, names) → **`workflow-craft`**.

## Quality checklist

- [ ] Used as a LOCATOR, not to derive planning rules.
- [ ] `plan-protocol`/`workflow-craft` canon NOT copied here — only pointers.
- [ ] Plan home (repo by default) and repo↔Brain sync direction stated.

## Links

- `general/plan-protocol` — plan-system canon (HOW).
- `general/workflow-craft` — workflow authoring discipline.
- `axioma/axioma-stack` — sibling axioma pointer.
