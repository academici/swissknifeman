---
name: go-to-market
bucket: pm
version: 0.1.0
description: GTM strategy, ICP, messaging framework, acquisition channels, launch plan
risk: draft
persona: pm
tags: [gtm, market, monetization]
requires: [competitive-analysis, monetization-design]
produces_for: [product-roadmap, pitch-deck]
outputs: ["docs/01_Business/06_Go_To_Market.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Go-To-Market (GTM)

Apply when: GTM strategy, market entry, acquisition channels, launch plan, ICP, messaging.

GTM = who, through what, with what message, in what order. No sharp ICP (Ideal Customer Profile) = shotgun.

## Step 1. ICP

Not "all users" — the most concrete first segment.

```markdown
## ICP v1

**Type:** [B2B / B2C / B2B2C]
**Segment:** [Small business / Freelancers / Students / ...]
**Company size:** [1-10 / 10-50 / 50-200 employees] (for B2B)
**Geo:** [Country / Region]
**Problem:** [Specific pain, one line]
**Buying trigger:** [What makes them search for a solution right now]
**Alternative:** [What they use now instead of our product]
**Reason to switch:** [Why pick us vs stay on current]
```

## Step 2. Messaging Framework

| Element | Content |
|:---|:---|
| **Value proposition** | [What product does + for whom + result] one line |
| **Tagline** | < 10 words, memorable |
| **Elevator pitch** | 2-3 sentences for investor |
| **Pain** | Top-3 pains solved |
| **Gain** | Top-3 concrete results |
| **Proof points** | Concrete numbers/cases (or [placeholder]) |

## Step 3. Acquisition Channels

Score by matrix:

| Channel | Cost | Speed | Scale | Priority |
|:---|:---|:---|:---|:---|
| Organic SEO | Low | Slow | High | 🟡 Medium |
| Paid ads (Meta/Google) | High | Fast | High | 🔴 Only after PMF |
| Content / Community | Low | Slow | Medium | 🟢 Start |
| Partnerships | Medium | Medium | Medium | 🟢 If network exists |
| Product-led growth | Low | Medium | High | 🟢 If freemium |
| Direct sales / outreach | Medium | Fast | Low | 🟢 At start for B2B |

## Step 4. Launch Plan

```
Phase 0: Pre-launch (before release)
- Waitlist / landing page
- Community seeding (Reddit, Telegram, ProductHunt)
- 10-20 beta users from ICP

Phase 1: Soft launch (week 1-4)
- Closed beta access
- Collect feedback
- Iterate product

Phase 2: Public launch
- ProductHunt / Hacker News / AppSumo (if fit)
- PR / Media outreach
- First paying

Phase 3: Growth
- Enable paid channels only after: CAC < LTV and Retention ≥ 40% (Day 30)
```

## Step 5. GTM as a function (Launch/Scale)

Launch plan above = the launch. At Launch/Scale: build a **repeatable growth engine**, not a one-off launch. Organic growth (founder-led selling, Product Hunt, personal connections) has a ceiling.

**Repeatable & channel-driven (Launch-exit):** growth predictable via concrete channels with clear economics — **CAC, LTV, payback** (numbers you know and can defend), not "got lucky with a post". Cross-check with `unit-economics`.

**Audience-segmented voice (Scale):** reach new users plus **investors** and **enterprise buyers**. Each audience has its own vocabulary and criteria:

| Audience | What they want to hear |
|---|---|
| Users | pain → result, time-to-value |
| Enterprise buyers | reliability, security/compliance, SLA, support, integration depth |
| Investors/analysts | moat narrative, growth mechanics, TAM, unit economics |

Build **brand voice & story** + product-marketing infra (interactive demo, integration docs, API references, sandbox) so GTM motion runs async. Moat narrative for investors/enterprise comes from `defensibility`.

## Document format

Place in `docs/01_Business/06_Go_To_Market.md`

## Agent adds itself

- Channel specifics for the vertical (SaaS vs Consumer vs Marketplace)
- Red flags: "No retention → ads only accelerate budget burn"
- Synergies with other vault projects if audience overlaps
- Concrete launch venues (not abstract "social media")

## Hard prohibitions

DO NOT:
- ICP "everyone who needs [product]" — too broad
- Launch paid channels before retention proven
- GTM without a concrete success metric (what "successful launch" means)

## Related skills

- `founder/competitive-analysis` — input for GTM: market, competitors, JTBD, open niche (required BEFORE GTM).
- `pm/monetization-design` — chosen monetization model sets channels and messaging (required BEFORE GTM).
- `pm/unit-economics` — source of paid-channel launch gates (CAC < LTV, payback); cross-check with metrics here.
- `pm/product-roadmap` — consumer: ICP and launch phases feed product phasing.
- `founder/startup-lifecycle` — frame: launch-plan = entry to Launch, repeatable channel-driven growth = Launch-exit.
- `founder/defensibility` — supplier of moat narrative for investor/enterprise voice at Scale.
- `founder/pitch-deck` — consumer: deck GTM section comes from here.

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 23940414311fab6ab75f8d64dc0d488e413a80070f58682e4796b9f485d6438b -->
