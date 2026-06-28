---
name: idea-discovery
bucket: founder
version: 0.1.0
description: Structured interview of a raw idea — JTBD, problem statement, hypothesis, before competitive-analysis
risk: draft
persona: founder
tags: [discovery, requirements, market]
requires: []
produces_for: [competitive-analysis, monetization-design, new-project]
outputs: ["docs/01_Business/00_Idea_Discovery.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Idea Discovery

Apply when: user brings a raw idea ("want to build X", "thought about Y") and there is no competitive-analysis, BRD, or even one-line product statement yet. Turn idea into a structured artifact downstream skills rely on.

First step of Founder chain: `idea-discovery → adversarial-check → customer-discovery → competitive-analysis → risk-assessment → new-project`.

## Do NOT apply when

- Idea already in `docs/01_Business/01_Concept_and_Monetization.md` or BRD → skip, go to `competitive-analysis`.
- User asks for a specific doc (BRD, GTM, risks) → not discovery; load the target skill.
- Technical question about an existing project → Founder mode does not activate.

## Interview principles

1. **Socratic, not survey.** One question at a time, wait for answer, dig deeper. Don't dump a checklist.
2. **JTBD frame.** Not "what's the product?" but "when [situation], person wants [outcome], so that [benefit]".
3. **No solutions.** Don't drift into stack, features, UI. Problem and context only.
4. **Mom Test.** Never ask "do you like the idea?" — only past behavior and facts.
5. **Caveman style.** Short replies. No preambles.

## Interview — 5 sections (in order)

1. **Trigger** — Where did idea come from? (own pain / someone's request / market signal). Was there a specific incident that sparked it?
2. **JTBD** — **When** (context, situation), **who** (role/segment, not "everyone"), **wants** (job, action), **so that** (outcome, real benefit). Record one line per canon: `When [situation], [persona] wants to [job], so that [outcome].`
3. **Problem statement** — How solved now? (workarounds). What exactly hurts in current solution? (3 concrete points). Frequency? (daily / weekly / monthly / rare). Cost of not solving? (money / time / forgone benefit).
4. **Hypothesis** — formulate as testable:
```
Мы верим, что [сегмент] нуждается в [решение]
потому что [инсайт о боли].
Узнаем, что правы, когда [метрика валидации].
```
5. **Kill-criteria** — at what market signal do we close the idea before dev starts? Min 2 criteria — usually "nobody pays" + "does not reproduce across other segments". **Falsification signal per criterion**: a concrete measurable metric and threshold at which it counts as triggered (not "low interest" but "<N of 20 interviews willing to pay $X"). Without a measurable threshold, kill-criteria don't work — they're easy to rationalize away.

## Problem-solution fit (exit of Idea stage)

Leave Idea stage when all **three** (Founder's Playbook) are "yes":

1. **Problem real, specific, frequent?** — name who faces it, how often, how painful, what they do now.
2. **Solution hits the real problem?** — the one validation uncovered, not the original assumption (sometimes matches, sometimes not).
3. **Signal enough to justify MVP?** — reasoned decision vs act of faith, not a certificate.

Evidence is gathered in `customer-discovery` (live conversations), not here; this skill sets the **hypothesis** they test. Before fixing the hypothesis → `adversarial-check` (AI confirms anything; pressure-test needed). Stage risk: **mistaking building for validating** — a working prototype is only a reason for conversation; proof is the conversation itself.

## What the agent adds itself

- **Alternative segments.** If user said "for everyone" — propose 2–3 narrow ICPs.
- **Adjacent JTBD.** If idea is a special case of a larger job, name it explicitly.
- **Synergies with vault.** Check project map in `CLAUDE.md §3` — overlap with TcenZor / Memster / Edufy / Finbrain.
- **Anti-patterns.** If idea smells like "solution in search of a problem" — name it directly before competitive-analysis.

## Output-file structure

`docs/01_Business/00_Idea_Discovery.md`:

```markdown
---
project: [ProjectName]
stage: discovery
created: YYYY-MM-DD
---

# Idea Discovery — [ProjectName]

## Триггер
[откуда взялась идея]

## JTBD
When [situation], [persona] wants to [job], so that [outcome].

## Problem statement
- Текущее решение: ...
- Боли: 1) ... 2) ... 3) ...
- Частота: ...
- Стоимость нерешения: ...

## Hypothesis
Мы верим, что ...
Потому что ...
Узнаем, что правы, когда ...

## Kill-criteria
1. ...
2. ...

## Альтернативные сегменты (агент)
- ...

## Синергии с vault (агент)
- [[ProjectName]] — ...

## Anti-patterns / red flags (агент)
- ...

## Следующий шаг
→ `.ai/skills/founder/competitive-analysis.md`
```

## Hard prohibitions at this stage

FORBIDDEN (all are later chain steps, not now):
- Discussing stack, technologies, architecture
- Detailing features or UX
- Computing unit-economics (no ICP and price yet)
- Writing BRD fragments
- Drifting into roadmap

## Related skills

- `founder/adversarial-check` — right after formulating hypothesis: pressure-test before committing resources
- `founder/customer-discovery` — chain continuation: turns hypothesis into evidence via live interviews
- `founder/startup-lifecycle` — frame: idea-discovery opens Idea stage, problem-solution fit = its exit
- `founder/competitive-analysis` — next chain step: JTBD here sets the competitive landscape
- `pm/monetization-design` — consumer: business-model choice relies on segment and pain from discovery
- `founder/new-project` — orchestrator: launches discovery as first step when setting up a project
- `general/spec-interview` — kindred interview method (one question at a time, agent reads context itself), but for a technical spec before code, not a business idea
- `founder/risk-assessment` — adjacent: kill-criteria and red flags overlap with market risks

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: d62b32515e2695e8fb78be38679cf7489d964cec56d1d9cef678a2426f151f09 -->
