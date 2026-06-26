---
name: requirement-critic
bucket: pm
version: 0.1.0
description: BRD audit: completeness, conflicts, assumptions, gap analysis, MoSCoW. Chat-only, no file
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

## Hard prohibitions
NEVER:
- Propose solutions during critique — only record problems
- Rewrite requirements — only state what's wrong
- Skip any of the 5 checks
- Give a blanket "BRD is good" without specifics

## Related skills
- `pm/brd` — audit target: critic checks a finished BRD (required BEFORE critique).
- `pm/prd-from-brd` — run AFTER closing found gaps, to avoid carrying them into PRD.
- `founder/risk-assessment` — assumptions and gaps from critique often become RAID-log entries.
- `architect/architecture` — critic is the last gate before the architecture phase (HOW).

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 9772f86cb54d88168d3b9f8943183ce14c90d6ec539f3ca24fda4b642413db4d -->
