---
name: product-roadmap
bucket: pm
version: 0.1.0
description: MVP definition, Impact/Effort prioritization, MVP → v1 → v2 → Backlog phases, phase-transition metrics
risk: draft
persona: pm
tags: [requirements, gtm, market]
requires: [brd, go-to-market]
produces_for: []
outputs: ["docs/01_Business/07_Product_Roadmap.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Product Roadmap

Apply when: task is roadmap, MVP, product phases, feature prioritization, v1/v2 scope.

Principle: Roadmap = strategic bets in chronology, not a wishlist. MVP = minimum at which the user gets value (not "minimum work for the team").

## Step 1. MVP Definition

Answer three questions:
1. **Who** gets value from MVP? (specific ICP from `[[Go_To_Market]]`)
2. **What value** — one specific job-to-be-done
3. **How will we know MVP works?** — success metric

```markdown
## MVP Definition

**Пользователь:** [Кто конкретно]
**Job-to-be-done:** [Что хочет сделать]
**Proof of value:** [Как докажем, что ценность есть]
**Метрика успеха:** [Конкретная цифра через X недель]
**Out of scope MVP:** [Что явно не входит в MVP]
```

## Step 1.5. Scope guard: feature-amendment criteria

Agentic coding removed the traditional anti-scope-creep forcing function (engineering cost); feature now costs an afternoon → zero-friction scope creep. Antidote: scope document before first line of code, shifting the decision point:
- ❌ "Should we add this?" (answer is always "sure, useful")
- ✅ "Has a critical mass of real users said they get no value without it?"

```markdown
## Scope guard
**Продукт делает:** [одно предложение — core]
**Продукт намеренно НЕ делает:** [список — важнее, чем in-scope]
**Feature-amendment criteria:** новая фича добавляется ТОЛЬКО если ___
  (конкретное доказательство от реальных пользователей, не founder-энтузиазм под видом product thinking)
```

When a new feature idea surfaces — run it through the criterion: genuine user signal or enthusiasm? Use `adversarial-check` to distinguish.

## Step 2. Feature prioritization

Impact/Effort matrix:

| Фича | Impact (1-5) | Effort (1-5) | Ratio | Фаза |
|:---|:---|:---|:---|:---|
| [Фича A] | 5 | 1 | 5.0 | ✅ MVP |
| [Фича B] | 4 | 2 | 2.0 | ✅ MVP |
| [Фича C] | 3 | 4 | 0.75 | 🔜 v1 |
| [Фича D] | 2 | 5 | 0.4 | ❌ Backlog |

**Rule:** MVP = everything with Ratio ≥ 2 and Impact ≥ 4.

## Step 3. Phases

```markdown
## MVP (0 → первый платящий пользователь)
**Длительность:** [X недель]
**Фичи:**
- [Фича 1] — критично для core job
- [Фича 2] — без неё невозможно

**NOT в MVP:**
- [Перечисление]

---

## v1 (MVP → Product-Market Fit)
**Цель:** Retention ≥ 40% (Day 30), NPS ≥ 40
**Фичи:**
- [Фичи, улучшающие retention]
- [Основные болевые точки из feedback]

---

## v2 (PMF → Growth)
**Цель:** Включить growth-каналы
**Фичи:**
- [Фичи, улучшающие CAC: viral loop, referral, SEO]
- [Монетизация: тарифы, апселл]

---

## Backlog (когда-нибудь)
- [Всё остальное]
```

## Document format

Place in `docs/01_Business/07_Product_Roadmap.md`

## Agent adds proactively

- "Quick wins" — high-impact, minimal-effort features the user didn't mention
- Explicit warning if MVP too big: "This isn't MVP, it's v1. MVP is [less]"
- Link to `[[Risk Register]]` — if a phase depends on an external factor
- Phase-transition metrics (when to consider a phase done)

## Hard prohibitions

NEVER:
- Roadmap without a success metric for each phase
- "Build everything first, then launch" — launch with MVP, iterate fast
- Features without justification (why, for whom, what it improves)
- Work on retention AND growth simultaneously — strictly sequential

## Related skills

- `pm/brd` — input: functional requirements from which MVP features are selected (required BEFORE roadmap).
- `pm/go-to-market` — source of ICP for MVP Definition and phase-transition metrics (required BEFORE roadmap).
- `pm/prd-from-brd` — RICE prioritization and story versions feed the phase breakdown.
- `pm/unit-economics` — phase-transition metrics (retention, CAC, LTV) at phase boundaries verified from here.
- `pm/pmf-diagnostics` — refines MVP-exit: MVP→v1 transition metric = genuine PMF (Sean Ellis, retention), not just "first paying".
- `founder/startup-lifecycle` — frame: MVP scope guard and phase gates = mechanics of Idea→MVP→Launch transition.
- `founder/adversarial-check` — feature-amendment filter: genuine signal vs founder enthusiasm.
- `founder/risk-assessment` — `[[Risk Register]]`: if a phase depends on an external risk, link explicitly.
