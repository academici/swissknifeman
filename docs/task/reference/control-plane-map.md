# Task: what is a rule and what is calculated

Task is enabled only by an explicit owner command. The normal fix lives in the Git diff and passes the affected checks without plan carriers. This map is needed to accompany an explicitly included plan: when changing a rule, first look for the source of truth, then its consumers. The number of modules alone does not indicate whether a new step is needed for the agent.

## Dictionary for performer

| Term | What does it mean here | What to do with it |
|---|---|---|
| Carrier | File with a specific role in the plan: author's contract, history, derivative view or transfer | First set the class according to the table below; do not consider any file a new source of truth |
| Admission/gate | Checking the validity of a specific transition, for example design → start | Read the `code` failure and correct the specified input; gate does not execute item for agent |
| Authority | The right to act with this effect | Check at the entry/publication boundary; a successful route or test does not create a privilege |
| Route evidence | Evidence of actually running provider/model/effort for the call | Check against declared semantic Routing; entry in the plan does not prove actual launch |
| Snapshot/fingerprint | Snapshot of selected inputs and its hash | After changing the design file, the old audit is not transferred to the new fingerprint |
| Bundle | Restored set of inputs of the selected item | Build at start item; do not create all bundles on design |
| Projection/view | Derived status, state or receipt | Rebuild by the owner of the writer from the original data; do not manually correct as contract |
| Journal event | Append-only fact about transition or result | Don't rewrite the old line; damaged history repair supported forward repair |
| Reconcile/terminal | Reducing evidence to a closing outcome item | Close only after actually completed announced checks |
| Baseline lint | Snapshot of already known errors outside the editable phase | Doesn't hide a new error or turn an old error into a resolution to a generic finish |

On the normal path, the agent only needs the selected item spec and its inputs: `prepare` returns the context, then the agent changes the product, performs the declared checks and closes the item. The terms above are needed to explain the failure or change of a Task, and not as a list of manual operations for each fix.

## One way from design to execution

| Step | Source of Truth | Check | Effect |
|---|---|---|---|
| Design phases | `plan.md`, `phases/Pn/Pn.md`, `phases/Pn/Pn.m.md`, owner decisions | Phase parser, local diagnostics | Only original carriers change |
| Finish the entire plan (optional) | All announced phases + `roadmap.md` | Full lint, coverage, Routing/execution sheet | `plan-design` event `item_id=finish` with fingerprint of source design files |
| General design audit (only `**Design Audit:** required` or upon request) | Same fingerprint, independent assessment of the whole plan | `plan-work.py design-gate`; journal append checks fingerprint and presence of finish | `plan-audit` event `item_id=design`; with `required` only `audit-green` opens execution |
| Start item | Selected Routing group and route evidence of current call | `plan_work.prepare` / `plan_recovery.start`: phase and item detailed (phase-scoped gate), authority, dependencies, bundle inputs | One durable start; bundle materializes for the selected item |
| Closure | Real validation/evidence and terminal decision | `task_contract`, `terminal_policy`, `plan_reconcile` | One terminal journal event, then update views |

By default, gate phase-scoped: execution requires detailed phases and items, not the entire plan; the remaining phases can remain skeleton/backlog. Strict whole-plan mode (finish + GREEN audit by fingerprint) is enabled by the line `**Design Audit:** required` in `plan.md`; it is described below. Plans with `execution-sheet/v1` use design gate now. For plans with a date from 2026-09-24, the gate is valid without a marker, so it cannot be circumvented by deleting the line from the new plan. Plans 2026-09-22, which began execution before this change and do not have a marker, remain on the same path; marker in the old plan means the conscious inclusion of a new contract. As long as at least one declared phase remains skeleton, `plan-run` is typed refusal. After fixing the design, you need to run finish and audit again on the new fingerprint. `Next` itself does not give the right to start.

## Data classes

