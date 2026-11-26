---
name: monetization-design
description: "Pick business model (SaaS / marketplace / ads / freemium / hybrid) with trade-off matrix and rationale"
---

# Skill: Monetization Design

Use when: must **choose** a monetization model before computing unit-economics. Not `unit-economics` (that computes LTV/CAC for an already-chosen model).

Run **after `idea-discovery`** (needs JTBD + segment) and **before `unit-economics`**.

## Do NOT apply when
- Model already fixed in `docs/01_Business/01_Concept_and_Monetization.md` — skip.
- Open-source project without commerce (OSS libraries) — N/A.
- User already knows the model and wants it justified — that's `unit-economics` + `go-to-market`, not selection.

## 6 base models (consider at least these)

| Model | Fits when | Does NOT fit when |
|:---|:---|:---|
| **SaaS subscription** | Recurring pain, retention >40% MoM | One-off transaction, B2C low-frequency |
| **Marketplace (take-rate)** | Two-sided, supply exists, GMV growing | Thin supplier margin, mono-side |
| **Transactional / pay-per-use** | Sporadic demand, low commitment | High-frequency without budget cap |
| **Ads / affiliate** | Large reach, low per-user monetization | Premium audience, B2B, < 100k MAU |
| **Freemium** | Strong network effect or demo effect | Expensive serving cost, B2B without champion |
| **Open-core / license** | DevTool, infra, OSS project with a company | B2C, SaaS-only |

**Hybrid** allowed (e.g. freemium + affiliate). State explicitly which layer is primary.

## Selection algorithm (4 steps)

### Step 1. Filter by JTBD
From `00_Idea_Discovery.md` take JTBD + frequency:
- **Daily/weekly job** → SaaS / freemium / ads
- **Monthly+ job** → transactional / marketplace
- **Project-based job** → license / per-project

### Step 2. Filter by segment
- **B2C mass** → ads / freemium / transactional
- **B2C premium** → SaaS / transactional
- **B2B SMB** → SaaS / freemium
- **B2B Enterprise** → SaaS + license
- **Developer tool** → open-core / SaaS

### Step 3. Trade-off matrix (mandatory in output)
For **at least 3 models** that passed filtering, fill:

| Criterion | Model A | Model B | Model C |
|:---|:---|:---|:---|
| Time-to-revenue | | | |
| Revenue predictability | | | |
| CAC payback (estimate) | | | |
| Volume dependency (network effect needed?) | | | |
| Regulatory risks | | | |
| Infra complexity | | | |
| Payment psychology (easy to pay?) | | | |
| Analog maturity (exists on market?) | | | |

### Step 4. Recommendation + migration path
- **Starting model** for MVP — one, explicit.
- **In 6–12 months** — where to migrate (if planned).
- **Migration trigger** — concrete metric (e.g. "at MAU > 50k and retention > 35% enable freemium → paid").

## Agent adds on its own
- **Industry antipatterns.** E.g. EdTech (Edufy) — no pure-ads; fintech (Finbrain) — no B2C freemium without compliance.
- **Pricing psychology.** Anchor, decoy, 9-endings — name explicitly when applicable.
- **Hidden model costs.** Marketplace needs two-sided support; freemium — high serving cost; ads — ad SDKs with privacy issues.
- **Product roadmap impact.** Features that become mandatory for the chosen model (billing, invoicing, paywall, dispute resolution).

## Output file structure
`docs/01_Business/03_Monetization_Model.md`:

```markdown
---
project: [ProjectName]
stage: monetization-design
requires_input_from: 00_Idea_Discovery.md
produces_input_for: [04_Unit_Economics.md, 06_Go_To_Market.md, BRD.md]
---

# Monetization Model — [ProjectName]

## Context
- JTBD: ...
- Segment: ...
- Frequency job: ...

## Models reviewed
[list after elimination - minimum 3]

## Trade-off matrix
[table by criteria]

## Recommendation
**Starting model:** [X]
**Rationale:** [3–5 items]

## Migration route
- T0: [model]
- T+6–12 months: [model] on trigger [metric]

## Anti-patterns for this domain (agent)
- ...

## Impact on roadmap / BRD
- Required features: ...
- Compliance-requirements: ...

## Next step
→ `.ai/skills/pm/unit-economics.md` (calculation LTV/CAC for the selected model)
```

## Hard prohibitions at this stage
MUST NOT:
- Compute concrete prices and LTV/CAC — that's `unit-economics`.
- Detail acquisition channels — that's `go-to-market`.
- Decide billing framework — that's `architecture`.

Only **model selection** and **trade-off rationale**.

## Related skills
- `founder/idea-discovery` — input: JTBD, problem, segment (required BEFORE model choice).
- `pm/unit-economics` — next step: LTV/CAC/payback for chosen model.
- `pm/go-to-market` — consumer: model drives channels and messaging.
- `pm/brd` — consumer: chosen model adds mandatory features (billing, paywall, invoicing).
- `founder/competitive-analysis` — analog models on market (maturity, take-rate) feed trade-off matrix.
