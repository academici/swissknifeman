---
name: customer-discovery
bucket: founder
version: 0.1.0
description: Systematic discovery — target profile, interview framework (past not future), post-interview 2-list analysis, asymmetry-check every 5 interviews, outreach automation
risk: draft
persona: founder
tags: [discovery, validation, market]
requires: [idea-discovery]
produces_for: [competitive-analysis, monetization-design, new-project]
outputs: ["docs/01_Business/00_Customer_Discovery.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Customer Discovery

Apply when: hypothesis from `idea-discovery` is formulated and run through `adversarial-check`, and you must confirm it with live conversations before building. Idea-stage; primary source of problem-solution fit evidence. Extends Mom-Test core of `idea-discovery`: **who** to ask, **what** to ask, **how** to analyze. Learning quality = (1) question quality × (2) right people.

## Do NOT apply when
- No testable hypothesis (do `idea-discovery` first).
- Solution already validated, MVP underway — that's `pmf-diagnostics`, not discovery.
- Hypothesis failed `adversarial-check` (KILL) — discovery won't save a dead idea.

## 1. Who to ask (target profile)
Precise profile > long contact list.
- **Job titles** — concrete roles feeling the problem acutely (not "business", but "SMB CFO, 50–200 ppl").
- **Company type / size** — segment, size, industry.
- **Team structure / seniority** — who decides, who suffers (not always same person).
- **Where reachable** — communities, events, LinkedIn groups, Slack/Telegram, subreddits.
- **Prioritization** — first by closeness to problem.
- Hypothesis touching >1 role (e.g. finance manager + CFO) → **separate question sets** per role; one framework would blur the difference.

## 2. What to ask (interview framework)
**Core rule: past, not future.** Rookie mistake — broad future question ("would you use a product that…") instead of concrete past ask ("tell me about the last time you hit this").

**Opening (context):**
1. Tell me about your role — typical day?
2. What tools do you use for [problem area]?

**Core (past behavior):**
3. Tell me about the **last time** you hit [problem].
4. How often? How painful?
5. What do you do now to cope? (workaround)
6. What's most annoying about the current approach?

**Probe (on deflection / vagueness):**
7. [Vague] "Can you give a concrete example?"
8. ["Not a problem"] "How do others on the team cope?"

**❌ Forbidden:**
- "Would you use…" (future-facing)
- "How important is feature X to you?" (social desirability)
- "Do you agree [problem] exists?" (leading)

## 3. Post-interview analysis
After **every** conversation — debrief: what **confirmed** the hypothesis, what **refuted**, what **surprised**.

**Every 5 interviews — synthesis + asymmetry check:**
- Two lists: evidence FOR hypothesis, evidence AGAINST.
- Recurring themes (heard 3+ times), surprises, contradictions.
- **If FOR significantly longer than AGAINST — ask: is this real in the data, or what I wanted to hear?** (see `adversarial-check`).

## 4. Outreach & schedule (automation)
Offload ops to tools (in Brain: MCP / Claude Code; in Cowork: connectors):
- From target profile → prospect list with verified contacts.
- Personalized outreach emails per role/context.
- Schedule (Gmail/Calendar via MCP), day-7 follow-up, status tracking table.
- Founder focuses on the **conversations**, not coordination.

## Output file structure
`docs/01_Business/00_Customer_Discovery.md`:

```markdown
---
project: [ProjectName]
stage: idea
created: YYYY-MM-DD
interviews_done: 0
---

# Customer Discovery — [ProjectName]

## Гипотеза (из idea-discovery)
[проверяемая форма]

## Target profile
- Job title / company / team / seniority / где досягаемы / приоритет

## Interview framework
[вопросы по секциям; разные наборы для разных ролей]

## Лог интервью
| # | Дата | Роль | Подтвердило | Опровергло | Сюрприз |
|---|---|---|---|---|---|

## Synthesis (каждые 5)
- FOR: …
- AGAINST: …
- Asymmetry check: реальный сигнал или wishful thinking?

## Вывод
→ problem-solution fit достигнут? (вход в startup-lifecycle idea-gate)
```

## Agent adds
- **Draft-questions audit.** Flags leading / future-facing / too-broad; suggests follow-up probe for 2–3 deflection-prone moments.
- **Recruit logic.** Min interviews, which segments, where to find.
- **Pattern-matching warning.** Flags where own reading of data may be bent to wishful thinking.

## Related skills
- `founder/idea-discovery` — **requires**: supplies hypothesis and target sketch
- `founder/adversarial-check` — synthesis/asymmetry check relies on it
- `founder/competitive-analysis` — consumer: confirmed pains set the competitive frame
- `founder/startup-lifecycle` — discovery closes Idea-exit (problem-solution fit)
- `pm/pmf-diagnostics` — next validation in time (already at MVP, not Idea)

<!-- ru-source-sha256: cf27d0750d0296d26ff048e9994b32153f0cd6989a29249e0bb9ea8c4d0ec2ea -->
