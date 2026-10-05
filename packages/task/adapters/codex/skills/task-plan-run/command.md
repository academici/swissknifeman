<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:ea6da7ab23e0ab9e9d1d9640beed2eddf1db823fd874a7f2aca9e8e561724131
Adapter: task.codex-command/1.0.18
-->
Resolve the installed Task runtime once:

```bash
TASK_CODEX_PLUGIN_ROOT="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')"
```
Use `python3 "$TASK_CODEX_PLUGIN_ROOT/scripts/plan-work.py"` for facade operations.

## Codex execution binding

`plan-work.py prepare` captures `CODEX_THREAD_ID` and provider-written turn_context through
`route_evidence_codex.capture_current`; no route export is needed. Resume and the Codex clear command use the current thread. Proof has source="provider-thread-state" and
source_version="codex-turn-context-v1". The source="cli-flag" compatibility fallback is only
for an attested fresh launch; doctor output/config/actor prose are forbidden substitutes.

At a genuine cold-start-root/owner-requested-new-session boundary, render the receipt's
**Native Codex command:** outside the metadata table:
```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:<command> <arguments>'
```
Use the successor's Routing. scope-complete retains continue-root; report its recommendation
without launching outside owner scope. Same-session completion uses the compact receipt.

Execute `$ARGUMENTS` in the owner-authorized scope. Use the existing `plan-work` facade;
its admission/reducers own route proof, checks, review and closure through `task_contract`. Runtime code is the source
of truth. Load schema, repeat, audit or cross-session references only for a named typed boundary.

1. Call `scripts/plan-work.py prepare --plan-dir <dir> --item <Pn.m> --command plan-run
   --actor <actor> [--session-id <session>]`. For a phase invocation pass `--phase Pn`; for
   multiple items pass the admitted `--request` and returned batch receipt. Pass the owner's
   `--reviewer <provider/model[/context][/effort]> [--review-effort <effort>]` when specified.
   Prepare captures the current provider-attested route and persists its `route-run-receipt/v1`,
   base commit, run context and pre-mutation admission. A stronger class/effort is recorded as
   over; a weaker or unknown route blocks. Do not export another route or reconstruct the contract.
   Consume the selected item capsule. `PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH`
   are errors; open full carriers only for the named ambiguity. Resume reuses the same durable run.
2. Implement the declared scope and acceptance. Run fast affected checks before expensive checks;
   finish generation before checking its outputs. Existing dirty changes retain their ownership.
   For systemic risk, complete the declared invariant-model/self-check. Ordinary low-risk work
   uses self-check and affected tests. Independent review requires an explicit owner request or a
   concrete risk: security/auth, destructive migration, irreversible external action,
   payment/accounting, concurrency/shared state, public API/schema, low-confidence impact,
   or release authority. A risk does not itself authorize a phase audit.
3. Call `plan-work.py validate --plan-dir <dir> --item <Pn.m> --attempt-id <unique-id>`.
   The runtime executes the declared Validation carriers in order, owns candidate-bound logs and
   contract receipts, stops after RED and returns `qualify` or `repair`. Project check definitions
   may add dependencies, environment and timeouts through `--checks`; acceptance carriers remain
   exact. Repair the failure and rerun affected evidence; retain all immutable attempts.
4. Call `plan-work.py close --plan-dir <dir> --item <Pn.m> [--note <result>]`.
   The runtime qualifies live bytes, write sites and required review, builds terminal evidence,
   appends once, regenerates views/continuity, and verifies delivery through `plan_delivery`.
   It returns `complete`, `repair`, or `review-ready`; do not write terminal JSON or Python helpers.
   For `review-ready`, call `plan-work.py review --plan-dir <dir> --item <Pn.m>`. Supported Grok
   transport starts one separate native read-only reviewer session with the exact selected route.
   Keep the candidate stable. Consume the reducer action: GREEN returns to close; FINDINGS means
   an owning fix, affected checks and the next review candidate. No unrequested reviewer or silent
   provider fallback. Other providers use the native independent review/record boundary.
   Use `review-status`, `review-cancel`, or `review-reconcile` with plan/item for an interrupted job;
   never launch another prompt while its outcome is unknown. Active review has no elapsed deadline
   or default turn cap. A cancelled review is not GREEN. Completed-round limits stay in review_policy.

Close each GREEN item in this invocation. Continue dependency-ready items within the admitted scope;
then report the receipt's semantic Next as a recommendation. Do not execute outside that scope.
Use one scoped commit. `finalize` resumes an already appended terminal through the same reducers.
Phase acceptance uses `phase_audit_policy`; an audit requires candidate/run-bound owner consent.
`plan-close` is whole-plan-only. Future-item read-budget/bundle debt is non-gating unless it affects
this item's dependency closure. Full-plan/fleet lint remains a release check.

`task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` is advisory; it grants no authority.
The enabled terminal-admission adapter owns Stop/lease checks. Continue an open authorized run,
honor an explicit owner stop, and retain actual external-wait evidence. A fresh-session/provider
handoff uses the returned typed continuity and native launch; ordinary item transitions need none.
Exceptional repeat and review contracts are in `runtime/plan-protocol/references/` on demand.
Large logs and manifests stay in artifacts; use compact tool results.
