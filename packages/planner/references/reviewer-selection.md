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

An owner message in the running session that names a reviewer selector (for example
`reviewer grok/grok-4.7/500k/high`) is the same explicit request as `--reviewer`; it applies to the
items of that invocation that are not finished yet. A reviewer on another provider runs as a headless
child process: build its argv with the `launch` verb of the orchestrator bridge (`plan.py bridge list`)
for role `reviewer`, passing the selector's exact model and effort, never the class mapping; send the
review brief on stdin, keep the stream in a plan artifact and do not hand-edit the argv. The bridge
documents the read-only launch: the reviewer can read everything and run tests and commands, but the
kernel refuses writes to the repository. Prove the route from the reviewer's own
session record, never from the launch: model and effort from its events, context capacity from
`contextWindowTokens` (grok: `~/.grok/sessions/<encoded cwd>/<session>/updates.jsonl`); capacity comes
from the reviewer CLI configuration, and a smaller observed window is a route mismatch. The brief asks
for a reproduction of every finding (failing test or command output); a finding without one is at most
plausible, and the executor confirms or rejects each finding by its own run before any correction.

A requested `plan-run --reviewer` may orchestrate one fresh review per selected item after its checks
pass and before recording completion. This uses native agent sessions and the existing JSON API;
`plan.py` does not launch agents. Record the verdict artifact and its actual reviewer/session in
`plan.py log --type note`. A requested review that has not passed remains pending; do not finish it
as GREEN. `--review` without a selector retains the dedicated review-item shape at the end of scope.
No owner request means no review item and no review launch.

For an automatic owner-requested item review, allow at most two completed rounds and one owning
correction. Interrupted or cancelled transport is not GREEN and is not a completed round. Reconcile
a running native session before launching another. A local re-review checks findings and changed
dependency closure; a repeated concurrency/transaction/auth/data-integrity class checks the shared
invariant model rather than repeating local patches. Any further round needs a new bounded owner
request. Persist history in plan artifacts/logs; restarting a session never resets the budget.

The former v2 `plan-work` facade, packet/archive machinery and native Grok ACP job runner are not
part of v3. Machine check execution, candidate-bound proof and smart orchestration are future work;
do not fabricate those receipts or load retired runtime modules.
