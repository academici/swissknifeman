---
name: idea-audit
bucket: founder
version: 0.1.0
description: Full destructive audit of an idea / concept / spec — first-principles → market skepticism → architectural pre-mortem → kill/build verdict. Antidote to confirmation-bias × AI × speed. Cross-stage.
risk: draft
persona: founder
tags: [validation, market, architecture]
requires: [idea-discovery]
produces_for: [brd, competitive-analysis, architecture, risk-assessment, new-project]
outputs: ["docs/01_Business/Idea_Audit.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Idea Audit

Apply when: there is a formulated idea, raw concept, or a ready spec/BRD, and hidden flaws must be **found before** the team starts building. The check must be **uncomfortable** — a comfortable audit is useless.

Core principle (per Anthropic Founder's Playbook methodology): AI supports what the user believes. The audit aims the tool the **opposite** way — finds weaknesses while they are cheap.

## Do NOT apply when

- No concrete idea / hypothesis → `idea-discovery` first.
- Single targeted pressure-test of one thesis → `adversarial-check` (faster, narrower).
- Object is a written **spec/BRD doc** (completeness/conflicts/MoSCoW) → `requirement-critic` (it works on the written doc; idea-audit works on the idea/concept).
- Broad RAID/risk pass needed → `risk-assessment`; idea-audit is its strategic prelude.
- Execution of an approved plan already underway → that is execution, not audit.

## Principles

1. **Attack the strongest version** of the thesis, not the convenient one.
2. **Default to refuted**: no data = weakness of the hypothesis, not neutrality.
3. **First principles first**: decompose to atoms, don't accept industry "obvious truths".
4. **Architect is also a skeptic**: tech debt, vendor-lock, wrong data-model kill as reliably as no market.
5. **Quantum of validation**: every conclusion rests on a signal (data / conversation / experiment), not logic.

## Module 0. First-Principles Decomposition (mandatory first)

Goal: strip "the obvious" and check what remains.

- **Step 0.1. Axiom list.** Write out **all implicit assumptions** ("users want X", "market Y is big", "tech Z allows it", "competitors didn't do P because…"). Format each:
```
[Confidence source]: own experience / others' experience / data / logic / faith
[Falsification signal]: at what observable event does the axiom collapse?
[Risk if wrong]: business consequence
```
- **Step 0.2. Risk ranking.** Risk = (probability of error) × (impact if wrong). Top-3 dangerous axioms → mandatory attack points in later modules.

## Module 1. Market skepticism (5 vectors)

Run all five. Market numbers **only** web-grounded (see "Web-grounding / RAG"), never from memory.

- **1.1 Pain real?** How many feel it **right now**? Source of the number? How do they solve it **without** the product? (if they do — pain is tolerable). Hard: "what concretely breaks in the target user's life without this product?" Context: "no market need" is historically the #1 startup-death cause (classic CB Insights post-mortem analysis, ~42%; 2026 update reframes as "poor product-market fit" ~43%).
- **1.2 Timing right?** Why now? What changed in 12–24 mo? Nothing changed → why not done 3 years ago? Changed → window or durable trend? Verify "Why now" via ≥3 independent sources.
- **1.3 Competitors failed — why won't you?** Who already tried (even indirectly)? Why failed? "We're better" → in what concretely? Structural advantage or "we're smarter"? Build the **most convincing** case where a competitor wins (not the convenient version of the threat).
- **1.4 Willing to pay?** WTP is tested by action, not words. What does the client do **now** to solve it? Pay for alternatives? How much? "Not paying yet, but will" — the most common early-stage delusion.
- **1.5 TAM real or drawn?** Top-down TAM (big number × share) is always a lie. Require bottom-up: how many concrete companies/people will pay a concrete price right now? Minimum viable market for unit-economics: CAC < LTV × 3.

## Module 2. Architectural pre-mortem

Goal: find technical risks that kill the product at Scale/Launch, **before** the first line of code.

- **Step 2.1. "Imagine failure in 18 months."** > Project failed, investors lost money, team split. Name 5 concrete **technical** reasons why. Mandatory categories:

| Category | Pre-mortem question |
|:---|:---|
| **Data model coupling** | Will the data schema need a full rewrite in 18 mo? |
| **Scalability cliff** | At what volume (DAU / RPS / data size) does the architecture fall? |
| **Vendor lock-in** | Which decisions create a dependency that is hard/costly to leave? |
| **Integration brittleness** | Which external APIs are critical? What if they change / fail / get pricier? |
| **Security debt** | What is simplified for speed, creating holes later (auth, PII, finances)? |
| **AI-specific risks** | Hallucination on the critical path? Agentic drift? Prompt injection? Cost creep? |

- **Step 2.2. Minimal viable architecture.** Don't design everything — find the **minimal** architecture reaching the first 1000 paying users without a critical refactor. "Architecture = decisions hardest to change later" — which are those here?
- **Step 2.3. Build vs Buy vs Adapt.** Per key component:
```
[Component] → Build / Buy / Adapt / Avoid
Rationale: [1–2 sentences]
Choice risk: [what goes wrong]
```

## Module 3. Internal contradictions of the concept

- **Step 3.1. Contradiction Scan.** Mutually contradicting statements; conflicting feature-promises ("simple for novices" + "powerful for experts" with no explicit mode); temporal (goal Q1, dependency ready Q3); resource (team of 3, plan of 15).
- **Step 3.2. Optimism Bias Detector.** Sections with no risks and only upside → suspicious. Numbers without a source → tag `[UNVERIFIED]`. Competitive analysis where all competitors are weaker → likely confirmation bias.

## Module 4. Kill-or-Build Verdict

### Scoring Matrix

| Criterion | Weight | Score (1–5) | Weighted |
|:---|:---|:---|:---|
| Pain real and verifiable | 3x | | |
| Timing right (Why-now clear) | 2x | | |
| Willingness to pay confirmed | 3x | | |
| TAM bottom-up viable | 2x | | |
| Technical pre-mortem passed | 2x | | |
| No contradictions in concept | 1x | | |
| **TOTAL** | **13x** | | **/65** |

**Interpretation:**
- 50–65: 🟢 **BUILD** — proceed to BRD / architecture
- 35–49: 🟡 **REVISE** — return to specific modules, state which
- 20–34: 🔴 **PIVOT** — idea frame wrong, change segment / problem / solution
- < 20: ⛔ **KILL** — structural problems, no point without full rework

### Verdict format
```
## Idea Audit Verdict: [idea name]
Score: [X]/65 — [BUILD / REVISE / PIVOT / KILL]

### Critical vulnerabilities (fix before BRD):
1. [vulnerability] → recommended action

### Unverified axioms (need validation):
- [axiom] — how to check: [experiment / interview / data]

### Architectural decisions to make before BRD:
- [decision]

### Next step:
→ BUILD: `pm/brd` / REVISE: back to `idea-discovery` / PIVOT: `adversarial-check` with new thesis
```

## Web-grounding / RAG

Market vectors (Module 1), failed competitors, "Why now", any numbers — **verify via external search**, do not generate from memory. Discipline canon — `general/verify-claims` (resident in every project). Before fixing a BUILD verdict, market data must have a source.

## What the agent adds itself

- **Catch own bias.** If the prior analysis was suspiciously optimistic — name it and attack harder.
- **Asymmetry check.** "Pro" heavily outweighs "con" → signal of confirmation bias, not reality.
- **Portfolio synergies.** Check whether the idea is partly built in a neighbor project (if a project map is in context).
- **Stage-aware depth.** `stage: idea` → full audit. `stage: mvp+` → focus on Modules 2 and 3.

## Hard prohibitions

FORBIDDEN:
- BUILD verdict without passing all 4 modules.
- TAM / CAC / LTV numbers without a source.
- Skipping the architectural pre-mortem even for "simple" ideas.
- Accepting "we're smarter than competitors" as an advantage without structural grounding.

## Related skills

- `founder/idea-discovery` — supplies the hypothesis; idea-audit follows right after.
- `founder/adversarial-check` — fast targeted pressure-test of one thesis; idea-audit — full destructive audit of the whole idea.
- `founder/competitive-analysis` — deepens Vector 1.3 (competitors).
- `founder/risk-assessment` — deepens RAID; idea-audit is its strategic prelude.
- `architect/architecture` — receives Module 2 as input for the pre-mortem.
- `architect/tech-stack-selection` — deepens Step 2.3 (Build vs Buy).
- `pm/requirement-critic` — sibling: same skepticism but on a written spec/BRD doc.
- `pm/brd` — consumer: takes the idea with a BUILD verdict and Scoring Matrix as input.
- `founder/startup-lifecycle` — idea-audit = mandatory step before exiting the Idea stage.
- `general/verify-claims` — web-grounding discipline for market facts.
