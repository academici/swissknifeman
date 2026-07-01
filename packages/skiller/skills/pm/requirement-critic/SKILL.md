---
name: requirement-critic
bucket: pm
version: 0.1.0
description: Audit of a written spec/BRD: completeness, conflicts, assumptions, gap analysis, MoSCoW + optimism-bias detector and [UNVERIFIED] tags. Chat-only, no file
risk: read
persona: pm
tags: [requirements, validation]
requires: [brd]
produces_for: []
outputs: [chat]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Requirement Critic

Use when: audit a BRD / requirement set before the architecture phase.

Role: skeptical technical reviewer, not author. Find problems expensive to fix after development starts.

## Step 1 — Completeness
Check each functional requirement:
- **Who**: actor specified? user role defined?
- **What**: action unambiguous? no double meaning?
- **When**: trigger present? what initiates the action?
- **Acceptance criteria**: measurable acceptance criteria present?
- **Edge cases**: data invalid / empty / concurrent request?
- **Negative scenario**: what does the system do on error?

## Step 2 — MoSCoW
Assign priority to each requirement:
- **Must**: product doesn't work without it / MVP impossible
- **Should**: important, but workaround exists at start
- **Could**: desirable if time permits
- **Won't**: explicitly out of scope (record it so it doesn't resurface later)

Rule: >60% requirements marked Must = red flag (no prioritization).

## Step 3 — Conflicts
Find contradictions inside the doc:
- **Logical**: req A assumes X, req B assumes not-X
- **Resource**: two reqs cannot be done simultaneously
- **Role**: one req grants a right, another forbids it
- **Temporal**: operation order contradicts across scenarios

Format: `⚠️ Конфликт: [Требование A] vs [Требование B] — [суть проблемы]`

## Step 4 — Implicit assumptions
Surface what's taken for granted but not recorded:
- Expected load (users / RPS?)
- Languages and locales (RU only? multilingual?)
- Platforms (web only? mobile? PWA?)
- Offline mode (needed?)
- Response time (unmentioned → dev decides → expectation conflict)
- Data access rights (who sees other users' data?)

Format: `❓ Допущение: [что не сказано, но подразумевается]`

## Step 5 — Gap analysis
Walk typical modules for the product type, check nothing is missed:

### SaaS / web app
- [ ] Authentication and authorization — described?
- [ ] Session management — specified?
- [ ] Email notifications — mentioned?
- [ ] List pagination — required?
- [ ] Search and filtering — covered?
- [ ] Data deletion — what happens to dependent records?
- [ ] Soft delete vs hard delete — defined?
- [ ] Data export — needed?
- [ ] Audit log (who did what) — needed?

### API / library
- [ ] API versioning — strategy described?
- [ ] Rate limiting — mentioned?
- [ ] Error response format — standardized?
- [ ] Authentication scheme — specified?
- [ ] Deprecation policy — present?

### Product / startup spec
- [ ] Target customer named concretely (not "everyone")?
- [ ] Kill-criteria / falsification signals present (when to close the product/feature)?
- [ ] Clear PMF / success metric defined?
- [ ] Technical constraints and non-functional requirements described?
- [ ] At least one external demand signal (not "we're sure")?

## Step 6 — Optimism Bias Detector
Docs under proximity bias hide risks. Specifically hunt:
- **Sections with no risks, only upside** → suspicious: flag and demand a contra-scenario.
- **Numbers without a source** (market, load, conversion, deadlines) → tag `[UNVERIFIED]` next to the claim; treat as unproven until sourced.
- **All competitors weaker** / "we have no competitors" → almost always confirmation bias.
- **Asymmetry** "pro ≫ con" → signal of writing what they want to hear.

Format: `🔶 Optimism: [claim] — no risk/source → [UNVERIFIED] / needs contra-scenario`

## Output format
```markdown
# Requirement Critique: [ProjectName / BRD]

## ✅ Что хорошо
- [Конкретно что сделано правильно]

## ⚠️ Конфликты
- [Конфликт 1]
- [Конфликт 2]

## ❓ Неявные допущения
- [Допущение 1]
- [Допущение 2]

## 🕳️ Пробелы (Gap)
- [Что не покрыто]

## 🔶 Оптимизм-байас / [UNVERIFIED]
- [утверждение без риска или без источника] → [UNVERIFIED] / нужен contra-сценарий

## 📊 MoSCoW
| Требование | Приоритет | Комментарий |
|:---|:---|:---|
| [название] | Must | |
| [название] | Should | |

## 🔑 Вопросы к уточнению (топ-3)
1. [Самый критичный вопрос]
2.
3.
```

## Agent adds itself
- Edge cases the user didn't mention (typical for the product type)
- Technical assumptions invisible to business but blocking development
- A flag on requirements that will need far more resources than they seem

## Web-grounding / RAG
Sourced numbers (market/load/conversion/deadlines) tagged `[UNVERIFIED]` — verify via external search when needed; discipline `general/verify-claims` (resident in every project). Never assert external facts from memory.

## Hard prohibitions
NEVER:
- Propose solutions during critique — only record problems
- Rewrite requirements — only state what's wrong
- Skip any of the 6 checks
- Give a blanket "BRD is good" without specifics
- Accept numbers without a source as fact — tag `[UNVERIFIED]`

## Related skills
- `pm/brd` — audit target: critic checks a finished BRD (required BEFORE critique).
- `pm/prd-from-brd` — run AFTER closing found gaps, to avoid carrying them into PRD.
- `founder/risk-assessment` — assumptions and gaps from critique often become RAID-log entries.
- `architect/architecture` — critic is the last gate before the architecture phase (HOW).
- `founder/idea-audit` — sibling: same skepticism but on a raw idea/concept (pre-BRD); requirement-critic works on the written spec/BRD doc.
- `general/verify-claims` — discipline for checking `[UNVERIFIED]` claims via external search.

<!-- ru-source-sha256: 271d3e0a2e4a7554a97827b2041b98e546530d52c5d8ef3eca5551938d7ba05c -->
