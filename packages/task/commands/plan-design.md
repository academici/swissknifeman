---
description: "Explicit Task plan design: author or refine executable plan contracts."
argument-hint: "<PLAN-ID>|new <title>|finish <PLAN-ID>"
model: opus
effort: high
---
Invocation payload: `$ARGUMENTS`.

Read `runtime/plan-protocol/SKILL.md` from the configured Task package root (the same
root that contains `lib/task/`) before using the plan schema. Its adjacent `references/` and
`snippets/` are delivered on demand with Task; a separate CORE skill is not required.

Design creates a v2 plan contract, not a second execution protocol. Read repository evidence,
declare `Phase Assurance | v1` in every new phase (impact, named seams, live/irreversible,
audit intent, rationale), Routing Batch/Review, Required Reads, Files, Validation and Deliverables, then generate
owned views. Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` as the normal-path vocabulary: focused validation,
selective projections, one semantic Next, and a measured context boundary.

For an existing phase, inspect its item carriers and state before designing. If its items are already
detailed and an unfinished item is execution-ready, return `task:plan-exec` for that item rather
than redrafting the phase. “Next/new phase”, item count, local repair, or an ordinary failed check
does not justify design; only new/from-draft scope or a concrete `design-required` contract decision
does.

внешняя ссылка на item использует `<PLAN-ID> Pn.m`; голый `Pn.m` допустим только внутри самого плана.

Design completion records exactly one semantic Next. A bounded remediation does not manufacture a
fresh audit/root; only a concrete context-budget, capability, owner-pause, independent review,
public/authority, or material-risk boundary does. `DESIGN-ROOT-TERMINAL` remains a design-result
handoff boundary: it must not execute or spawn a successor in the same design invocation.

An applicable terminal-admission lease is a provider adapter concern: design supplies only typed
continuity and delivery carriers, never free-prose terminal authorization.

For new ordinary Routing groups, start Почему with `recommended:`; ready subsets may execute.
Use `required:` for an explicit atomic/owner-mandated group. Historical unmarked groups stay
exact until changed through their existing decision carrier.
