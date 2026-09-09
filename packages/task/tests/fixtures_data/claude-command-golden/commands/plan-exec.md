---
description: "Plan protocol: execute plan item(s) Pn.m from plans/ exactly as specified; closure and handoff are mandatory. Pins Sonnet/medium."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
model: sonnet
effort: medium
---
Execute the requested master-plan item. The model/effort are pinned: do not switch them. This
command is self-contained; read `plan-protocol` only when the plan explicitly links to it. Process
multiple items sequentially through the complete cycle below. A Routing batch uses the maximum
member review depth; an individual item uses its `Review` column (`full` by default).

## DecisionRequest and isolated-child-return (P6.3)

Free prose never grants information or authority. Missing facts/authority use `decision-request` v1
through `task.plan_authority.authorize()`: `delegated` executes only the exact action,
`approval_required` materializes `DecisionRequest` with `plan-decisions.py request`, and `denied`
stops. Durable requests carry continuation identity, authority-frame timeout, and
`escalate`/`reject`. Only allowlisted provenance-backed system records may resolve clarification;
then canonicalize and classify intent again.

Judgement uses one provider-neutral `isolated-child-return` for a risk trigger or repeated durable
fingerprint. Root creates `return-judgement` v1, checks capability, and chooses a reviewer distinct
from the executor. No full transcript, unrelated history, self-review, or second sample is allowed.
Missing capability is `cold-start-root: capability-missing`. Use immutable
`return-judgement@1.0.0` at `packages/task/prompts/return-judgement-rubric-v1.md`
(`SHA-256 63323e5565fa2c321354e36ebe47624f37f86c3c3372ba01efaedcc61b6c2e1e`). An uncalibrated
`model_id × rubric_sha256` pair or order-sensitive swap is `INSUFFICIENT_EVIDENCE`.

## Continue-first block gate (v1)

<!-- block-confirmation:v1:begin -->
1. Reproduce the signal minimally and write one immutable `repair-decision/v1` before any block,
   checkpoint stop or redesign. It binds the exact red original carrier, baseline/candidate digests,
   path owner attribution, bounded diff, every material surface, and pre/post validation.
2. `task.plan_repair.evaluate()` is the only repair-versus-design classifier. It returns only
   `repair-in-current-attempt`, `gather-evidence`, `block-candidate`, or `design-required`. A red
   clean baseline without a proved candidate delta, and every bounded all-false material surface,
   is same-attempt repair even outside `Files`; rerun the exact original carrier. Such an action
   cannot mutate terminal status or recommend `plan-design`.
3. `design-required` needs a decision question, evidence gap, alternatives, and expected decision
   artifact. `FIX_REQUIRED`, reviewer agreement, path count, or a red carrier are not a design gate.
4. Only a record reduced to `block-candidate` enters this independent block gate; bind its digest
   into `block-candidate/v1`. The block reducer consumes, and never reclassifies, that repair result.
5. Record nonterminal `local-repair` or `block-candidate`; this does not change `status`/`attempt`.
6. Build immutable `block-candidate/v1` with a material fingerprint, `scope_coverage` and concrete
   `boundary_evidence`. An in-scope `acceptance-failure` returns to local repair. An external
   candidate requires `rag.status=verified` and `rag:perplexity:sha256:<64 lowercase hex>` evidence;
   otherwise record `rag-pending` and gather RAG.
7. One fresh fingerprint gets one distinct `isolated-child-return` reviewer. Reuse its review unless
   the material fingerprint changes.
8. The reviewer applies `block-confirmation-rubric-v1` and returns only
   `reviewer_actor/context/verdict/evidence_ids`; verdict is `JUSTIFIED`, `AVOIDABLE`,
   `INSUFFICIENT_EVIDENCE`, `OUT_OF_SCOPE`, or `MALFORMED`.
9. Root validates it and calls `task.plan_blocking.evaluate()` once. Reviewer evidence is not
   authorization.
10. Only `terminal-block` after distinct `JUSTIFIED` may produce `blocked`/`escalated`; all other
   outcomes continue repair or evidence collection. Never append a terminal event directly.
<!-- block-confirmation:v1:end -->

Before product-journal start, unavailable route evidence is `ROUTE-UNVERIFIABLE` and results in
`routing-rejected`, never an attempt/status transition. Return the exact fresh launch and repeat the
route gate; do not substitute config, actor, or prose.

## Execution cycle

