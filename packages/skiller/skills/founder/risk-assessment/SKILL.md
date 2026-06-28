---
name: risk-assessment
bucket: founder
version: 0.1.0
description: 6 risk categories (incl. AI/Agentic), Risk Matrix, RAID log, pre-mortem for critical risks
risk: read
persona: founder
tags: [validation, compliance, security, agentic]
requires: []
produces_for: [new-project, pitch-deck]
outputs: [chat, "docs/01_Business/Risk_Register.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Risk Assessment

Use when: risk assessment, pre-mortem, RAID log, blocker analysis, product vulnerabilities.

## Principle

- Name risks explicitly, with specifics. No "maybe there will be problems".
- Format each risk: **"If [condition] → then [consequence] → because [cause]"**

## Step 1. Automatic analysis (no questions)

Analyze 6 risk categories yourself:

| Category | Check |
|:---|:---|
| **Technical** | 3rd-party deps, scalability, single point of failure, security |
| **Market** | Market size, timing, deep-pocketed competitors, user behavior shift |
| **Regulatory** | GDPR, licensing, App Store / Play Market policies, country legislation |
| **Financial** | Runway, burn rate, single monetization channel dependency, CAC > LTV |
| **Team/Operations** | Key person dependency, knowledge in one person, no backup processes |
| **AI/Agentic** | Hallucination on the critical path, agentic drift (out-of-bounds), prompt injection, cost creep (inference cost growth at scale), eval/guardrail gaps, single-LLM-provider dependency |

## Step 2. Risk Matrix

Rate each risk:

| Risk | Probability (1-5) | Impact (1-5) | Score | Status |
|:---|:---|:---|:---|:---|
| [Name] | 3 | 5 | 15 | 🔴 Critical |
| [Name] | 2 | 3 | 6 | 🟡 Medium |
| [Name] | 1 | 2 | 2 | 🟢 Low |

**Score = Probability × Impact**
- 15-25 → 🔴 Critical (mitigation plan mandatory)
- 6-14 → 🟡 Medium (monitor)
- 1-5 → 🟢 Low (accept)

## Step 3. RAID log

```
## Risks
- R1: [Description] | Score: X | Mitigation: [action]

## Assumptions
- A1: [Taken as fact without verification]

## Issues (already on fire)
- I1: [Already a problem now]

## Dependencies
- D1: [What success depends on, outside team control]
```

## Step 4. Pre-mortem (mandatory for critical risks)

For each 🔴 risk:

> "Imagine 12 months from now the product failed precisely due to [risk X].
> What exactly happened? Which decisions led to it?"

Surfaces hidden assumptions never spoken aloud.

## AI era: premature scaling (distinct market risk)

**Scaling execution far ahead of what the business requires** — committing to a product path before validating it's worth committing to. Agentic coding makes it easy to scale execution past problem-solution fit without consciously choosing to. AI builds/tests/refactors around a flawed premise as eagerly as a great one.

- Add explicit Risk Matrix risk: "building/scaling before validation".
- Mitigation — keep `sense-making` (validation) **ahead** of building; gate stages (`startup-lifecycle`).

> For market risks and any critical assumptions (RAID Assumptions) — run `adversarial-check`: AI supports what you believe; need a reverse-directed pressure-test.

## Document format

Place in:
- `docs/01_Business/Risk_Register.md` — startups
- `docs/03_Dev/Risk_Register.md` — technical risks of a specific project

File structure:

```markdown
# Risk Register: ProjectName

## Risk Matrix
[table]

## RAID log
[R/A/I/D sections]

## Critical risk mitigation plan
### R1: [Name]
- Trigger: [when this risk materializes]
- Action: [what to do]
- Owner: [who]
- Deadline: [when to resolve or accept]
```

## Agent adds itself

- Risks user didn't mention (typical for industry/product)
- Hidden dependencies between risks ("if R1 → automatically R3")
- Clarifying question ONLY if risk is blocking and info missing: "Is a legal entity in RF planned? — regulatory risk assessment depends on it"

## Hard prohibitions

DON'T:
- Vague wording ("there may be problems")
- Invented risks without justification
- Ignore categories — all 6 must be checked (for AI products the AI/Agentic category is mandatory)

## Related skills

- `founder/adversarial-check` — fast pointed pressure-test of assumptions; risk-assessment — broader RAID/pre-mortem
- `founder/startup-lifecycle` — premature scaling = Idea/MVP failure mode; gate keeps validation ahead of building
- `founder/new-project` — orchestrator: runs risk-assessment at stage 3 of launch chain
- `founder/pitch-deck` — consumer: risk-acknowledgement slide addresses key risk from this register
- `architect/legal-compliance` — deepens regulatory category (GDPR, AI Act, DSA, licensing)
- `architect/security-design` — deepens technical category (auth, OWASP, STRIDE threat modeling)
- `quality/tech-debt-audit` — adjacent for technical risks of existing code (impact × effort)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: dc1c0898b6a2be6b12d99937ae58c645e4578c2c520e1b425a78ef5172814e43 -->
