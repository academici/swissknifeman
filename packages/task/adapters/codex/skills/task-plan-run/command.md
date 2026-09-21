<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:fcec0c67bb951c1d274dc40fed4b2c390f498fa22b22c3f9ae3f02275381b82d
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

## Codex current-route binding — provider-specific

Before the first product-journal mutation, capture the effective route for this exact command:

```bash
export TASK_CODEX_PLUGIN_ROOT="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')"
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH="${TASK_CODEX_PLUGIN_ROOT}/lib:${TASK_CODEX_PLUGIN_ROOT}/../.."   python3 -m task.route_evidence_codex capture   --expected-invocation '$ task:plan-run <arguments>' --expected-cwd <repo-cwd>)"
```

Replace `<arguments>` and `<repo-cwd>` with the exact current invocation payload and repository
cwd. A non-zero exit is `ROUTE-UNVERIFIABLE`; do not start or mutate the product item.

For Codex, `task.route_evidence_codex.capture_current(...)` resolves the current
`CODEX_THREAD_ID` first and validates the latest provider-written `turn_context`: concrete
model, reasoning effort, cwd, approval policy, sandbox policy, and the exact current Task
prompt. The resulting actual-route record carries `source="provider-thread-state"` and
`source_version="codex-turn-context-v1"`.

This path is valid both after a full native launch and after the Codex clear command, which
starts a fresh chat inside the same CLI process. A model or reasoning change before product
journal start is therefore checked from the current chat state, never from stale process argv.
If persisted thread state is genuinely absent, exact ancestor argv remains a compatibility
fallback with `source="cli-flag"`. Malformed/mismatched thread state fails closed; config,
doctor output, actor prose, and self-attestation remain forbidden substitutes.

This provider binding defines how Codex satisfies the D24 write-site checks in the canonical
command below. The projected contract snippets consume exactly
`json.loads(os.environ["TASK_CODEX_ROUTE_EVIDENCE"])`; do not recreate route evidence from
placeholders, `codex doctor`, configuration, or agent prose. Its fresh-native-only wording constrains the `cli-flag` compatibility fallback;
its private-rollout prohibition forbids manual probing but not this validated adapter-owned
read; neither rule prohibits a verified cleared chat or overrides current `turn_context`
evidence.


## Codex snapshot transport guard — provider-specific

Run `task.plan_recovery.prepare()` before analysis, then consume its immutable v2 five-carrier
snapshot. Set both
the nested `exec_command.max_output_tokens` and the outer `// @exec: {"max_output_tokens": ...}`
budget high enough for the current immutable byte chunk; never treat a successful shell exit as a
complete read. Every chunk must retain `snapshot_sha256`, byte `offset`/`next_offset`, and the
terminal marker. A missing terminal marker, a cursor gap, visible transport truncation, or a
live/snapshot digest mismatch is `PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH` before
the product journal starts. Continue only from the same snapshot; never reread a live carrier to
replace a lost chunk.

Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/execution-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory execution context.

Execute `$ARGUMENTS` by the canonical `task:plan-exec` lifecycle. `plan-run` inherits the current
provider-attested route; it never pins model or effort and it never substitutes config or prose for
route evidence. Capture five v2 carriers once, admit the Routing group or ready subset of a recommended group, persist one
`route-run-receipt/v1`, then reuse route/context evidence until `route_change_boundary()` proves change.

After each GREEN item, close the item and any directly closable GREEN phase in this invocation,
then compute Next from the resulting state. Continue a compatible ready successor inside the
owner-authorized admitted scope in this root. Local reversible repair stays in this invocation.
If the owner requested only the completed scope, stop product writes and persist lifecycle
`scope-complete` with its checkpoint: the reducer retains `continue-root` with reason
`authorized-scope-complete`. A chat final reports the successor as a recommendation; it grants no
execution authority and does not require a new process. Never invent work when the objective is done.
An explicit request for a new session updates lifecycle to `owner-requested-new-session`; persist a
fresh post-close checkpoint and render exactly one native launch for that successor. A routine
item/phase transition or test failure does not imply a session boundary. A real external wait keeps
its time/predicate gate visible. Design-only/review-only requests remain separate deliverables.

Activate only for explicit owner plan intent or an exact cited local workflow policy; use the
shared [intent routing canon](../references/intent-routing.md). An exact current owner `plan-run`
is intent to execute the declared item. Before protected writes, an item-declared finite `Authority`
gate may be materialized through `task_contract.materialize_owner_invocation(plan_dir, item_id)`:
the builder captures the live provider user message itself, appends its brief/Decision Log carriers,
and regenerates their bundle. It cannot widen scope, Files, environment or release/fleet authority.
Ungated prose is `AUTHORITY_CONTRACT_GAP`; route metadata or caller-supplied grants never authorize.
Run read-only environment preflight autonomously. A real environment failure records `NO-GO`
with repair evidence and a continuation, rather than repeating an already attested owner question.
Persist external/calendar waits as `waiting-external` with observation start, `resume_at`, evidence
fingerprint, runnable-after predicate and exact continuation in a durable checkpoint. Resume the same
run/evidence chain only after the actual time and predicate evidence; do not restart the observation
or close a production window using a fixture clock. An unchanged finite scope needs no renewed grant.

Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` for transient change-impact selection: focused validation and one
commit are normal; declared hard risk widens validation/review; foreign baseline is non-gating unless
its closure intersects; audit is read-only; only changed projections are generated once; one semantic
Next is rendered by `plan_delivery`. A declared Validation carrier needs current GREEN evidence, not
another run at each lifecycle transition: reuse it while relevant product/test/tool/config inputs and
environment are unchanged, rerun the affected delta after change, and rerun a live check at its live
boundary. Follow the complete close and delivery gates from `plan-exec`.

After GREEN acceptance, persist evidence and the terminal journal event, run
`task.plan_reconcile.reconcile_terminal()` to regenerate and verify changed views,
and close the item in this invocation. If it is the last item of a GREEN phase and no audit is
explicitly admitted by `phase_audit_policy`, create the phase closure in this invocation too. Compute
Next only from that post-closure state and dependencies. Never render a launch for `plan-close` of
this result or for another `plan-run`/`plan-exec` of the current item.

For an installed terminal-admission adapter, arm the lease only after this command's run receipt,
refresh it only after material progress or typed owner-wait, and use its check verdict before a
terminal response. It is repository-owned admission evidence, not a claim that an unconfigured
provider transport is intercepted.

An open durable run is not a response boundary: use commentary for partial progress and continue
the authorized work. Before final, the enabled Stop adapter runs `check-open` against the current
provider session even without a lease/request payload. `TASK_OPEN_RUN_FINAL_FORBIDDEN` requires
continuing or persisting a legitimate terminal block/checkpoint; a green subset of tests is not
an exception. An explicit owner stop remains binding. The check does not itself close any run.

At every actual final after closure, render the shared receipt fragment through worktree-local
`plan-delivery.py --plan-dir <plan-dir> --subject <subject> --kind terminal --render-final`
(or the same command with `--verify <receipt>`). This delivery rule applies even without an optional
terminal-admission lease. A lease controls transport admission, not whether Next is reported.