1. **Capture exactly five files, once.** Check `Layout | v2` in `## 0. Meta`; otherwise return
   `PLAN_LAYOUT_V1_RETIRED`. Before exposing any input, capture only `plans/<PLAN-ID>/plan.md`,
   `plans/<PLAN-ID>/phases/<Pn>/<Pn>.md`, `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md`,
   `plans/<PLAN-ID>/bundles/<Pn.m>.json`, and `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md` through
   `task.plan_context.capture()`. Read chunks only from that immutable content-addressed snapshot;
   retain the receipt, byte cursors, and terminal marker for every member. A transport truncation,
   offset gap, absent terminal marker, or live/snapshot digest mismatch is
   `PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH` before product-journal mutation.
   `handoff.md` is not a v2 input and rereading/inventory is forbidden.

2. **Preconditions and routing.** `Home: repo:<path>` is the only execution home. A mirror/Brain
   launch stops with the bare restart command. Accept only `⬜ Not started` or `🟡 In progress`,
   except one accepted D24 recovery with unchanged spec and `allow`; honor `LOOP_BUDGET_EXCEEDED`.
   Enforce phase-first ordering. Read §3 Routing manually, never with regex. Its default matrix is
   `plan-exec = sonnet/medium`. `Exec` is `plan-exec` | `manual` | `plan-design`; an empty Exec is
   derived from `haiku < sonnet < opus ≈ fable` and `low < medium < high < xhigh < max`:
   `model ≤ sonnet` and `effort ≤ medium` means `plan-exec`, otherwise `manual`.
   `Exec = manual` (declared or derived) stops with
   `ROUTING-BLOCKED: Pn.m — required <model/effort>, command pins sonnet/medium`; it changes no
   status. Lower Routing for `Exec = plan-exec` is safe overshoot and is recorded in Known
   Deviations. An explicit `Exec = plan-exec` that contradicts model/effort stops with
   `ROUTING-INCONSISTENT: Pn.m — Exec=plan-exec at <model/effort>` and changes no status.
   `Exec = plan-design` returns for redesign. Ambiguous design/contract routing fails safe; chat
   approval never overrides §3.

   Run the mandatory pre-mutation Task Contract before every mutation:

   ```
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib" python3 - <<'PY'
   import sys
   from task import task_contract, route_evidence
   contract = task_contract.build("plans/<PLAN-ID>", "<Pn.m>", actual_route=route_evidence.capture_actual(
       "<provider-attested model_class>", "<provider-attested effort>",
       source="provider-doctor", model="<provider-attested model>"))
   result = task_contract.evaluate(contract)
   print(result)
   sys.exit(0 if result["pre_mutation"] == "allow" else 1)
   PY
   ```

   Actual route comes only from the provider-attested API. The command selector/actor is not actual
   evidence. Unknown evidence stops before mutation. `ROUTE_UNDERSHOOT` is a real route deficit and
   must have been caught by routing; report `ROUTING-INCONSISTENT`. `ROUTE-UNVERIFIABLE` records
   nonterminal `routing-rejected` and refreshes provider evidence without creating a block. `AUTHORITY_BOUNDARY`,
   `ROUTE-UNVERIFIABLE`, `AUTHORITY_BOUNDARY`, `LOOP_BUDGET_EXCEEDED`,
   `PORTABILITY_EXTERNAL_INPUT`, `PORTABILITY_INPUT_MISSING`, `VERSION_HASH_MISMATCH`,
   `CONFLICT_UNRESOLVED`, `CONFLICT_PRECEDENCE_VIOLATION`, `NEXT_CHANGED_WITHOUT_TRANSITION`,
   `CAPABILITY_UNSUPPORTED`, `SLICE_INCOMPLETE`, and `COLD_START_INCOMPLETE` follow the contract's
   stop/escalation disposition. `ModuleNotFoundError` for `task.task_contract` or
   `task.route_evidence` is fail-closed.

   Before that item contract and before any journal/status mutation, call
   `task.plan_admission.batch_admission(plan_dir, requested_items, receipt=...)`. For a new
   layout-v2 plan its closed allow set is the exact declared Routing Batch, declared `solo`, or
   its digest-bound remaining suffix. `BATCH_REQUIRED`, `BATCH_AMBIGUOUS`, and `BATCH_STALE` print
   the canonical invocation and leave the item untouched; never infer a group from prose.

