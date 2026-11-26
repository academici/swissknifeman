# Optional reviewer selection

Review runs only on an explicit owner request. `--review` requests review on the current native
route; `--reviewer provider/model[/context][/effort]` requests it on the exact selected route.
Without either flag or an explicit review request, use self-check and affected tests only.
Hard risks widen self-checks and support a review recommendation; they do not authorize review.

Parse the selector with `planner.review_selection.reviewer` and command options with
`planner.review_selection.invocation_selection`. Providers: `claude-code`, `codex`, `cursor`, `grok`.
Examples: `codex/gpt-6/high`, `grok/grok-4.7/500k/high/`; `hight` is accepted as `high` for
compatibility. `--effort` (review/audit) or `--review-effort` (execution) must agree with an effort
suffix. Audit defaults to `xhigh`, other explicitly selected reviews to `high`.
Context is required capacity, not a consumption budget; prove it from the actual provider session.
An unknown or insufficient capacity is a route mismatch, never an implicit model substitution.

Keep executor and reviewer sessions separate. Before implementation, resolve an available native
read-only launch on the chosen provider/model/effort. If this session cannot launch it, provide the
exact review handoff and report the pending review; do not claim a verdict. Never substitute another
provider, model or effort. The actual native session establishes route and independence; an owner
selector only declares intent. Reviewers inspect, return findings and stop; only the executor repairs.

## Review intent

| Source | Action |
|:--|:--|
| Command flag `--reviewer` / `--review` | Explicit opt-in, with the command's existing item or scope shape; record the requested review in the plan before running it. |
| Owner message in the session asking for review, in ordinary words or with a selector | Normalize into the plan for unfinished items of this invocation: `plan.py set <plan> <item> --json '{"review":{"mode":"requested","reviewer":{...},"reason":"owner request: <quote>"}}'` (D13), then use the normal path. |
| `item.review.mode: requested` in the plan | Conductor reviews per item when run policy enables it; otherwise it announces `REVIEW_REQUESTED_POLICY_OFF`. Interactive plan-run uses the review-only runner below. |
| None of the above | Self-check plus affected tests. |

## Interactive review runner

Use the orchestrator's review-only runner after GREEN item checks. Build a run-options JSON file
with `reviewer` set to the exact selected `provider/model[/context][/effort]`; keep its path as
`<reviewer-options.json>`. Record the review request in the plan first; there is no unrecorded
run-only review of a plan item. Use the parent of the first implementation commit as `<base>`
(or the pre-implementation HEAD when the implementation is still uncommitted).

```sh
python3 -I .swissknifeman/launcher.py orch input adhoc --review <base>..WORKTREE --plan <plan> --item <item> --goal "<item summary>" > "$TMPDIR/review-<item>.json"
python3 -I .swissknifeman/launcher.py orch conduct run --input "$TMPDIR/review-<item>.json" --options <reviewer-options.json> > "$TMPDIR/review-<item>.result.json"
```

Read only the final JSON line (`run`, `receipt`, `verdict`, `open`, compact `findings`) and the
`review-receipt.json` it names. Raw reviewer streams and transcripts stay in the run directory;
never load them into the owner/executor session. The receipt records the actual reviewer/session
and selector source. Keep that evidence in the
item's artifacts and record its path with `plan.py log --type note`.
The runner performs review and triage once,
without executor work, acceptance commands, correction rounds, advisor or commit. Pass its receipt
to `plan.py finish <plan> <item> … --review-receipt <path>`. A receipt with open confirmed defects
is review evidence, not a claim that those defects were fixed: correct them within the existing
bounded rounds and refresh the receipt for the resulting candidate before closing.

For an automatic owner-requested item review, allow at most `policy.review_rounds_max` completed rounds and
`policy.corrections_max` owning corrections (context pack `policy`, or `plan.py config show`; defaults 2 and 1). Interrupted or cancelled transport is not GREEN and is not a completed round. Reconcile
a running native session before launching another. A local re-review checks findings and changed
dependency closure; a repeated concurrency/transaction/auth/data-integrity class checks the shared
invariant model rather than repeating local patches. Any further round needs a new bounded owner
request. Persist history in plan artifacts/logs; restarting a session never resets the budget.

The former v2 `plan-work` facade, packet/archive machinery and native Grok ACP job runner are not
part of v3. Use the current conductor contracts for candidate-bound receipts; never fabricate receipts or load retired runtime modules.
