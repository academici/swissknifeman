---
name: unit-economics
bucket: pm
version: 0.1.0
description: "Unit economics: LTV, CAC, payback, churn, break-even, 3 scenarios"
risk: draft
persona: pm
tags: [monetization]
requires: [monetization-design]
produces_for: [pitch-deck, go-to-market]
outputs: ["docs/01_Business/04_Unit_Economics.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Unit Economics

Apply when: task on unit economics, financial model, LTV/CAC, break-even, monetization.

Principle: unit economics = economics of one unit (1 user, 1 order, 1 subscription). If negative, scaling only accelerates losing money.

## Required metrics by monetization model

### SaaS / Subscription
| Metric | Formula | Target |
|:---|:---|:---|
| MRR | Paying × ARPU | Growth MoM |
| LTV | ARPU × (1 / Churn%) | LTV > 3×CAC |
| CAC | Acquisition spend / New customers | As low as possible |
| LTV/CAC | LTV ÷ CAC | Target: ≥ 3:1 |
| Payback period | CAC ÷ (ARPU × Gross margin%) | Target: < 12 mo |
| Churn | Lost / Base × 100 | < 5% monthly for SMB |

### Marketplace
| Metric | Formula |
|:---|:---|
| GMV | Transaction volume |
| Take rate | Commission / GMV |
| Net revenue | GMV × Take rate |
| CAC (supply / demand) | Separately for each side |

### Freemium / Consumer
| Metric | Formula |
|:---|:---|
| Conversion rate | Paying / All users |
| ARPU | Revenue / MAU |
| Revenue per cohort | What each cohort brings over 12 mo |

## Steps

1. Current state — fill table with what's known. Unknowns = hypotheses marked [estimate].
2. Break-even analysis:
```
Break-even = Fixed costs / (Unit price - Variable cost per unit)
```
   Show at what user/transaction count project hits 0. Add timeline — how many months at current growth rate.
3. Scenarios:

| Scenario | Churn | CAC | Conversion | Break-even |
|:---|:---|:---|:---|:---|
| Pessimistic | +50% | +50% | -30% | [mo] |
| Base | [current] | [current] | [current] | [mo] |
| Optimistic | -30% | -20% | +50% | [mo] |

## Document format

Place in `docs/01_Business/04_Unit_Economics.md`. Structure:
```markdown
# Unit Economics: ProjectName

## Business model: [type]
## Key metrics (current / forecast)
[table]
## Break-even analysis
## Scenario analysis
## Conclusions: what to do to improve unit economics
```

## Red flags (name explicitly)

- LTV < CAC → unprofitable growth
- Payback period > 18 months → cash flow problems
- Churn > 10% monthly → "leaky bucket"
- Gross margin < 40% → no room for sales and marketing
- Single acquisition channel → dependency risk

## Agent adds itself

- Comparison with industry benchmarks (SaaS: LTV/CAC ≥ 3, Churn < 5%)
- Proposal: which metric to improve first and how
- Link to risk: if unit economics negative → link to `[[Risk Register]]`

## Related skills

- `pm/monetization-design` — input: chosen business model sets the metric set (required BEFORE calculation).
- `pm/go-to-market` — consumer: paid-channel launch gates (CAC < LTV, payback) taken from here.
- `founder/pitch-deck` — consumer: financial slide of deck relies on these numbers.
- `founder/risk-assessment` — negative unit economics → entry in Risk Register.

<!-- ru-source-sha256: 5f24a65cf9afec41fa348376b1ea6e13c55e3da2735cb6ecc97b10d370a95646 -->
