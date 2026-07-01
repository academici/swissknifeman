---
name: postmortem
bucket: operator
version: 0.1.0
description: Blameless postmortem after SEV-1/2 incident — timeline, root cause (5 Whys), contributing factors, action items, knowledge distribution
risk: draft
persona: operator
tags: [incident, ops, workflow, reflection]
requires: [incident-response]
produces_for: [tech-debt-audit, runbook]
outputs: ["docs/03_Dev/Postmortems/[YYYY-MM-DD]_[ShortName].md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Postmortem

Apply when: SEV-1/SEV-2 incident closed (`incident-response` → RESOLVE); capture **what happened, why, what changes**. Mandatory part of incident lifecycle, not optional.

## When NOT to apply
- SEV-3/4 (backlog ticket suffices)
- Repeat of already-analyzed incident → update existing PM + raise unresolved action items
- External incident (vendor outage) with no reaction from us → short note suffices
- "Near miss" unnoticed by users → optional, usually useful

## Step 1. Blameless principle
Analyze **systems and processes**, not people. Forbidden:
- Name a person as root cause ("Alice deployed broken code")
- "should have known", "should have checked"
- Personal performance discussion (separate channel)

Allowed:
- Describe people's actions neutrally ("engineer deployed")
- Discuss what in the system made the error possible (no staging, no canary, no smoke tests)

Goal: a second identical incident must be impossible regardless of who is on shift.

## Step 2. Structure — mandatory sections

```markdown
# Postmortem: <ShortName> — <Date>

**Severity:** SEV-X
**Duration:** HH:MM (detect → resolve)
**Impact:** N users affected, $X revenue lost / Y errors / Z downtime min
**Owner:** @person
**Status:** Draft / In Review / Finalized

## Summary
2-3 sentences. What happened, what effect, what was fixed.

## Timeline (UTC)
| Time | Event | Source |
|:---|:---|:---|
| HH:MM | Алерт сработал | PagerDuty |
| HH:MM | IC объявлен | #incident-N |
| HH:MM | Гипотеза X | log message |
| HH:MM | Rollback deploy abc123 | git log |
| HH:MM | 5xx нормализовался | dashboard |
| HH:MM | SEV закрыт | IC |

## Root Cause
What **actually** broke. Technical + systemic level.
**Технический:** запрос N+1 в новой версии checkout-service вызвал DB connection pool exhaustion.
**Системный:** PR прошёл review без нагрузочного теста; staging не имел нагрузки приближённой к prod.

## Contributing Factors
- Не было canary deployment
- Алерт на connection pool сработал с задержкой 8 мин (порог слишком высокий)
- Runbook DatabaseConnectionsExhausted указывал на старую процедуру

## What went well
- IC объявлен быстро
- Rollback сработал чисто
- Comms обновляли status page вовремя

## What went poorly
- Не было canary → весь трафик ушёл на сломанную версию
- Runbook устарел → SME 5 мин искал актуальную команду
- Юзеры узнали раньше из Twitter, чем мы со statuspage

## Action Items
| Action | Owner | Due | Priority |
|:---|:---|:---|:---|
| Включить canary deployment | @bob | 2 weeks | P1 |
| Снизить порог alert N | @anna | 1 week | P1 |
| Update runbook DatabaseConnectionsExhausted | @carol | 3 days | P2 |
| Add staging load test для checkout | @bob | 1 month | P2 |

## Lessons
1-3 lessons as "rules". Structural ones move to `tech-debt-audit`.
```

## Step 3. Root Cause Analysis — 5 Whys (or variant)
Don't stop at first "why" — dig to the system.

Example:
1. Why: checkout 5xx → connection pool exhausted
2. Why: pool exhausted → new code did N+1 query
3. Why: code passed review → no load test, N+1 invisible on small dataset
4. Why: no load test → staging env without realistic data volume
5. Why: staging without volume → historically dev-only, never reached prod-parity

Rule: ≥ 3 levels of "why", else action items become cosmetic.

Alternative: Fishbone diagram, Causal map — for very complex multi-system incidents.

## Step 4. Action Items — quality criteria
Every AI must have:
- **Owner** (one person, not "team")
- **Due date** (concrete, not "when we can")
- **Priority** (P1 = before next deploy, P2 = this quarter, P3 = backlog)
- **Verifiable** — how we know it's done

Anti-pattern AI:
- "Будем внимательнее" (not verifiable)
- "Документировать процесс" (no owner / due)
- "Обсудить с командой" (not an action)

Rule: AI without owner+due is not an AI, it's a wish. Return to draft.

## Step 5. Review process
| Stage | Who | Deadline |
|:---|:---|:---|
| Draft | IC or assigned owner | 48h after resolve |
| Internal review | Tech team | 1 week |
| Cross-team broadcast (if impact > one team) | Owner | 2 weeks |
| Action items tracked | Owner + team lead | Until all P1 closed |

Publish: in repo (this skill), link in incident channel. Search-able. Not Notion-only, not "lost in Slack".

## Step 6. Postmortem-process metrics
| Metric | Target | Meaning if exceeded |
|:---|:---|:---|
| Drafted within 48h | ≥ 90% | Process dying |
| Action items P1 closed within deadline | ≥ 80% | AI written "on paper" |
| Repeat incidents same root cause | < 10% | Lessons not working |
| Postmortem reviewed by ≥ 2 people | 100% | Need external view |

## What the agent adds
- Markdown template ready to copy
- File naming convention: `YYYY-MM-DD_<ShortName>.md` (chronological sort)
- Action items import to issue tracker — leave a hook (don't do it ourselves; anchor link in template)
- Link to `tech-debt-audit`: "structural problem" lessons → Tech_Debt_Register rows, impact high
- Link to `runbook`: if runbook outdated/missing → AI to update/create runbook
- Blameless checklist: verify timeline has no names in negative context, no "should have" phrasing

## Output file structure `[YYYY-MM-DD]_[ShortName].md`
See Step 2 (full structure). Folder:

```
docs/03_Dev/Postmortems/
├── 2025-03-14_checkout-5xx.md
├── 2025-04-02_payment-webhook-down.md
└── _index.md  ← перечень + статус action items
```

## Hard prohibitions
- Name a person as root cause / contributing factor
- Close SEV-1/2 without postmortem (process violation)
- Action items without owner+due+priority
- Action items like "be more careful" / "communicate better"
- Hide postmortem in internal chat — must be in repo
- Finalize without at least one external reviewer (min 2 eyes)
- Ignore `What went well` — part of the culture; without it PM becomes only punishment
- Close postmortem without 5 Whys (or alternative RCA method) to structural level

## Links
- `operator/incident-response` — postmortem input: action log, severity, timeline (lifecycle RESOLVE → POSTMORTEM)
- `operator/runbook` — outdated/missing runbook → action item to update/create (produces_for)
- `quality/tech-debt-audit` — structural lessons → Tech_Debt_Register rows, impact high (produces_for)
- `operator/capacity-planning` — capacity incidents: root cause often = lack of headroom/forecast
- `architect/observability-design` — contributing factor "alert fired late" → tune thresholds/SLO
<!-- ru-source-sha256: 0e4a3de231ff381cf4bc850c07710a6d81e6c3ef9c4b2edeffdfb07a5d672567 -->