3. **Start.** Set item and `## Phase Status` to `🟡 In progress`, obtain `session_id` with
   `plan-session.py current --id`, and append the start event with the same `run_id` for the whole
   attempt:

   ```
   run_id = task.journal.derive_run_id(plan_id=plan_id, item_id=item_id, attempt=attempt, session_id=session_id)
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib" python3 -m task.journal append --plan-dir plans/<PLAN-ID>
   --plan <PLAN-ID> --item <Pn.m> --command <plan-exec|plan-run — actual command>
   --actor <model>/<effort> --session-id <session_id> --run-id <run_id> --attempt <N> --result in-progress
   ```

   Missing standalone helpers are warned and skipped. Run
   `python3 -m task.validation_admission --plan-dir plans/<PLAN-ID> --item <Pn.m>` immediately;
   exit `2`/`disposition=local-repair` requires the same-attempt repair, the decision from
   `task.validation_admission.local_repair_decision(report)`, exact `make <target>` admission, and
   a retry. Continue only after `allow`.

4. **Implement only Scope Included.** Rules and Code Guidance are hard limits. Put unrelated ideas
   in **Pending Work**. Handle signals as `observe → minimal reproduce → classify → act → verify`;
   use safe reversible repair/bounded wait for transient or pre-existing failures. Put declared
   reconnaissance in `plans/<PLAN-ID>/findings/<Pn>-<slug>.md`.

5. **Escalate only through the block gate.** Triggers are multi-package refactor, unclear
   architecture, public contract/SemVer, protected generated assets, rule conflict, or unclear
   acceptance. A justified `terminal-block` writes the exact item blockquote, `**Status:** 🔴 Blocked`,
   `**Escalation Needed:** yes`, applicable `Closure Protocol | v1` continuation,
   `handoff.md`, `ESCALATION-REQUIRED: Pn.m — <reason>`, and the terminal journal append using
   `--result escalated --friction escalation --note "<reason, ≤1 line>"`.

6. **Validate.** Run every item `Validation` command and record closed `terminal-evidence/v1` with
   carrier, `green|red`, evidence IDs, and current spec digest. A red carrier keeps the item
   `🟡 In progress`; repair and rerun that carrier. `🟠 Done with deviations` still requires green
   validation plus `recoverable-validation-gap/v1`/`repair_exhausted`. Report a concrete fix and
   launch block for every residual `N−K>0`, foreign diff, defect, or material gap.

7. **Close with two commits.** Re-run Task Contract for both predicates using the same route API:

   ```
   contract = task_contract.build("plans/<PLAN-ID>", "<Pn.m>", actual_route=route_evidence.capture_actual(
       "<provider-attested model_class>", "<provider-attested effort>",
       source="provider-doctor", model="<provider-attested model>"))
   result = task_contract.evaluate(contract)
   ```

   `result["pre_mutation"] == "allow" and result["pre_final"] == "allow"` are required.
   First commit only `Files` paths,
   green package `validate.sh`, and Russian Conventional Commit subject. Then update status,
   factual Completion Notes, `write-site: pre_mutation: <code> · pre_final: <code>`, Pending Work,
   Known Deviations, phase/index/update log/date, terminal journal decision, generated plan views,
   `plan-downstream.py` downstream record (including `unqualifiable`), handoff, and lint. Commit
   plan bookkeeping separately. Never use `git add -A`,
   `git commit -a`, amend, or touch foreign diffs. `🟠` is only material deviation; process deviation
   remains `🟢` but is recorded. Every reported number is `<number> (at <git-ref>)` with its command.

8. **Delivery.** Before final, run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-delivery.py" --plan-dir plans/<PLAN-ID> --subject <Pn.m> --kind terminal`.
   `FINAL_BEFORE_TERMINAL_FORBIDDEN`, stale journal/state/handoff, or a nonzero exit returns to repair;
   do not issue `final` first.
   Final output contains `Delivery receipt: <compact JSON>`, the exact recommendation, status,
   files, commits, validation, lint, foreign diff, deviations/escalation, `Batch`, and a Routing-derived
   launch block. Manual Next uses the bare item prompt or `/model <M>` + `/effort <E>` +
   `/task:plan-run <ID> Pn.m`; terminal phase selection uses
   `task.plan_gates.phase_audit_policy(..., candidate_snapshot=candidate["snapshot"])`:
   `audit-phase: task:plan-audit <PLAN-ID> Pn` or `close: task:plan-close <PLAN-ID> Pn`.
   Context is exactly `continue-root`, `isolated-child-return`, or `cold-start-root`.
   Before persisting it, build `task.plan_continuity.WorkEstimate` from provider-attested
   route/capabilities, context health, the digest-bound remaining batch, loaded-input reuse,
   cold-start cost, lifecycle, and checkpoint; call `task.plan_continuity.reduce()` once and pass
   that same decision to `PlanNextCarrier`. Never let the renderer choose a different context;
   `waiting-owner` emits no runnable successor.
