---
name: product-roadmap
description: "MVP definition, Impact/Effort prioritization, MVP → v1 → v2 → Backlog phases, phase-transition metrics"
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

**User:** [Who exactly]
**Job-to-be-done:** [What does he want to do?]
**Proof of value:** [How to prove that there is value]
**Success Metric:** [Specific figure via X weeks]
**Out of scope MVP:** [What is clearly not included MVP]
```

## Step 1.5. Scope guard: feature-amendment criteria

Agentic coding removed the traditional anti-scope-creep forcing function (engineering cost); feature now costs an afternoon → zero-friction scope creep. Antidote: scope document before first line of code, shifting the decision point:
- ❌ "Should we add this?" (answer is always "sure, useful")
- ✅ "Has a critical mass of real users said they get no value without it?"

```markdown
## Scope guard
**The product does:** [one sentence - core]
**The product does NOT intentionally:** [list - more important than in-scope]
**Feature-amendment criteria:** a new feature is added ONLY if ___
  (concrete proof from real users, not founder-enthusiasm under the guise product thinking)
```

When a new feature idea surfaces — run it through the criterion: genuine user signal or enthusiasm? Use `adversarial-check` to distinguish.

## Step 2. Feature prioritization

Impact/Effort matrix:

| Feature | Impact (1-5) | Effort (1-5) | Ratio | Phase |
|:---|:---|:---|:---|:---|
| [Feature A] | 5 | 1 | 5.0 | ✅ MVP |
| [Feature B] | 4 | 2 | 2.0 | ✅ MVP |
| [Feature C] | 3 | 4 | 0.75 | 🔜 v1 |
| [Feature D] | 2 | 5 | 0.4 | ❌ Backlog |

**Rule:** MVP = everything with Ratio ≥ 2 and Impact ≥ 4.

## Step 3. Phases

```markdown
## MVP (0 → first paying user)
**Duration:** [X weeks]
**Features:**
- [Feature 1] — critical for core job
- [Feature 2] — impossible without it

**NOT in MVP:**
- [Enumeration]

---

## v1 (MVP → Product-Market Fit)
**Target:** Retention ≥ 40% (Day 30), NPS ≥ 40
**Features:**
- [Features that improve retention]
- [Key pain points from feedback]

---

## v2 (PMF → Growth)
**Target:** Enable growth-channels
**Features:**
- [Features that improve CAC: viral loop, referral, SEO]
- [Monetization: tariffs, upselling]

---

## Backlog (someday)
- [Everything else]
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
