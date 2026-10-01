---
name: competitive-analysis
bucket: founder
version: 0.1.0
description: Use when researching market, competitors, JTBD, open niche, attack vector. Uses Perplexity search_deep.
risk: external
persona: founder
tags: [discovery, market, gtm]
requires: [idea-discovery]
produces_for: [go-to-market, new-project, pitch-deck]
outputs: ["docs/01_Business/02_Competitive_Analysis.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Competitive Analysis

Apply when: need market/competitor analysis or product positioning.

## Analysis structure

### 0. JTBD frame (before analyzing competitors)

State the job first:

> "User hires this product to [make progress X] in situation [Y], instead of [alternative Z]."

This defines the real competitive landscape. A competitor is not only a direct analog but any solution the user uses now for that job.

### 1. Competitor map (3–5 players)

Per competitor:
| Field | Content |
|:---|:---|
| Name | + URL |
| Segment | who they sell to, company size |
| Business model | Freemium / SaaS / marketplace / etc |
| Strengths | concrete, with data |
| Weaknesses | concrete vulnerabilities — UX, price, reach, tech debt |
| Threat to us | Low / Medium / High + why |

### 2. Open niche

State explicitly: "Niche X is unoccupied because [reason]. Our product can enter via [attack vector]."

### 3. Attack vector

Concrete strategy: what to do better than competitors from day one. Not "be better" — concrete: "win on price in SMB segment" / "only one with offline mode" etc.

Typical attack vectors:
- **Price:** cheaper for lower segment big players ignore
- **Vertical:** horizontal product → vertical solution for one industry
- **UX:** complex tool → simple for non-experts
- **Integration:** standalone → embedded in ecosystem ICP already uses
- **Business model:** license → SaaS, or vice versa

## Competitor neglect (antidote)

Startup-specific: founder so focused on own vision that they **systematically underrate** competitors. Antidote — build the **most convincing** case why a competitor in this space succeeds and you don't.

- **Exercise:** per tier-1 competitor — argument for its **real** threat, not the convenient one that's easy to rebut. Why its approach is genuinely better, why customers pick it, why your differentiators may be less defensible than they seem.
- This is `adversarial-check` aimed at the landscape. If positioning didn't survive it → revise positioning.

## Extended landscape (tiers)

Map beyond direct:
- **Direct** — head-on analogs (section 1 above).
- **Indirect** — another solution to same job (incl. "Excel + by hand", "do nothing").
- **Adjacent players** — neighbors who could enter your space.
- **Potential acquirers** — who'd buy (and what that makes vulnerable/protected).

## TAM / SAM / SOM

Build and **pressure-test the assumptions** under them. Market expanding, consolidating, or mature? — affects timing and differentiation. Buyer landscape: who holds budget, who influences the decision, who uses — **same** people or different?

> ⚠️ Confirmation bias × AI: ask to compute TAM → AI finds a number that makes the market fundable. Compute with `adversarial-check`, not to confirm.

## Trend analysis

Name **3 external trends** (regulatory / technological / demographic) that will materially affect the market in the next 2 years; per trend — is it a **tailwind or headwind** for the specific hypothesis. Listen to early indicators: subreddits, LinkedIn groups, the exact language users use for the problem; analogous markets where a similar problem was already solved — what worked, what didn't.

## Quality rules

- Use real data: ProductHunt, G2, App Store reviews, LinkedIn, Crunchbase
- Don't invent competitors — only real ones
- If a competitor is unknown — search via WebSearch before writing
- Name concrete weaknesses (not "clunky UI" — "no bulk actions, users complain in G2 reviews")

## Document format

Place in `docs/01_Business/02_Competitive_Analysis.md` or `docs/01_Business/03_Competitive_Analysis.md` depending on project numbering.

Mandatory positioning table at the end:
```
Our product vs market:
[axis X] vs [axis Y] — where we stand
```

## Related skills

- `founder/adversarial-check` — competitor neglect and "argue why competitor wins" is it, aimed at the landscape
- `founder/defensibility` — consumer: at Scale, tiered landscape and trends feed moat strategy
- `founder/idea-discovery` — prior step: JTBD and problem statement that set the competitive landscape (who counts as competitor)
- `pm/go-to-market` — consumer: ICP and messaging build on the found attack vector
- `founder/pitch-deck` — consumer: Competition and Why-now slides take the market map from here
- `founder/new-project` — orchestrator: calls this skill at stage 2 of the launch chain
- `pm/monetization-design` — adjacent: business-model choice relies on competitors' segment and models
