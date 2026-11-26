---
name: pmf-diagnostics
description: "Product-market fit diagnostics — pre-launch measurement framework, Sean Ellis test (>40%), effort test, retention D1/7/30, false-positive patterns, pivot diagnosis"
---

# Skill: PMF Diagnostics

Apply when: MVP is in real users' hands and you must judge whether **PMF is reached** (MVP-stage exit criterion) — or it's a false positive. Also: set up the measurement framework **before** the first user.

Main trap: those who mis-identify early traction as PMF usually started measuring **after** launch, picking metrics for "what worked" not "what didn't". **Antidote: measurement framework before the first user.**

## Do NOT apply when

- No working MVP with real users yet (idea stage) → `customer-discovery`.
- Need a product roadmap or scope, not diagnostics → `product-roadmap`.

## 1. Measurement framework (set BEFORE launch)

Before first user, define:
- **Retention benchmarks** for the product type.
- **Activation criteria** — what counts as "activated".
- **Day 1 / Day 7 / Day 30 targets** — concrete numbers in advance.
- **What a false positive is for this specific product** (see below).

When data arrives — ask AI to build an **adversarial case against** your own traction: "what would a skeptic say about these numbers?" (`adversarial-check`).

## 2. PMF signals (real)

- **Sean Ellis test:** "how would you feel if you could no longer use the product?" → **>40% "very disappointed"** = meaningful PMF indicator.
- **Effort test:** pre-PMF retention needs constant intervention (frequent outreach, incentives, personal follow-up, founder heroics). Post-PMF the product **pulls itself** (pulling, not pushing). Shift from push to pull = one of the cleanest signals.
- **Retention plateau:** retention curve flattens to a plateau (not falling to zero) across several cohorts.
- Organic referral without incentive; users find unplanned use cases.

> No single data point confirms PMF — it's a **pattern across several iteration cycles**.

## 3. False positives (anti-patterns)

- **Signups without activation.**
- **Revenue without retention** (single-purchase, no repeat).
- **Enthusiasm without repeat usage.**
- **Launch spike ≠ sustained interest** — energy from founder's friends, investor's portfolio companies, Hacker News headline. None predicts week 6/12.

## 4. Iterate toward evidence, not completeness

MVP stage ends at genuine evidence of PMF — regardless of how "finished" the product feels. PMF declaration = judgement combining founder intuition with collected evidence, across **several** iteration cycles.

## 5. Pivot diagnosis (if 3+ iterations with no movement toward PMF)

Feed retention data + user feedback + original problem hypothesis and ask **3 questions**:
1. Is there a segment reacting **differently** from the rest? (the right audience may already be in the data, just underweighted)
2. Gap between designed value and experienced value — is it a **positioning** problem or a **product** problem? (different fix strategies)
3. What must be true for the current product to find genuine PMF — and is that realistic?

Answers determine: **adjust** (onboarding/messaging/emphasis) / **pivot** (segment or hypothesis) / **return to Idea stage**.
Mismatch between results and expectation is **not failure but a working system**: MVP stage is designed to surface this before over-investing in the wrong answer.

## Output file structure

`docs/01_Business/PMF_Diagnostics.md`:

```markdown
---
project: [ProjectName]
stage: mvp
created: YYYY-MM-DD
---

# PMF Diagnostics — [ProjectName]

## Measurement framework (pre-launch)
- Activation: … | Retention D1/D7/D30 targets: … | False positive = …

## Current data
| Metric | Target | Actual | Verdict |
|---|---|---|---|
| Sean Ellis "very disappointed" | >40% | … | … |
| Effort: push vs pull | pull | … | … |
| Retention D30 | … | … | … |

## False-positive check
- signups without activation? revenue without retention? launch spike? → …

## Adversarial (skeptic on these numbers)
- …

## Verdict
PMF reached / not reached / pivot diagnosis needed
[if 3+ iterations with no movement — 3 questions + adjust/pivot/return]
```

## Agent adds on its own

- **Realistic benchmarks by product type** (B2B SaaS vs consumer vs marketplace — different retention norms).
- **Flag vanity metrics.** If focus is on signups/downloads — redirect to retention/activation.
- **Link to roadmap.** If PMF not reached — what scope experiment is next (`product-roadmap`).

## Related skills

- `pm/product-roadmap` — **requires**: phase gates and success metrics; pmf-diagnostics refines MVP-exit
- `founder/customer-discovery` — predecessor (Idea validation); pmf-diagnostics is its MVP analog
- `founder/adversarial-check` — adversarial case against your own traction
- `founder/startup-lifecycle` — pmf-diagnostics closes the MVP→Launch gate
- `pm/unit-economics` — adjacent metrics (LTV/CAC) for Launch readiness
