# Continue-first: repair, block confirmation and delivery receipt

Task considers tool error, route rejection, pending decision and local defect as
surveillance rather than automatic `Blocked`. Durable journal distinguishes four nonterminals
result:

| Result | Meaning | Impact on status/attempt |
|:--|:--|:--|
| `routing-rejected` | current dispatch does not cover Routing | does not affect |
| `decision-pending` | a materialized solution is expected | does not affect |
| `local-repair` | performing limited reversible repair | does not affect |
| `block-candidate` | material hypothesis awaits confirmation | does not affect |

The minor reversible defect is corrected in the current attempt, after which the original Validation is repeated.
A new design pass is not created for this.

## Repair evidence v1

Before checkpoint, block or redesign executor writes closed `repair-decision/v1`. He ties
exact source red carrier, baseline/candidate digest, affected paths with owner item, bounded diff,
all material-surface axes and pre/post validation. `task.plan_repair.evaluate()` is the only one
classifier and returns `repair-in-current-attempt`, `gather-evidence`, `block-candidate` or
`design-required`.

Reversible repair within a matched task continues at product/dependency/test delta
and beyond the suggested threshold for the number of files. Paths retain owner attribution. Public/security/schema
impact requires a proven candidate delta and appropriate verification. Unresolved
frozen/authority/irreversible boundaries require evidence; red baseline does not cancel them.
New result selection/Acceptance with `decision_question`, `evidence_gap`, `alternatives`
and `expected_artifact` require design. The limit of independent audits does not expend the right to repair;
repeating one error without new information requires a change in approach or checkpoint.
`block-candidate/v1` stores the digest repair record and consumes it without its own reclassification.

Terminal close additionally checks the append-only log: each qualified repair remains
incomplete until a later immutable entry with the same item, command and digest of the original
carrier will not record its green in `post_validation`. Therefore, a single focused green cannot
hide non-repeated original check.

## Producer readiness and correction routing

Producer declares a connection with exactly one directive ``producer-readiness/v1``. Terminal decision carries
`producer-readiness/v1`: `nonempty-candidates` binds a positive deterministic set,
and `empty-by-decision` - zero set and one accepted owner decision `D#`. Bundle and downstream
transmit only digest-bound projection to the consumer; valid readiness itself is green
downstream carrier without mandatory shell launch.

`task.plan_readiness.correction_decision()` - the only reducer for continuation: verified output
or approved no-op → `continue-current`; stale/missing → `repair-in-current-attempt`; proven
contract conflict with `phase-reentry-justification/v1` → `reopen-phase`; closed `fix-branch/v1` with
declared target → `priority-fix`. The solution is always nonterminal and is projected into status/returns.
Lint and delivery reject `plan-design` for the terminal phase without exact re-entry evidence. Delivery
also rejects the automatically generated `plan-design` if the phase is already detailed and has
unfinished item: the next step is then `plan-run`, not a repeat expensive design pass.

## Planned protocol without a separate CORE skill

The commands `plan-*` read short general principles and exactly one mode from
`runtime/plan-protocol/references/`: `design-mode.md`, `execution-mode.md` or
`review-mode.md`. The full `runtime/plan-protocol/SKILL.md` remains the canon of the schemes and is readable
as required by a specific part, rather than as a required context for every run.
The generator delivers side by side `references/` and `snippets/`, including template index; `--check`
checks their contents. These files are read as needed and do not add entries to native
skills listing. Installation of a separate `core:plan-protocol` is not required to execute a Task.

## Workset, preparation and terminal reconciliation

The explicitly requested sequence items is one ordered workset. For recommended batch
first ready frontier is allowed with an empty completed prefix; the future consumer is checked after
durable terminal producer, and not before it starts. Batch receipt saves membership/order and follows
via start/terminal events. Therefore, closing one item does not resolve final as long as the receipt contains
unstarted remainder without terminal boundary.

