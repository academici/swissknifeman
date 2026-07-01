---
name: incident-response
bucket: operator
version: 0.1.0
description: Prod incident response process — severity levels, roles (IC/Comms/SME), communication, action log, handoff to postmortem
risk: draft
persona: operator
tags: [incident, ops, workflow, sla]
requires: []
produces_for: [postmortem]
outputs: ["docs/03_Dev/Incident_Response.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Incident Response

Apply when: service in prod, need documented response process (severity, decision-makers, user comms, action capture). Typically after first real incident, or team grown to 3+ engineers.

## Do NOT apply
- Pre-prod / prototype
- Solo dev without SLA
- Internal team tool with no dependent users
- Corporate incident process already exists — don't duplicate, only adapt

## Step 1. Severity levels

| Severity | Description | Example | Reaction |
|:---:|:---|:---|:---|
| **SEV-1** | Full outage of critical service, data loss, security breach | Site down, DB corrupting | Page all on-call, IC assigned in 5 min, status page updated in 15 min |
| **SEV-2** | Degradation of significant share of users/functions | Checkout broken, 30% of requests 5xx | Page on-call, IC in 15 min, status updated in 30 min |
| **SEV-3** | Degradation of non-critical function or issue for < 5% users | Search slow, background job stuck | Ticket to queue, handle in business hours |
| **SEV-4** | Cosmetic / single-user issue | Label misaligned | Normal bug-flow |

Severity defines **speed**, not **importance**. A SEV-3 bug can be business-critical but it's backlog, not incident.

## Step 2. Incident roles

| Role | Responsibility | Assigned when |
|:---|:---|:---|
| **Incident Commander (IC)** | Makes decisions, doesn't fix. Coordinates. | Immediately on SEV-1/2 declaration |
| **Subject Matter Expert (SME)** | The one who fixes. Can be several. | As pulled in |
| **Communications Lead (Comms)** | Status page, users, internal stakeholders | SEV-1, or incident > 30 min |
| **Scribe** | Real-time action log | SEV-1, optional SEV-2 |

IC ≠ SME. If a person fixes, they can't coordinate simultaneously. Small team (≤ 3) — IC and Comms may be one.

## Step 3. Incident lifecycle

```
1. DETECT      — alert fired / user reported / saw metric
   ↓
2. DECLARE     — IC declares incident, severity, opens channel
   ↓
3. INVESTIGATE — SMEs find root cause, IC coordinates, Scribe logs
   ↓
4. MITIGATE    — service restored (not necessarily cured — may rollback, disable feature)
   ↓
5. RESOLVE     — root cause fixed or mitigation confirmed reliable
   ↓
6. POSTMORTEM  — see postmortem skill (mandatory for SEV-1/2)
```

Mitigate ≠ fixed. Deploy rollback = mitigation, code bug fix = resolve. Postmortem written after resolve.

## Step 4. Channels & communication

| Channel | When | Who writes |
|:---|:---|:---|
| `#incident-<id>` in Slack/Discord | SEV-1/2 — dedicated channel per incident | All participants |
| Status page (statuspage.io / instatus / homegrown) | SEV-1/2 — public | Comms Lead |
| Internal mailing / channel announce | SEV-1 — every 30 min | IC |
| Postmortem doc | After resolve | Owner assigned by IC |

Single source of truth = incident channel. No discussions in DM. Everything in channel.

Status page template:
- `Investigating`: «We're aware of [problem] affecting [scope]. Investigating.»
- `Identified`: «Cause identified as [X]. Working on fix.»
- `Monitoring`: «Fix deployed. Monitoring.»
- `Resolved`: «Resolved at HH:MM. Postmortem to follow.»

## Step 5. Action Log

In incident channel — mandatory with timestamps. Every action, hypothesis, observation.

```
14:32 [Alert] api-5xx-rate > 5% over 5 min
14:34 [IC] @anna declaring SEV-2, IC=me
14:35 [SME] @boris checking api-server metrics
14:38 [SME] boris: 5xx from /checkout, rest ok
14:40 [Hypothesis] last deploy 14:20 touched checkout
14:42 [Action] rolling back deploy → SHA abc123
14:45 [Mitigation] 5xx dropped to baseline
14:50 [Decision] keep rolled-back version, fix separately
15:10 [Resolve] SEV-2 closed
```

Basis for postmortem; timeline of facts without interpretation.

## Step 6. Escalation

When to wake the second/third person.

| Condition | Action |
|:---|:---|
| SEV-1 declared | Page primary on-call immediately |
| Primary on-call no response in 15 min | Page secondary |
| SEV-1 > 1 hour without mitigation | Escalate to management |
| Affects legal / compliance / PII | Comms Lead notifies legal/security immediately |
| Decision beyond on-call authority (e.g. paying for third-party service) | Escalate to management |

## Agent adds
- "First 5 minutes" checklist for on-call (pinned in Runbooks)
- Incident channel topic template: `SEV-X | IC: @name | Status: investigating | Started: HH:MM`
- Paging tool recommendation (PagerDuty / Opsgenie / Grafana OnCall) — chosen by budget and stack
- Blameless culture warning: action log and postmortem hold actions and facts, not judgments of people
- Link to architectural artifacts: every alert references a runbook (see `runbook`), runbook → architectural context

## Output file `Incident_Response.md` structure

```markdown
# Incident Response Process: [ProjectName]

## 1. Severity matrix (SEV-1..4 with examples for this product)
## 2. Roles (IC/SME/Comms/Scribe) + who can be IC
## 3. Lifecycle (DETECT → POSTMORTEM)
## 4. Channels & communication (where to write what)
## 5. Status page (URL + who updates)
## 6. Escalation matrix (when to wake whom)
## 7. Action log template
## 8. Link to on-call rotation and runbooks
```

## Hard forbidden
- IC fixing by hand simultaneously (loses coordination)
- Discussing incident in DM bypassing channel (incomplete action log)
- Declaring SEV-1 without clear criteria (devalues severity)
- Closing incident without recording postmortem owner (SEV-1/2)
- Naming people's blame in action log ("X screwed up") — actions and facts only
- Lowering severity without IC's consent (easy to hide SEV-2 as SEV-3)
- Deploying fix to prod without code review during SEV-1 "because it's burning" (one disaster breeds the next) — except explicit rollbacks

## Links
- `operator/runbook` — per pageable alert; SME takes first diagnostic/mitigation steps from here
- `operator/oncall-rotation` — Primary/Secondary definition, paging policy by severity, escalation
- `operator/postmortem` — mandatory step after RESOLVE for SEV-1/2 (lifecycle → POSTMORTEM)
- `operator/capacity-planning` — capacity incidents as separate classification; pre-event war room
- `architect/observability-design` — alerting/SLO/error budget on which DETECT and severity matrix are built

<!-- ru-source-sha256: 188b534da19a9575bb20d47b8645a3830c4b787dee22a3c5e3ac8be4c83373b8 -->
