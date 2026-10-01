# 4 pillar observability

Skill reference `observability-design`.


### 1. Logs
**What:** structured events with context.
**Solutions:**
- Levels: ERROR / WARN / INFO / DEBUG — when to write what
- Format: JSON with diagram (timestamp, level, service, trace_id, user_id, message, attrs)
- Where: stdout → aggregator (Loki / CloudWatch / Datadog / Better Stack)
- Retention: hot (7d) / warm (30d) / cold (1y by compliance)
- PII in the logs: **deny** or **mandatory masking** (see `security-design`)

### 2. Metrics
**What:** aggregated numbers over time.
**Categories:**
- **RED** (for request-driven): Rate, Errors, Duration — per endpoint
- **USE** (for resources): Utilization, Saturation, Errors — on CPU/RAM/disk/network/DB-pool
- **Business KPI**: MRR, active users, conversion - separate dashboard
- **Custom domain**: for AI-projects - token usage, latency per model, hallucination rate (see `eval-design`)

### 3. Traces
**What:** path of one request through all components.
**Solutions:**
- Standard: OpenTelemetry (default)
- Sampling: head-based (1–10%) or tail-based (100% errors, 1% success)
- What to trace: incoming HTTP, outgoing HTTP, DB queries, queue messages, LLM-calls
- Trace_id propagation: through everything service-boundaries (including background jobs)

### 4. Alerts
**What:** automatic degradation signals.
**Principles:**
- Alert = action required. If there is no action, it’s not an alert, it’s a dashboard.
- Severity tiers: P1 (paging, 24/7) / P2 (working hours) / P3 (ticket)
- To each alert - runbook (see below)
- Deny flaky alerts: after the 3rd false positive - redo or delete

---
