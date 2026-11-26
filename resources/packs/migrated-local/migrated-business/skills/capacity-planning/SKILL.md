---
name: capacity-planning
description: "Capacity planning — load forecasting, headroom, autoscaling policy, cost budget, what to monitor, when to scale up/down"
---

# Skill: Capacity Planning

Apply when: service in prod, load metrics for ≥1 month, question is "will we survive next quarter / Black Friday / marketing campaign". Also: suspected expensive under-utilization (paying for idle hardware).

## Do NOT apply
- < 1 month of prod data (unreliable statistics)
- pre-prod / MVP without realistic traffic
- MVP with manual scaling once per half-year (overhead not justified)
- fully serverless, pay-per-request, no downstream bottlenecks (capacity = money, not resources)
- internal tool with predictable load (10 users, same pattern) — one estimate is enough
- existing corporate capacity-management process exists (use it, don't duplicate)

## Step 1. What to measure
Capacity is multi-dimensional, not just CPU.

| Resource | Measure | Bottleneck signal |
|:---|:---|:---|
| **CPU** | % utilization (avg + p95) | > 70% sustained |
| **Memory** | RSS / heap utilization | > 80% or OOM kills |
| **Network** | bandwidth in/out, connections | > 70% NIC, or port exhaustion |
| **Disk I/O** | IOPS, throughput, queue depth | queue depth growing |
| **Disk space** | free GB + growth rate | < 30 days runway |
| **DB connections** | active / max | > 80% |
| **External rate limits** | requests vs quota | > 70% quota |
| **Latency under load** | p50/p95/p99 vs RPS | p99 grows non-linearly |

Rule: capacity is always multi-dimensional. Autoscaling on a single metric (CPU) is a common error.

## Step 2. Headroom

| Load type | Headroom | Rationale |
|:---|:---:|:---|
| Steady predictable | 30% | minor spike protection |
| Bursty (B2C, retail) | 50-70% | burst can be x3-5 |
| Seasonal (Black Friday, tax period) | 100%+ starting 2 weeks before | don't stretch scaling onto day X |
| Critical (payments, login) | ≥ 50% always | downtime cost > headroom cost |
| Background / batch | 10-20% | non-critical, will restart |

Trade-off: headroom = money. Too much burns budget; too little pages on-call.

## Step 3. Load forecasting
3 horizons:

| Horizon | Method | Sources |
|:---|:---|:---|
| **Tactical** (1-2 weeks) | trend + seasonality from metrics | dashboard + business calendar |
| **Quarterly** | growth rate × current peak | metrics + sales/marketing pipeline |
| **Annual** | business plan + capacity per unit | business plan + per-user resource cost |

Simple model:
```
forecast_peak = current_peak × (1 + monthly_growth)^months × seasonal_factor
required_capacity = forecast_peak × (1 + headroom)
```
`seasonal_factor` for known events (BF, Q4, launches) — from history or conservative x2-x3 estimate.

## Step 4. Autoscaling policy

| Policy | When | Pitfalls |
|:---|:---|:---|
| **Manual** | stable load, small amplitudes | pages on-call on spike |
| **Reactive (HPA on CPU/mem)** | standard B2C | scaling lag + cold start |
| **Predictive scheduled** | known patterns (workday, BF) | useless for unexpected spike |
| **Predictive ML** | large amplitudes, data available | hard to maintain |
| **Hybrid (scheduled + reactive)** | production-grade | hardest to debug |

Autoscaling params — MUST fix:
- Trigger metric (what we measure)
- Threshold (when it fires)
- Cooldown (between scale events)
- Min replicas / max replicas (runaway protection — both down and up)
- Scale-down policy stricter than scale-up (don't flap)

Runaway risks:
- Autoscale without max limit → one bad request = $10K/hr AWS bill
- Autoscale-down on a metric that drops due to incident → cascading failure
- HPA + cluster autoscaler without quota → exhausts availability zone

## Step 5. Cost budget — tied to capacity
Capacity planning without budget is academic.

| Measure | Why |
|:---|:---|
| Cost per request / cost per user | unit economics for PM/founder |
| Cost per service per month | bottom-up budget |
| Cost share idle vs working | headroom efficiency |
| Cost growth rate vs revenue growth rate | business-model health |

Link: capacity_plan → required spend → must fit founder/PM budget. If not → escalate up (business-model decision, not operational).

## Step 6. Pre-event protocol (launch, BF, marketing push)
**2 weeks before** expected spike:
1. **Forecast:** expected peak load x2 of forecast (buffer)
2. **Pre-scale:** raise capacity to forecast level ahead of time (don't trust autoscale on cold start)
3. **Load test:** run synthetic load on realistic data
4. **Failure injection:** chaos engineering on key components
5. **Game day:** tabletop walkthrough of scenarios with team
6. **War room:** at launch — dedicated channel, IC assigned ahead, runbooks ready
7. **Stand-by autoscaling:** max replicas temporarily raised
8. **Post-event review:** actual vs forecast — for next-time calibration

## Agent adds itself
- Concrete forecast formula with current metrics substituted (if provided)
- Autoscaling policy recommendation per stack (Kubernetes HPA / AWS ASG / serverless)
- Link to `observability-design`: which SLO metrics drive capacity decisions
- Link to `incident-response`: capacity-caused incidents → separate classification in postmortem
- "Pre-event readiness" checklist (8 items above — ready checkbox)
- Cost monitoring hint: AWS Cost Explorer / GCP Billing / Datadog Cost Management — choose by stack

## Output file structure `Capacity_Plan.md`
```markdown
# Capacity Plan: [ProjectName] — [Quarter/Year]

## 1. Current load (snapshot 8 each measurement dimensions)
## 2. Bottleneck analysis (where we will rest first)
## 3. Headroom policy (per service)
## 4. Forecast (tactical / quarterly / annual)
## 5. Autoscaling policy (per service)
## 6. Cost budget (current spend + projected)
## 7. Pre-event protocols (for known events - BF, launches)
## 8. Review cadence (how often we review - usually quarterly)
## 9. Open risks / known limits (that we will not be able to scale - for example, monolithic DB)
```

## Hard prohibitions
DO NOT:
- Autoscaling without `max replicas` (runaway cost)
- Capacity planning without cost component (tech-only)
- Forecast based on a single month of data (no seasonality)
- Make a capacity decision that violates SLO (if headroom smaller — flag as risk)
- Predict with ML models without a stable baseline model first (overfitting)
- Pre-event without load test (hope is not a plan)
- Ignore downstream rate limits (scaled own service horizontally → vendor kills us with rate limit)
- Assume serverless = "no capacity problems" (there are: concurrent executions, downstream connections, cost)

## Links
- `architect/observability-design` — source of metrics/SLO/SLI and error budget that capacity decisions build on (prerequisite)
- `laravel-testing/health-checks` — availability monitoring impl (disk/queue/heartbeat), signals for bottleneck analysis
- `operator/incident-response` — capacity incidents classified here; pre-event war room takes roles from here
- `operator/oncall-rotation` — headroom affects page frequency; lack of capacity = on-call burnout
- `operator/runbook` — scale-up as runbook mitigation relies on autoscaling policy from this skill