`task.plan_recovery.prepare()` first validates the request, then restores the selected state and
bundle, checks the producer readiness and only after that removes the five-carrier snapshot. If
declaration is unsolvable, response contains `PLAN_BUNDLE_UNRESOLVABLE`, exact entry and command
re-render. Design lint dry-render and announcement of all nonterminal admission-ready items,
but does not save future bundles en masse.

After the terminal journal, `task.plan_reconcile.reconcile_terminal()` is called. Under file
by blocking it rebuilds state/decision/status views, materializes exactly one next ready
bundle, checks freshness and builds delivery receipt. The repeated call is idempotent and does not add
journal rows; stage error remains resumable local repair with
`PLAN_RECONCILIATION_INCOMPLETE`.

## Continue-root without an extra session

After GREEN item executor closes item and ready GREEN phase in current invocation, then
materializes the successor and reads the typed Context. `continue-root` continues compatible ready item
within the scope permitted by the owner. Dirty baseline is saved and compiled; ordinary
repair, item/phase change, generated drift and failed check do not form a context boundary.

If exactly completed scope is ordered, lifecycle `scope-complete` with post-close checkpoint gives
`continue-root` and reason `authorized-scope-complete`. Agent completes response, reports exact Next
as a recommendation for the same chat and does not receive new execution rights. Completion
response does not mean the end of the plan or the mandatory start of a new session.

An explicit owner request for a new start changes the lifecycle to `owner-requested-new-session` and
recalculates typed decision after closure. The resulting `cold-start-root` requires one native
active provider command with current successor. Real context/capability boundary as well
saves the checkpoint. For waiting, the exact condition `# NOT before: `; the team is not
appears to be an unconditional launch now.

Each actual final after closure receives a common fragment from
`plan-delivery.py --plan-dir <plan-dir> --subject <subject> --kind terminal --render-final`.
You can send `--output <receipt>` or check the saved receipt via `--verify <receipt>`.
This works without the optional terminal-admission lease. When lease is set, the tolerance is final
checks the terminal receipt of the current subject; scope-complete and cold-start do not allow closing
unfinished item. The usual active continue-root remains nonterminal.

In Routing there is one execution mode, `Exec=run`; legacy `plan-exec`, `manual` and `plan-run` resolve to it.
The compiler and lint call one `task_contract.resolve_exec`; the raw cell is kept in `declared_exec` and
the digest. Unknown spellings are rejected.

## When Blocked is allowed

Material candidate is serialized as private `block-candidate/v1`. For external RAG problem
is always required: `rag.status=verified` and at least one evidence ID. Then a separate reviewer,
not matching executor, receives only capsule in context `isolated-child-return` and returns
one verdict. Reviewer does not authorize the action; `task.plan_blocking.evaluate()` selects it
deterministically:

| Verdict | Action |
|:--|:--|
| `JUSTIFIED` | allow terminal block |
| `AVOIDABLE` | continue local repair |
| `INSUFFICIENT_EVIDENCE` | collect minimally missing evidence |
| `OUT_OF_SCOPE` / `MALFORMED` | fix capsule and repeat review |

Thus, the unconfirmed suspicion does not color the item and does not pass it to `plan-design`.
Safety and authority gates remain fail-closed: the reviewer only confirms the facts, but does not issue them
right to act.

After the last terminal item, the phase becomes a candidate for closure. Fingerprint
requires explicit Layout v2, binds item specs/state and digest declared `Files`,
but not the general Git HEAD: audit bookkeeping does not invalidate its own proof, but the change
product carrier invalidates. GREEN acceptance allows direct-close by default; legacy
`Audit Intent: required`, integration and number of items do not assign audit themselves. Additional audit
requires targeted owner consent and specific evidence gap associated with candidate and one run
via `audit-admission/v2` in decision record. The new phase-audit start events check this agreement;
historical terminal rows without run ID remain readable, but do not authorize a new run.
Reviewer may end up with audit-attention/audit-red and
`decision.action=return-owning-continuation`, `signal_class=acceptance`, `scope_class=<owning item>`,
`terminal=false`, `recovered=false`, reason_code, evidence_ids and exact exec-items/run-items
continuation for owning item of the same phase. Journal/lint/delivery accepts this result,
but the phase remains open. The contractor repairs, confirms affected acceptance and closes
result without automatic second phase audit. Old authority/block RED outcomes remain readable.

