<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-design.md
Canonical SHA-256: sha256:596348032dd0ec0b227dca35acadeb5b430587e382868acfba7b2696c43826bf
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
detailed, continue to the first undetailed phase; after the last phase, run design finish and one
whole-plan design audit. Recommend execution only after that audit is GREEN for the current authored
design. “Next/new phase”, item count, local repair, or an ordinary failed check
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
After finish, `task:plan-audit <ID> design` records an independent GREEN verdict for that exact
fingerprint. Use `scripts/plan-work.py design-gate --plan-dir <dir>` to see the allowed transition.
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

For new ordinary Routing groups, start Почему with `recommended:`; ready subsets may execute.
Use `required:` for an explicit atomic/owner-mandated group. Historical unmarked groups stay
exact until changed through their existing decision carrier.
