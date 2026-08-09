---
name: new-project
bucket: founder
version: 0.1.0
description: "Use when launching a new startup project: concept, competitors, risks, full folder structure."
risk: write
persona: founder
tags: [discovery, requirements, market, gtm]
requires: [idea-discovery, competitive-analysis, risk-assessment, ecosystem-reuse-gate]
produces_for: []
outputs: [ProjectName.md, "docs/01_Business/01_Concept_and_Monetization.md", "docs/01_Business/02_Competitive_Analysis.md", "docs/01_Business/Risk_Register.md", "Открытые вопросы.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: New Project / Concept Analysis

Use when: user gives a new idea, concept, startup, or product — anything needing assessment and doc launch.

## Step 0. Idea-gate (before any docs)

On raw idea or first report, run before scaffolding:
1. `idea-discovery` — sharpen hypothesis to testable form.
2. `adversarial-check` — pressure-test before commit (AI confirms anything; need counter-vector).
3. `customer-discovery` — if no evidence from live talks yet, plan it (serious project → gather; quick validation → at least a framework).
4. **Problem-solution fit (3 "yes"):** problem real+specific+frequent? solution hits a real problem? signal enough for MVP? (`startup-lifecycle` Idea-exit).

Document only if gate passes. Fail → do not scaffold, return to discovery/pivot.

## Step 1. Deep analysis (mandatory, do not skip)

Agent does this **autonomously** before any documenting:
1. **JTBD analysis** — via `competitive-analysis.md` (starts from JTBD frame; result → basis of BRD and GTM).
2. **Competitive analysis** — 3–5 real players:
   - who they are, which segment they hold
   - concrete weak spots (UX, price, coverage, tech)
   - unoccupied niche the product can enter
   - need real search → use Perplexity MCP (`.ai/guidelines/perplexity-mcp.md`)
3. **Risks** — must read `.ai/skills/founder/risk-assessment.md`:
   - run through all 5 categories (technical, market, regulatory, financial, team)
   - Risk Matrix scoring each
   - state explicitly: "If [condition] → then [consequence]"
4. **Concept improvements** — propose what wasn't in the brief:
   - adjacent high-ROI features
   - alternative business models
   - synergies with other vault projects (see map in CLAUDE.md)

## Step 2. Blocking questions only

Ask only if you **cannot proceed** without the answer.
- ❌ "Need a mobile client?"
- ✅ "Sell direct or via partners? Drives white-label in v1."

Rule: if agent can answer itself with >70% confidence — answer, document the decision.

## Step 2.5. Ecosystem reuse-gate (before scaffold)

Before creating the folder structure, run `ecosystem-reuse-gate` against the ecosystem radar — do not reinvent what already exists in other projects/packages.

## Step 3. Documentation (staged)

Creating control-tower `ProjectName.md`: set frontmatter **`stage: idea`** (validation stage; new project always starts at idea). Stage advances via stage-gate review (`startup-lifecycle`), never manually.

Stages strictly sequential. Each requires explicit "Approved" before the next.

| Stage | File | Skill | Forbidden |
|:---|:---|:---|:---|
| 1 | `docs/01_Business/01_Concept_and_Monetization.md` | — | Technical details |
| 2 | `docs/01_Business/02_Competitive_Analysis.md` | `competitive-analysis.md` | — |
| 3 | `docs/01_Business/Risk_Register.md` | `risk-assessment.md` | — |
| 4 | `docs/01_Business/04_Unit_Economics.md` | `unit-economics.md` | SQL, classes |
| 5 | `Открытые вопросы.md` — blocking only | — | Answer for the user |
| 6 | `docs/02_Workflow/` — FSM processes | `business-process.md` | Architecture decisions |
| 7 | `docs/01_Business/06_Go_To_Market.md` | `go-to-market.md` | — |
| 8 | `docs/01_Business/07_Product_Roadmap.md` | `product-roadmap.md` | — |
| 9 | `docs/03_Dev/BRD.md` | `brd.md` | Classes, DB schemas, code |
| 10 | `docs/03_Dev/Architecture*.md` | `architecture.md` | — |
| 11 | `docs/03_Dev/Database_Schema.md` | `data-schema.md` | SQL |
| 12 | `docs/03_Dev/API_Endpoints.md` | `api-design.md` | — |

## Step 4. Cross-project synergies

On new project, check vault map (CLAUDE.md) for:
- shared modules to extract into `02 - Knowledge/`
- audience overlap with another project → bundle/partnership
- shared tech solutions → link via `[[file]]`

## Related skills

Orchestrator: does not duplicate domain skills, calls them by stage. Chain:
- `founder/startup-lifecycle` — stage frame: new-project sets `stage: idea`, runs idea-gate
- `founder/idea-discovery` — step 0: raw-idea discovery (JTBD, hypothesis, kill-criteria) before concept
- `founder/adversarial-check` — idea-gate: pressure-test hypothesis before scaffold
- `founder/customer-discovery` — idea-gate: problem-solution fit evidence via live interviews
- `architect/ecosystem-reuse-gate` — step 2.5: check the ecosystem radar before scaffold
- `founder/competitive-analysis` — step 2: market, competitors, attack vector
- `founder/risk-assessment` — step 3: 5 risk categories, Risk Register
- `pm/unit-economics` — step 4: LTV/CAC/payback
- `pm/business-process` — step 6: FSM processes
- `pm/go-to-market` — step 7: GTM strategy
- `pm/product-roadmap` — step 8: MVP → v1 → v2
- `pm/brd` — step 9: Business Requirements Document
- `architect/architecture`, `architect/data-schema`, `architect/api-design` — steps 10–12: technical design
- `pm/monetization-design` — adjacent: business-model choice before unit-economics
- `roles/solo-founder`, `roles/startup-cto` — personas that activate this chain
