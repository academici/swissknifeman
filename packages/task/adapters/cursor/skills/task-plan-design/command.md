<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-design.md
Canonical SHA-256: sha256:4d22e6bf0b011eb659b7bf0cee4f49d73d9af9d90ae826e338e3961261ecd057
Adapter: task.cursor-command/1.0.17
-->
## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ task:` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: economy=composer-2.5-fast, implementation=composer-2.5, frontier=claude-opus-5-thinking-high.

---
disable-model-invocation: true
description: "Explicit Task plan design: author or refine executable plan contracts."
argument-hint: "<PLAN-ID>|new <title>|finish <PLAN-ID> [--review]"
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

Start with `scripts/plan-work.py design-context --plan-dir <dir> --phase <Pn>` for a phase, or
`scripts/plan-work.py design-context --plan-dir <dir> --finish` for the documented finish form.
Use its compact schema and current phase/Routing context; open full canon only for a named ambiguity.
Design creates a v2 plan contract, not a second execution protocol. Read repository evidence,
declare `Phase Assurance | v1` only for an integration seam, hard risk, live/irreversible action,
owner-requested audit, or ambiguous default; omission means isolated/reversible/direct-close.
Declare Routing Batch/Review, Required Reads, Files, Validation and Deliverables, then generate
owned views. Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` as the normal-path vocabulary: focused validation,
selective projections, one semantic Next, and a measured context boundary.
In Validation, name exact acceptance commands that must pass. Add an impact check only with its
trigger (for example, shared schema change); put live checks at the external boundary and keep
diagnostic suggestions outside the blocking acceptance list. An explicitly declared check stays
binding until its contract is transparently changed.

For an existing phase, inspect its item carriers and state before designing. If its items are already
detailed, execution may start for that phase: either detail every phase first (then design finish)
or detail one phase, execute it, and detail the next from the real code. Execution is admitted per
phase; a whole-plan design finish and one `task:plan-audit <ID> design` are required only when
plan.md declares `**Design Audit:** required` or the owner asks for them. “Next/new phase”, item count, local repair, or an ordinary failed check
does not justify design; only new/from-draft scope or a concrete `design-required` contract decision
does.

For `new`/`from-draft` allocate the identity with
`python3 scripts/plan-id.py --codename <NAME>` (it scans `plans/` and `plans/archive/`): use the returned
`plan_id`, `title_prefix` (`Plan №N -`) and `short_id` (`PLAN<N>`) verbatim, never a guessed `№1`/`PLAN1`;
re-run it right before writing the plan directory.

Assign the Short ID and format references according to
`runtime/plan-protocol/references/work-references.md` from the installed Task package
(`PLAN<N>.D35`, `PLAN<N>.P2.3`; legacy: `<PLAN-ID> <local-ID>`).

Design completion records exactly one semantic Next. A bounded remediation does not manufacture a
fresh audit/root; only a concrete context-budget, capability, owner-pause, independent review,
public/authority, or material-risk boundary does. Design-only scope must not execute or spawn
an unauthorized successor. Completion alone does not require a fresh process: use `scope-complete`
and a same-root recommendation; the owner may invoke execution in this session.

Review is opt-in ([review contract](../references/intent-routing.md#review-is-opt-in)): every item Review
is `none` (self-check plus affected tests) and the plan has no `Review Pn` item, even for a hard risk
(name the risk and the `task:review` recommendation in the item's Why instead). Only with `--review` (not
part of the plan title or ID) or an explicit owner request, add one dedicated read-only item (`Review Pn`,
numeric `Pn.m`, Deliverable = verdict file) at the end of the requested scope; slice review items only
when the owner asked for per-slice review. Never write `Independent review` into an item's Validation.
Routing names a minimum semantic class; the Executor/Reviewer cells of the execution sheet are recommended defaults from the provider model
pool, so the owner may swap models inside the pool without editing the plan.

Prefer a few outcome items (normally at most four), at most eight necessary reads per item, and
about 250 lines/2,000 words for an ordinary phase/item contract. These are advisory targets.
When a complex handoff needs more detail, add the implementation dossier, verified retrieval note,
worked examples and raw capture/no-search record described in `design-mode.md`. Link the chosen
carriers from the phase and affected item `Inputs`; finish checks the declared set. An ordinary
local phase needs no empty dossier or no-search ceremony. Search output is supporting data, never
self-verification. Reconciliation is an inline step,
not a separate item without an independent product outcome. After the second owner urgency signal,
stop optional research and complete the smallest sufficient result. Report artifacts and remaining
work, never an unsupported percentage.

Finalize a phase with `scripts/plan-work.py finalize-design --plan-dir <dir> --phase <Pn>
--actor <actor> --session-id <session>`. For `task:plan-design <ID> finish`, use the same command
with `--finish`; it validates any declared supporting artifacts and records a design fingerprint.
After finish, `task:plan-audit <ID> design` (only for `Design Audit: required`/on request) records
an independent GREEN verdict for that exact fingerprint. Use `scripts/plan-work.py design-gate --plan-dir <dir>` to see the allowed transition.
Phase design proposes local groups; finish re-evaluates all phases and dependencies together. Write
the final groups to the `<!-- execution-sheet/v1 -->` table in `roadmap.md`, one exact row per
admission: provider-neutral command, one unified semantic route, and the batch's maximum review.
Use only `economy|implementation|frontier` in Routing, never concrete provider selectors. A batch
launch uses the maximum class/effort and review of its members; the provider adapter then selects one
model for the whole admission. When asked what to execute, copy the command from this execution
sheet; `handoff.md` only points to the current eligible command and must not invent another grouping.
Author the semantic handoff first; before GREEN audit it points to the next design phase, finish,
or design audit. Finalization owns generated views, design journal and receipt; execution start
materializes its selected bundle. Make one focused repair if needed;
a persistent diagnostic is a specific reported conflict, not permission for an unbounded audit.

An applicable terminal-admission lease is a provider adapter concern: design supplies only typed
continuity and delivery carriers, never free-prose terminal authorization.

For new ordinary Routing groups, start with `recommended:`; ready subsets may execute.
Use `required:` for an explicit atomic/owner-mandated group. Historical unmarked groups stay
exact until changed through their existing decision carrier.