Already green checks are reused while the relevant product/test/tool/config inputs remain unchanged
and surroundings. Lifecycle transition and bookkeeping-only diff do not require product replay;
changed inputs require affected rerun, live check is performed on its live boundary.

## Protection against premature final

After the terminal journal event and recording `handoff.md` commands `plan-run` and `plan-close`
calls `plan-delivery.py --kind terminal`. Receipt binds plan/subject, terminal run ID and
journal pointer, commit, digests plan/handoff/state/closure and exact recommendation from saved
handoff. Non-terminal state returns `FINAL_BEFORE_TERMINAL_FORBIDDEN`; stale handoff -
`HANDOFF_RECOMMENDATION_MISSING` or `STALE_TERMINAL_RECEIPT`.

`plan-run` brings GREEN item to journal/state/closure in the same owner session. After the last
GREEN item delivery also requires a valid phase closure (`PHASE_CLOSURE_REQUIRED` - continue
local close) before giving external Next. `plan-close` current item, restarting it
and audit without admission cannot be such Next. A separate explicitly requested `plan-close` is retained.

`plan-design` and `plan-audit` use `--kind handoff`: this does not state product terminality, but
forces the final response to copy the exact persisted Next. The ending contains a mark
`Next step recommendation: ` and exact `recommendation` receipt.

Package runtime does not see the transport lifecycle of the provider, so heartbeat and check are already
of the sent transcript remain separate adapter/harness seam. Receipt honestly protects
package-owned boundary to `final`, but does not declare an unreachable transport hook.

## Terminal admission lease

An enabled Stop adapter first calls `plan-terminal-admission.py check-open
--project-root <cwd> --provider-session <session>`. This step does not require a lease or special
payload: it checks the latest execution state of the current live session `plans/*/journal.jsonl`.
`in-progress` rejects final with `TASK_OPEN_RUN_FINAL_FORBIDDEN`; intermediate successes are displayed
as progress. Session-bound batch receipt with unstarted balance final does not prohibit: reason
`TASK_WORKSET_REMAINING` gets into the report, and final must name the exact semantic Next. The check does not close the item and does not replace the existing receipt gate.
Real protection requires the Task CLI delivered and the native Stop hook enabled; move run to
new session and full structured waiting handoff require separate binding.

`terminal_admission` adds the repository-owned seam between a Task run and a documented provider
Stop adapter. Its ignored `.swissknifeman/task-terminal/` state binds provider/session, Task
session, plan, subject, command and run ID to one monotonic, expiring lease; turn identity remains
in each event, so a later turn of the same run stays applicable. Concurrent Task runs never replace
each other. `arm` follows run admission;
`refresh` needs a changed progress fingerprint or typed `waiting-owner`; `release` is explicit.
`check` is a total reducer: no matching lease is `NOT_APPLICABLE`, while invalid, stale or ambiguous
applicable state fails closed with a recovery action.

For a terminal decision it requires the exact validated P1.3 `terminal` continuity result that was
last refreshed into the lease, rebuilds the receipt and compares only
`plan_delivery.required_final_message(receipt)` with the in-memory proposed fragment. JSONL events
contain identities, sequence, verdict/reason and SHA-256 values, never raw transcript text. A stale,
released or corrupted lease has the named `re-arm` recovery. This is local deterministic admission
proof; provider payload translation and transport capability claims belong to P4.2.

When interrupted after terminal journal and before state projection delivery returns
`STALE_TERMINAL_RECEIPT`. Repeated `append_idempotent_terminal` does not duplicate the entry;
regeneration via `plan-views state` restores projection. Writer doesn't rewrite
byte-identical file. Checks cannot be declared completed based on the passed list of names.
