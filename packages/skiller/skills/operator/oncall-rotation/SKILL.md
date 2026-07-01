---
name: oncall-rotation
bucket: operator
version: 0.1.0
description: On-call rotation design — schedule, primary/secondary, handoff, compensation, burnout defusing, paging policy
risk: draft
persona: operator
tags: [ops, incident, sla, handoff]
requires: []
produces_for: [incident-response]
outputs: ["docs/03_Dev/OnCall_Rotation.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: On-Call Rotation

Apply when: service needs 24/7 (or at least business-hours) reaction time and you must fix **who & when** owns incidents. Team ≥ 2 engineers; SLA or at least internal reaction-time expectations exist.

## Do NOT apply
- Solo developer (always on-call) / no SLA, incidents handled "whenever noticed"
- One engineer in project — no rotation, just "him"
- No prod / no users — nothing to react to
- Fully managed service where provider is on-call (e.g. pure no-code Bubble + Stripe)
- Internal-only tool with tolerance > 1 working day

## Step 1. Coverage — what we protect
Define **reaction window** first, then rotation.

| Service | Reaction window | Rationale |
|:---|:---|:---|
| B2C SaaS, global audience | 24/7 | Users across TZs |
| B2B SaaS, US-only | 24/7 on working days, weekends best-effort | SLA in contracts |
| Internal tool | Team business hours | No external pressure |
| MVP in beta | Business hours + critical alerts | Balance burnout / risk |

**Anti-pattern:** 24/7 rotation for a service that doesn't need it — burns team without business gain.

## Step 2. Rotation size

| Team size | Rotation | Shift length | Note |
|:---:|:---|:---|:---|
| 2 | Don't do 24/7 | — | Burnout machine. Alt: business-hours only + best-effort after |
| 3 | Min 1 week/person, ≥ 2 weeks "rest" | 1 week | Tough but possible |
| 4-5 | Standard: 1 week on / 3-4 weeks off | 1 week | Sustainable |
| 6+ | Can do follow-the-sun (by TZ) | 12 hours or 1 week | Ideal |

**Rule:** ≥ 4 people in rotation = sustainability threshold. Fewer = plan as temporary measure.

## Step 3. Primary / Secondary

| Role | Reaction | Why |
|:---|:---|:---|
| **Primary** | Answers page within SLA (typically 5-15 min) | First strike |
| **Secondary** | Backup if primary doesn't answer within X min, or on SEV-1 | SPOF protection |

**Paging policy:**
- SEV-1: primary + secondary in parallel (or primary, then secondary after 5 min)
- SEV-2: primary, secondary after 15 min
- SEV-3: ticket, waits for business hours

Secondary engages **only if primary didn't answer** — not a stand-in who also drops everything.

## Step 4. Handoff
Shift handoff = separate artifact. Without it rotation becomes "everyone's own hell". Handoff note (5 min at shift end):

```markdown
## On-Call Handoff: [Date]
**From:** @alice  **To:** @bob

### Открытые инциденты
- [SEV-X | id] статус, что сделано, что осталось

### Активные алерты (noise)
- алерт X шумит, копаем; флапает, не реагировать пока ROOT.

### Изменения в проде за смену
- Deploy abc123 → checkout (риск средний)
- Feature flag X включён 50%

### Watchlist
- [ ] Дашборд Y — следить за latency завтра в пик
- [ ] Vendor Z объявил maintenance window 14:00 UTC
```

Post handoff in incident channel or shared doc, **not in DM**.

## Step 5. Compensation & politics

| Approach | Description | When |
|:---|:---|:---|
| **Time off** | Day off per on-call week | EU teams, default |
| **Pay** | $X/shift + $Y/page | US teams |
| **Comp time** | Accumulated day off | Hybrid |
| **None** | Part of base duties | Contentious, only if team agrees in writing |

**Hard minimum:**
- Whoever was paged at night may come later or take a day
- Pages > N per shift → review: paging policy broke
- Never give on-call feature tasks in parallel (focus killer)

## Step 6. Rotation health — metrics
Review monthly / quarterly:

| Metric | Target | Exceeding means |
|:---|:---|:---|
| Pages per shift | ≤ 2-3 | Noise, alert tuning needed |
| Pages outside working hours / shift | ≤ 1 | Strengthen self-healing |
| % shifts with secondary escalation | < 10% | Primary not coping (training? noise?) |
| MTTR (mean time to resolve) | matches SLA | Else runbooks don't work |
| Burnout signal (survey) | "comfortable" from 80%+ | Else revise rotation |

## Agent adds itself
- Scheduling tool recommendation (PagerDuty / Opsgenie / Grafana OnCall / Google Calendar — fallback)
- Markdown handoff note template (copy-ready)
- Min headcount calc for desired window (account vacations/sick — usually +1 over calculated)
- Junior-on-call warning: minimum 3 mo experience in team + shadowing 2 shifts before solo
- Link to `incident-response` — who Primary is in incident-response.IC terms

## Output file structure `OnCall_Rotation.md`

```markdown
# On-Call Rotation: [ProjectName]

## 1. Покрытие (окно реагирования + SLA)
## 2. Размер ротации и обоснование
## 3. Расписание (как генерируется, где живёт)
## 4. Primary / Secondary policy
## 5. Paging policy по severity (см. incident-response)
## 6. Handoff (когда, формат, где хранится)
## 7. Compensation
## 8. Junior on-call policy (shadowing, требования)
## 9. Метрики здоровья ротации (что измеряем, как часто смотрим)
```

## Hard prohibitions — NEVER
- 24/7 rotation on 2 people as permanent scheme (only bridge for 1-2 months)
- Primary simultaneously loaded with a feature task on deadline (double context-switch)
- Page without runbook — page must say what to do (see `runbook`)
- Change schedule on day of shift without consent of both participants
- Treat on-call as "free add-on to work" (fix comp in writing)
- Junior on-call without shadowing ≥ 2 shifts
- Use DM to summon on-call — only paging channel/tool (DMs get lost)

## Links
- `operator/incident-response` — Primary = IC in incident-response terms; severity matrix defines paging policy
- `operator/runbook` — page MUST point to a runbook; without it rotation is pointless
- `operator/capacity-planning` — lack of headroom = more pages = burnout; rotation health depends on capacity
- `architect/observability-design` — alert tuning & self-healing cut the noise that rotation health is measured by

<!-- ru-source-sha256: b315495bcabbab0701de183ce0faaea7b3cc2640cd3357ee7b9e612888f117b2 -->
