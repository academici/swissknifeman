---
disable-model-invocation: true
description: "Explicit Task plan design: author or refine executable plan contracts."
argument-hint: "<PLAN-ID>|new <title>|finish <PLAN-ID>"
model: opus
effort: high
---
Invocation payload: `$ARGUMENTS`.

Activate only when the owner explicitly invokes Task. Use the owner's time/research budget as
an execution constraint: inspect only evidence that can change the decision, reuse known findings,
and stop expanding once the implementation choices and acceptance are clear. Audit inventories
are references, not automatic acceptance checklists. Do not impose research quotas or exhaustive
caller/test census. If a hard authority/security boundary cannot fit, report that concrete conflict.

Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/design-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory execution context.

Start with `scripts/plan-work.py design-context --plan-dir <dir> --phase <Pn>` for an existing plan.
Use its compact schema and current phase/Routing context; open full canon only for a named ambiguity.
Design creates a v2 plan contract, not a second execution protocol. Read repository evidence,
declare `Phase Assurance | v1` only for an integration seam, hard risk, live/irreversible action,
owner-requested audit, or ambiguous default; omission means isolated/reversible/direct-close.
Declare Routing Batch/Review, Required Reads, Files, Validation and Deliverables, then generate
owned views. Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` as the normal-path vocabulary: focused validation,
selective projections, one semantic Next, and a measured context boundary.

For an existing phase, inspect its item carriers and state before designing. If its items are already
detailed and an unfinished item is execution-ready, return `task:plan-exec` for that item rather
than redrafting the phase. “Next/new phase”, item count, local repair, or an ordinary failed check
does not justify design; only new/from-draft scope or a concrete `design-required` contract decision
does.

Назначай Short ID и оформляй ссылки по `runtime/plan-protocol/references/work-references.md`
из установленного пакета Task (`PLAN1.D35`, `PLAN1.P2.3`; legacy: `<PLAN-ID> <local-ID>`).

Design completion records exactly one semantic Next. A bounded remediation does not manufacture a
fresh audit/root; only a concrete context-budget, capability, owner-pause, independent review,
public/authority, or material-risk boundary does. Design-only scope must not execute or spawn
an unauthorized successor. Completion alone does not require a fresh process: use `scope-complete`
and a same-root recommendation; the owner may invoke execution in this session.

Prefer a few outcome items (normally at most four), at most eight necessary reads per item, and
about 250 lines/2,000 words per ordinary phase. These are advisory economy targets, not lint gates;
explain a necessary security/public-contract exception briefly. Reconciliation is an inline step,
not a separate item without an independent product outcome. After the second owner urgency signal,
stop optional research and complete the smallest sufficient result. Report artifacts and remaining
work, never an unsupported percentage.

Finalize once with `scripts/plan-work.py finalize-design --plan-dir <dir> --phase <Pn>
--actor <actor> --session-id <session>`. Author the semantic handoff first; this operation owns
generated views, eligible bundles, design journal and receipt. Make one focused repair if needed;
a persistent diagnostic is a specific reported conflict, not permission for an unbounded audit.

An applicable terminal-admission lease is a provider adapter concern: design supplies only typed
continuity and delivery carriers, never free-prose terminal authorization.

For new ordinary Routing groups, start Почему with `recommended:`; ready subsets may execute.
Use `required:` for an explicit atomic/owner-mandated group. Historical unmarked groups stay
exact until changed through their existing decision carrier.
