---
name: runbook
bucket: operator
version: 0.1.0
description: Operational runbook template per P1/P2 alert — symptoms, diagnostics, mitigation steps, escalation, post-actions
risk: draft
persona: operator
tags: [ops, incident, template, monitoring]
requires: []
produces_for: [incident-response]
outputs: ["docs/03_Dev/Runbooks/[AlertName].md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# Skill: Runbook

Apply when: a prod alert exists that may page on-call. Every P1/P2 alert **must** have a runbook. Runbook = step-by-step from "saw alert" to "fixed or escalated".

## When NOT to apply
- Non-paging alerts (SEV-3/SEV-4 tickets).
- Informational / notify-only alerts — runbook redundant.
- Alerts still being tuned ("checking it doesn't spam") — validate first, then runbook.
- Single-user issue (that's support flow, not runbook).
- Alerts you plan to disable — disable them, don't write a runbook.
- No incident-response process → pointless; do `incident-response` first.

## Step 1. One alert = one runbook
- Per alert: separate file `docs/03_Dev/Runbooks/<alert_name>.md`. Filename = alert name in the system (Prometheus rule name, Datadog monitor name, etc.). Alert → runbook link straight from the page → one click.
- Anti-pattern: one "general runbook" with sections for 30 alerts.

## Step 2. Mandatory runbook sections
```markdown
# Runbook: <AlertName>

**Severity:** SEV-X
**Owner:** team / @person
**Last updated:** YYYY-MM-DD by @author
**Linked alert:** <link to rule in Prometheus/Datadog/etc>

## Symptoms
What the user sees / what's on the dashboard. Clear criterion "this is it".

## Likely causes
Top-3 causes by frequency over last N months. If new alert — hypotheses.

## Diagnostic steps
1. Open dashboard X → check Y
2. Query logs `query: ...`
3. Check upstream / dependency Z status

## Mitigation
What to do to make the user better **now**.
- Option A: rollback deploy (command: ...)
- Option B: scale up replicas (command: ...)
- Option C: feature flag off (command: ...)

## Verification
How to confirm mitigation worked. Concrete signal, not "looks ok".

## Escalation
When to escalate and to whom.
- If diagnostics didn't find cause in 15 min → @team-X
- If payment flow affected → @payments + Comms Lead

## Post-actions
What to do **after** resolve:
- Open postmortem ticket (if SEV-1/2)
- Create root-cause issue
- Record in `tech-debt-audit` if structural problem
```

## Step 3. Diagnostic steps — what to write
Rule: concrete commands, links, queries — not "check service health".

| Good | Bad |
|:---|:---|
| `kubectl get pods -n api -l app=checkout` | "check pod status" |
| Open dashboard: <link> panel "p99 latency" | "check metrics" |
| Datadog: `service:checkout status:error` over 15 min | "logs" |
| `psql -c "SELECT count(*) FROM jobs WHERE status='stuck'"` | "look in DB" |

If a step needs prod access — state **which level** and what to do if you lack it (fast escalate).

## Step 4. Mitigation — reversibility priority
Preference order:
1. **Feature flag off** — instant, reversible, doesn't touch deploy.
2. **Rollback deploy** — fast, relatively safe.
3. **Scale (out/up)** — if capacity issue.
4. **Hotfix** — last option, raises risk of second-order incident.

Per mitigation:
- Command / procedure (exact copy-paste).
- What confirms success.
- What confirms failure → next option.

## Step 5. Keeping it current
Runbooks rot fastest in the repo.

| Trigger | Action |
|:---|:---|
| Used runbook in incident | After postmortem — review, update |
| Service changed (new dependency, migration) | Owner walks their runbooks |
| Alert silent > 6 months | Review: still relevant? Possibly delete |
| Runbook didn't help in incident | Postmortem states explicitly what to fix in runbook |

Health metric: % of runbook uses where it actually helped (post-incident survey: helpful / partially / not at all).

## Step 6. Alert↔runbook linkage
Alert **must** carry runbook link in its payload:
```yaml
# Prometheus alert example
- alert: HighErrorRate
  annotations:
    summary: "5xx rate > 5%"
    runbook_url: "https://github.com/org/repo/blob/main/docs/03_Dev/Runbooks/HighErrorRate.md"
```
No `runbook_url` → alert must not page (policy). CI check optional (linter over Prometheus rules).

## Agent adds
- Runbook template (ready markdown, copy-replace).
- Link to `incident-response`: state in runbook which severity/IC roles apply.
- Directory hint: `docs/03_Dev/Runbooks/<AlertName>.md` (one filename = one alert name).
- "Runbook ready" checklist: has symptoms / diagnostics ≥ 3 steps / mitigation ≥ 2 options / concrete verification.
- PII warning: no real user data in examples — masks only.

## Output dir structure
Structure of `[AlertName].md` = Step 2. File named after the alert:
```
docs/03_Dev/Runbooks/
├── HighErrorRate.md
├── DatabaseConnectionsExhausted.md
├── PaymentWebhookFailure.md
└── _README.md  ← index, owners, review dates
```

## Hard forbiddens
- Pageable alert without runbook (CI should catch if present).
- One runbook for many alerts ("general troubleshooting").
- Diagnostic steps like "google it" / "ask the architect".
- Mitigation without `verification` section.
- Hotfix as first mitigation option.
- Real PII / secrets in example commands.
- Silent staleness: runbook untouched > 6 months → review mark.
- Storing runbooks outside repo (Confluence-only, Notion-only) — lost on tooling rotation.

## Links
- `operator/incident-response` — prerequisite; without an incident process a runbook is meaningless; severity/IC roles come from here.
- `operator/oncall-rotation` — page must link to runbook; runbook = what to do when paged.
- `operator/postmortem` — stale runbook surfaces in postmortem → AI to update (postmortem produces_for runbook).
- `operator/capacity-planning` — scale-up mitigation relies on autoscaling policy and max replicas.
- `architect/observability-design` — alerting defines which alerts need runbooks (runbook_url in payload).
- `laravel-testing/health-checks` — /health (live/ready) as source of symptoms and diagnostic steps.
- `laravel-extras/pennant-development` — feature-flag off as priority (reversible) mitigation.
- `quality/tech-debt-audit` — structural problem from post-actions → row in Tech_Debt_Register.
