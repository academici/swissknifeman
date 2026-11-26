---
name: pitch-deck
description: "Use when building a 10-slide investor deck per YC/Sequoia canon from existing project artifacts."
---

# Skill: Pitch Deck

Apply when: user asks for "deck"/"pitch"/"investor presentation" or is going for a round (pre-seed / seed / A).

Output = **markdown describing each slide**, NOT PPTX. Export to .pptx/.pdf is separate via `document-generator` MCP (only if asked).

## Do NOT apply when
- No existing `competitive-analysis` and `unit-economics` — refuse, send user to run those skills first.
- Internal team deck requested — plain markdown, no 10-slide canon.
- Pre-discovery stage (deck before JTBD).

## 10-slide canon (Sequoia / YC hybrid)

| # | Slide | Show | Vault source |
|:---|:---|:---|:---|
| 1 | **Title** | Name, one-liner, contacts, date | `ProjectName.md` |
| 2 | **Problem** | Who hurts, how much, cost of not solving | `00_Idea_Discovery.md` |
| 3 | **Solution** | One MVP screen + how it closes the pain | `01_Concept_and_Monetization.md` + `BRD.md` |
| 4 | **Why now** | Trend / tech / regulation, window of opportunity | `02_Competitive_Analysis.md` + research |
| 5 | **Market size** | TAM / SAM / SOM with sources | research (Perplexity `search_deep`) |
| 6 | **Competition** | Market map + our attack vector | `02_Competitive_Analysis.md` |
| 7 | **Product** | 2–3 key MVP features + screenshot/wireframe | `BRD.md` + `07_Product_Roadmap.md` |
| 8 | **Business model** | How we earn + unit economics LTV/CAC | `03_Monetization_Model.md` + `04_Unit_Economics.md` |
| 9 | **Traction / GTM** | What exists (pilots, waitlist, MAU) + launch plan | `06_Go_To_Market.md` + current metrics |
| 10 | **Team + Ask** | Team, how much, what for, runway | user |

**Optional 11–12:**
- Roadmap (phases from `07_Product_Roadmap.md`)
- Appendix: financial model, tech deep-dive

## Slide rules
1. One thesis per slide.
2. Eye reads in 5s. Title = main thesis, not "Problem" but "3 of 4 SMBs lose 8 hours/week on X".
3. Numbers > epithets. "Fast" = nothing; "3.2× faster than peers" = thesis.
4. Sources: every number on slides 4, 5, 6, 8, 9 — with link / appendix.
5. Visual hierarchy: one main object, rest is support.

## Survey questions BEFORE writing
- Round stage (pre-seed / seed / A) — sets traction-slide depth.
- Ask amount + runway (months) + what for (R&D / GTM / hire).
- Team: names, roles, key past experience.
- Traction available: MAU/MRR/LOI/pilots/waitlist — concrete numbers.
- Deck audience: VC / angel / accelerator (slight tweak per each).

## Agent adds itself
- **Hook on Problem slide.** If pain is weak, rewrite as "X people lose Y because Z".
- **Why-now candidates.** From competitive-analysis + research find 1–2 fresh trends (AI wave, regulatory change, competitor plateau).
- **Competitive vector.** Not just matrix — **one sentence** on our angle (cheaper / faster / niche / new tech / new model).
- **Risk-acknowledgement slide (optional).** If project has obvious risk (DMCA, regulation) — address it yourself in appendix.

## Output file structure

`docs/01_Business/08_Pitch_Deck.md`:

```markdown
---
project: [ProjectName]
stage: pitch-deck
round: [pre-seed | seed | series-a]
ask_usd: [amount]
runway_months: [number]
created: YYYY-MM-DD
---

# Pitch Deck — [ProjectName]

## Slide 1 — Title
- Title: [ProjectName]
- One-liner: [one line]
- Contact: ...

## Slide 2 — Problem
**Abstract:** [main hook]
- To whom it hurts: ...
- The cost of not deciding: ...
- Source: [[00_Idea_Discovery]]

## Slide 3 — Solution
**Abstract:** ...
- What we do: ...
- Screenshot / wireframe: [link]
- Why the pain closes: ...

## Slide 4 — Why now
**Abstract:** ...
- Trend / technology: ...
- Window of opportunity: ...

## Slide 5 — Market size
- TAM: $X (source)
- SAM: $Y (source)
- SOM: $Z (our taking)

## Slide 6 — Competition
- Map: [table from 02_Competitive_Analysis]
- Our attack vector: [one sentence]

## Slide 7 — Product
- Feature 1: ...
- Feature 2: ...
- Feature 3: ...

## Slide 8 — Business model
- Model: [from 03_Monetization_Model]
- LTV: $X, CAC: $Y, payback: Z months (from 04_Unit_Economics)

## Slide 9 — Traction / GTM
- Current: [numbers]
- Plan GTM: [from 06_Go_To_Market]

## Slide 10 — Team + Ask
- Command: [names, roles]
- Ask: $[amount] on [runway] months
- To which: [breakdown]

## (Appendix) — Risk acknowledgement
[if applicable]
```

## Hard prohibitions

FORBIDDEN:
- Numbers without source.
- "Revolutionary", "unique", "no analogs" — without proof.
- "Vision" slide without traction (defer to series A+).
- Financial projections beyond 24 months at pre-seed.
- Hiding a key risk — VCs will find it anyway.

## Export

If user asks .pptx or .pdf:
- Use `document-generator-mcp` (see `docs/ai/mcp-servers.md`).
- Markdown stays source of truth — `.pptx` rebuilt from it each time, not edited separately.

## Related skills

Deck consumes ready artifacts, recomputes nothing. Slide sources:
- `founder/competitive-analysis` — Competition + Why-now slides (market map, attack vector).
- `pm/unit-economics` — Business model slide (LTV/CAC/payback).
- `pm/go-to-market` — Traction / GTM slide (launch plan).
- `founder/idea-discovery` — Problem slide (pain, cost of not solving).
- `pm/monetization-design` — Business model slide (chosen business model).
- `pm/product-roadmap` — Product slide + optional Roadmap.
- `founder/risk-assessment` — optional Risk-acknowledgement slide in appendix.
