---
name: task-development-philosophy
bucket: repository-bootstrap
version: 0.1.0
description: "Guardrails for keeping Task plans flexible, proportional, and loop-free. Activate before creating or revising a plan in this repository or changing packages/task planning, validation, audit, close, retry, or budget policy."
when_to_use: "Use for swissknifeman plan authoring and Task workflow-policy changes."
risk: read
persona: architect
tags: [task, philosophy, planning, proportionality, evidence-reuse, anti-loop, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Task development philosophy

Treat this skill as the constitutional context for developing `packages/task` and authoring
executable plans in this repository. Read it before designing a new plan or changing Task workflow
policy. Apply its principles through proportional decisions; do not turn every sentence into a new
schema field or gate.

## Purpose

`task` is a lightweight control layer for turning work that is too large for one reliable agent
run into bounded, independently understandable slices. It supplies routing, durable handoff,
validation ownership, review, and recovery tools so agents can keep delivering with little owner
coordination.

The package is successful when it makes substantial work faster and calmer:

- a large objective becomes a short sequence of coherent vertical outcomes;
- every item can be resumed from committed context after a session loss;
- the agent has enough freedom to repair ordinary defects without redesign or owner interruption;
- validation effort follows changed risk and reuses trustworthy evidence;
- audit catches integration and deception risks without re-executing the plan by default;
- terminal boundaries are rare, concrete, and genuinely outside the current authority or scope.

The package is not a formal-verification system, a replacement for engineering judgement, or a
promise that no defect can escape. Optimize for bounded confidence and development throughput, not
perfect certainty at unbounded cost.

## Core balance

Hold these values together. None may erase the others.

1. **Flow.** Prefer the shortest safe path from intent to a working, validated outcome.
2. **Decomposition.** Split by independently valuable and verifiable vertical results, not by
   layers of ceremony or by every file touched.
3. **Autonomy.** Let the owning agent resolve local, reversible, in-scope uncertainty. Ask the
   owner only for authority, irreversible choices, or a real product decision.
4. **Evidence.** Persist enough provenance to resume and trust work, but treat generated paperwork
   as support for delivery, not as the product itself.
5. **Proportionality.** Spend review, tests, tokens, and wall time in proportion to changed impact.
   Cost is an engineering constraint and therefore part of correctness.
6. **Escape.** Every loop must have a bounded exit: reuse evidence, narrow to a delta, repair the
   owning seam, or request one explicit decision. Never normalize endless audit/repair cycles.

## Plan-authoring rules

Before writing a new plan, establish:

- the smallest owner-visible outcome that justifies a plan rather than a direct task;
- phase boundaries that correspond to integration milestones;
- item boundaries that can be implemented and validated without reading the whole plan;
- the owner of each invariant and generated carrier;
- which validations are deterministic and reusable, which are integration checks, and which must
  remain live;
- a dependency graph sufficient to calculate affected downstream items;
- explicit stop conditions and a bounded audit/retry budget;
- what is deliberately not optimized or perfected in this plan.

Keep plans detailed enough for cold start, but do not make every item repeat the phase context.
Prefer a small number of meaningful items over artificial micro-items, and prefer a new phase only
when it creates a real integration or authority boundary.

Do not prebuild speculative machinery. Record an unmeasured idea in `roadmap/` with a trigger. Turn
it into plan scope only after the trigger occurs or the owner explicitly prioritizes it.

## Validation economy

Use the cheapest evidence that can falsify the current risk:

```text
static/structural check
  → affected unit or artifact test
  → changed-item validation
  → dependency-closure integration check
  → full phase audit only when broad material impact is demonstrated
```

Item close owns item-level Validation. Persist a digest-bound receipt so later consumers can prove
whether inputs, product, tool, route, and result are unchanged. Audit must verify those receipts and
rerun invalid or risk-sensitive checks; it must not mechanically replay every green command.

Run one full audit for a material phase baseline. After that:

- protocol/bookkeeping-only change → gate rebind;
- bounded product change → changed items plus dependency closure;
- broad or unbounded material change → justified second full audit;
- third full audit in one lineage → explicit owner decision.

Historical `Done with deviations`, regenerated views, a journal append, a line-number drift, or an
expired live receipt are not by themselves reasons to replay the whole phase. Rerun the exact live
gate at its boundary; keep deterministic product evidence reusable.

For the measured repeat-audit contract and thresholds, read
[`roadmap/2026.08.14-repeat-audit-evidence-reuse-budget.md`](../../../../../roadmap/2026.08.14-repeat-audit-evidence-reuse-budget.md)
when changing audit policy. For evidence-anchor topology, also read
[`roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md`](../../../../../roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md).

## Repair and escalation

Continue first for local, reversible, in-scope failures. Repair the owning seam, rerun only its
affected validation, and continue the same objective. Do not convert ordinary test failures,
generated drift, missing bookkeeping, route noise, or a large file count into redesign.

Escalate only when the next action needs authority the agent does not have, changes a frozen/public
contract beyond scope, performs an irreversible or external action, or remains genuinely unbounded
after one concrete decomposition attempt. A reducer may confirm the boundary; prose such as
"complex" or "safer to revisit" may not.

When a machine gate conflicts with this philosophy, obey the current gate, preserve evidence, and
record the measured mismatch at its owning source or in `roadmap/`. Do not silently bypass the gate,
and do not describe the resulting overhead as successful policy.

## Audit role

Audit is an adversarial integration review, not a second executor.

Audit should answer:

- Did the committed product satisfy the intended phase outcome?
- Are scope, authority, public contracts, security, and integration seams honest?
- Can the next phase trust the evidence and handoff?
- What changed since the last trusted baseline?

Audit should not optimize for finding any possible nit, restate every item report, or rerun work
whose inputs and receipts are unchanged. Non-gating observations remain visible without forcing
RED. A safe finding is repaired once at its owner; repeated symptoms from one seam are grouped and
the seam is fixed.

## Anti-patterns

Reject these designs:

- a plan whose main output is more planning machinery;
- horizontal decomposition that produces no independently usable outcome;
- permanent full-review triggers based only on historical status;
- repeated audits with no new material hypothesis;
- validation that ignores reusable item evidence and always starts from zero;
- generated audit bookkeeping included in the material candidate it must certify;
- a remediation item per symptom when one shared seam caused them;
- owner interruption for choices already bounded by scope and reversible implementation;
- safety language used to justify unlimited cost without a concrete failure scenario;
- gates that make the valid path impossible and then blame execution for looping.

## Decision test

Before adding a Task rule, gate, carrier, or mandatory pass, answer:

1. What measured failure does it prevent?
2. Who owns the invariant?
3. What is the cheapest deterministic enforcement point?
4. Can existing evidence prove it without another execution?
5. What is its wall-time, token, and cognitive cost on the normal path?
6. How does an agent recover when it fires?
7. What prevents it from creating a self-sustaining loop?
8. When can the rule be removed or simplified?

If the failure is unmeasured, use roadmap. If the enforcement is more expensive than the plausible
damage and does not protect security, irreversible data, or a public contract, prefer a warning,
targeted test, or review checklist. If there is no bounded recovery path, redesign the rule before
shipping it.

## Plan-design checkpoint

For every new or materially revised plan in this repository, silently verify before handoff:

- each item is a meaningful vertical unit;
- repeated reads and validations are not copied without an ownership reason;
- the plan names the minimum sufficient audit depth and evidence-reuse boundary;
- a second full audit requires a material-change justification;
- local repairs remain same-root and do not manufacture redesign loops;
- no generated carrier is accidentally both audit bookkeeping and self-invalidating product;
- owner-visible value dominates orchestration overhead.

Record a decision or `## Обсуждение` only when a real trade-off exists. Do not add boilerplate
"philosophy compliance" sections to every plan.

## Provenance (root-bootstrap, P1.2)

Repository-authored internal philosophy, grounded in field regressions captured in
`roadmap/2026.08.10-plan-evidence-anchor-audit-loop.md` and
`roadmap/2026.08.14-repeat-audit-evidence-reuse-budget.md`. It is source-only and projects to thin
Claude/Codex root-bootstrap pointers through `skiller registry`; it is not published to consumer
projects as an ordinary skill.