| Class | Specific media | Consequence of absence |
|---|---|---|
| Author's contract | `plan.md`, phase indices, item specs, `roadmap.md`, decisions made | You can't prove scope, dependency, or route; corrected by the author |
| Durable history | `journal.jsonl` | You cannot assert start, finish, audit GREEN or terminal outcome; not restored from prose |
| External proof | Provider route/authority, owner grant, live validation | Cannot be made from local cache; requested from the source at the appropriate boundary |
| Recoverable view | `status.md`, item states, decision views, bundles | Rebuilt by deterministic owner writer; stale view does not become the new rule |
| Transmission/diagnostics | Handoff receipt, context snapshot, diagnostic baseline | Links a specific pass or attempt; its absence should not create a new product scope |

Optional design dossier (`research/Pn-design.md`, verified retrieval note, examples, capture/no-search record) appears only when a compact contract is not enough for a fresh performer. If dossier is declared, finish checks the set and references. Don't create four empty files per normal phase. Changing the selected dossier after the GREEN audit changes the design fingerprint.

## Owners of invariants

| Invariant | Solution Owner | Consumers |
|---|---|---|
| Valid item, group and semantic route | `task_contract` + declared Routing | `plan_admission`, `plan_work`, provider adapter |
| Priority producer → consumer | `plan_recovery` and `plan_readiness` | start, handoff, lint |
| Completeness of design and relevance of the general audit | `plan_readiness.design_snapshot/design_gate` + journal event | `plan_work.prepare`, `plan_recovery.start`, `plan_delivery` |
| Write and close authority | `task_contract`, `terminal_policy` | start, reconcile, delivery |
| Proven terminal outcome | `journal` | item state, status, receipt, downstream |
| Byte-fresh generated file | `plan_projection` + writer of a specific type | lint, context snapshot, delivery |

`plan_delivery` represents a valid continuation and checks for handoff. It must not infer a new legal transition from the free text `Next`. `command_render` represents the provider command; he should not come up with another Routing. `plan_weight` measures reads/context, but does not own authority. If two modules independently solve one of the invariants, first eliminate this duplication; moving files for the sake of fewer modules is not the goal.

## Where to look in case of failure

0. `PLAN_DESIGN_INCOMPLETE` in phase-scoped mode refers to the launch phase/item: detail it (`task:plan-design <ID> Pn`). Points 2–4 only apply if `Design Audit: required`.
1. `PLAN_DESIGN_INCOMPLETE`: check declared phases, skeleton marker, required item spec fields and open clarification.
2. `PLAN_DESIGN_FINISH_MISSING`: execute `finalize-design --finish` on current authorized carriers; it doesn't execute item.
3. `PLAN_DESIGN_AUDIT_MISSING` or `PLAN_DESIGN_AUDIT_NOT_GREEN`: check the latest design audit in the journal and correct its comments.
4. `PLAN_DESIGN_AUDIT_STALE`: compare fingerprint from `plan-work.py design-gate --plan-dir <dir>` with the last audit event; changing the authoring file requires a new finish/audit.
5. `PLAN_JOURNAL_INVALID`: there is a line outside the scheme in the append-only history; determine its source and apply a supported forward repair or historical exception. Do not silently edit the line and do not accept it as GREEN.
6. After GREEN, check the local route, authority, producer readiness and bundle. Do not rerun the general design audit due to a normal item test failure.

## Cost check

`plan-work.py` outputs diagnostic `metrics.wall_ms` and `metrics.payload_bytes` for each call. `payload_bytes` reads JSON before adding the metrics block itself; this is the size of the returned context, not the number of provider tokens. For local design, separately count the number of full lint calls and recorded bundles. For item start, consider captures, journal scans, state/bundle writes and affected validation runs. Measure the same short and long plan before/after the change. The exact provider tokens and monetary value are only available with a real provider receipt; do not infer them from the local file size. Cache or persistent index is only justified after a profile that shows repeated work on unchanged inputs.
