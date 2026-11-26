---
name: agent-design
description: "Design or audit an agent loop, tool boundary, autonomy policy, or recovery behavior."
---

# Agent Design

Use when building or auditing an agent system. The project's authorized use case and risk
model define autonomy; this skill does not reduce an already authorized coding session to
approval-before-every-step or demand a BRD before a bounded repair.

## Loop and tool contract

The model proposes actions; the harness validates parameters, enforces actual permissions,
executes tools, and records outcomes. Define:

- Tool names/schemas, timeouts, bounded outputs, and a result correlated with each call,
  including failures and refusals. Streaming/progress events follow the provider protocol.
- Trust boundaries: imported pages, memory, files, and tool output are data, not authority.
  Keep credentials outside model context; grant only capabilities needed for the task.
- A measurable done condition and next-action decision. Continue useful authorized work;
  checkpoint on a real resource/context boundary; stop when the objective is achieved.
- Structured failures and recovery: distinguish denied, invalid, transient, uncertain-effect,
  and terminal outcomes. Do not disguise retries to bypass a permission denial.

## Autonomy and concurrency

Select permissions by action, resource, reversibility, user intent, and adopted policy. Read
and reversible local changes commonly proceed within existing authority; external sends,
financial effects, and destructive operations require the authority appropriate to their
actual impact. A prior explicit authorization remains valid. Use preview/commit or separate
confirmation when the product's risk or transaction scope requires it, not as a blanket
second approval for all multistep work.

Parallelize independent operations only when their resources and side effects are isolated.
Writes to separate owned outputs can be independent; conflicting writers, dependent commits,
shared-state mutations, or order-sensitive sends must serialize. For uncertain outcomes of
non-idempotent effects, inspect receipts/state before retrying. Cancellation does not prove
an effect was rolled back.

## Bound resource use

Choose enforced limits sufficient to bound the actual loop: steps, tokens, time, cost, output
size, or resource-specific quotas. Four separate counters are not obligatory when an existing
bound covers the risk. Record which controls are enforced and which telemetry is unavailable;
do not imply an unmeasured cost or context budget is safe.

Keep stable cacheable prefixes where the provider supports them. Compact/history handling
must preserve decisions, authorization, outstanding work, and tool/result coherence; cache
optimization never forbids necessary context repair.

## Verification and delivery

Test harness policy enforcement independently from model behavior. Include relevant negative
cases: prompt injection, authority bypass, oversized output, expired context, invalid tool
input, concurrent writes, cancellation, and duplicate external effects. Use representative
model evals for task completion and unnecessary approvals/restarts; deterministic harness
tests alone cannot prove model behavior. Record traces without secrets or private reasoning.

Choose rollout/checkpoints by failure impact and observed reliability. A limited release or
shadow run may be appropriate; a fixed ladder of autonomy levels is not a required ceremony.
Keep design-only work bounded and distinguish source checks from live provider evidence.

See [loop sketch](snippets/agentic-loop.md) and [tool contract](snippets/tool-contract.md).
Use `architect/eval-design` or `architect/observability-design` for substantive decisions in
those areas, not as mandatory documents on every change.
