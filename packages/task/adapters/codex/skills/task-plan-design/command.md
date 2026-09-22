<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-design.md
Canonical SHA-256: sha256:94ff873887684608d02a5280a1ad5562930cfb7e85c89a450e5d6e93e6ef5140
Adapter: task.codex-command/1.0.16
-->
## Native Codex launch-block — required only at a real user-facing boundary

This generated runtime is the Codex provider projection. Render only the Codex-native launch;
never copy Claude Code slash syntax as the executable invocation and never print both providers.
`$ task:…` is an invocation inside the **current** Codex session, not a fresh launch.
When the typed Context is `continue-root`, keep executing the compatible ready successor within
the owner-authorized scope in this root. If that scope is complete, report the exact successor as a
recommendation for this chat; a final answer does not require a new `codex` process. A command, phase, directory, local repair, or ordinary test failure is not a session
boundary.

At a fresh-session boundary, keep Batch/Model/Thinking/Context/Суть in the metadata table,
but never put the command in a table
cell or column. Immediately after the table print `**Native Codex command:**` and a fenced `bash`
block which explicitly pins the repository cwd, mapped model, reasoning effort, approval policy,
and sandbox:

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:<command> <arguments>'
```

Prefer one physical command line. If intentional formatting uses multiple shell lines, terminate
every continued line except the last with `\`; never rely on Markdown visual wrapping.

**Final-response guard:** continue compatible work inside the admitted owner scope. At an actual
chat stop, include the exact shared receipt recommendation even when no terminal-admission lease
is installed. `scope-complete` retains `continue-root`; it does not authorize the successor or
require a fresh launch. An explicit new-session request updates the persisted decision to
`cold-start-root: owner-requested-new-session` with a fresh post-close checkpoint. Then include the
copyable native Codex block after the metadata table. Waiting continuations retain the exact gate;
never present them as an unconditional command to run now. A completed objective needs no invented
successor. Render only the active provider.

Derive the class and effort from the next item's Routing before rendering it; for `plan-run`,
do not reuse the preceding session's route. Current Codex mapping: economy=gpt-5.6-luna, implementation=gpt-5.6-terra, frontier=gpt-5.6-sol;
low=low, medium=medium, high=high, xhigh=xhigh. At a fresh-session boundary, keep the provider-neutral Next too; its
`$ task:…` form alone or an unpinned `codex` command is not a native fresh launch.

## Codex design route

Use the current provider route once; honor the requested design budget. Design-only Markdown
does not require execution admission, a durable execution start, or a terminal-admission lease.
Use `plan-work.py design-context` and `finalize-design` for compact context and generated carriers.
Do not capture execution route proof or load raw five-carrier snapshots merely to author a phase.
Fixed design routing is frontier/high; diagnose an unrequested cost overshoot before authoring.

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
