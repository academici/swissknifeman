# Review mode

Review is read-only over product work.  Inspect the declared candidate and changed-risk
delta, rank demonstrated findings by impact, and return one owning continuation for each
material defect.  Do not perform product repair, execute a successor, or turn uncertainty
into a new audit cycle.

A plan review item (`Review Pn`) is this same read-only mode scheduled as an ordinary item: it reuses
the executed results of its phase, runs only the checks its Validation names (the one broad pass of
the phase lives here), and writes a verdict file; product repair is the next owning item.

A phase audit additionally requires the existing candidate/run-bound consent contract.
Generated bookkeeping drift may be reconciled only through its deterministic owner and
must not be reported as a product defect.  Fresh evidence is reused; a new audit needs a
new material hypothesis and matching authority.

Read `../SKILL.md` on demand for audit-admission, candidate fingerprint, or whole-plan close
schema details.  Completion is the requested review artifact, not implementation or
release.

## Executor/reviewer handoff

The default is self-check plus affected tests. A dedicated phase/slice review requires an explicit owner request or a concrete risk.
Only an explicit owner requirement adds `owner-review: <provider/model>` to an item's Validation.
The carrier is an acceptance requirement, not permission for unbounded recursive review.
For one-command operation use `task:plan-run <PLAN-ID> <Pn|items> --reviewer <provider/model>`.
It explicitly requires review of every requested implementation item and durably registers that
selection at each prepare (optional `--review-effort`, default high). The root may orchestrate the
bounded transport; the reviewer still executes in its own read-only session. This request never
changes executor routing, grants phase-audit consent or requires rewriting frozen item specifications.
`task:review <PLAN-ID> <Pn.m> [--reviewer <provider/model>] [--effort high]` and
`task:plan-audit <PLAN-ID> <Pn|design> [--reviewer <provider/model>] [--effort xhigh]`
perform the requested review/audit without requiring a selector. Omission inherits the actual
captured native provider/model/effort in a fresh non-executor review session; execution/design
commands without the flag add no external review. An explicit selector names the exact reviewer.
Providers are `claude-code`, `codex`, `cursor`, `grok`; use the full
model ID, not a semantic model class. The current captured route and effort must match, and the
reviewer session must differ from the executor. Native review/audit frontmatter does not pin a
model/effort; compatibility routing minima never replace the explicit selection. A route mismatch
returns a launch for that chosen reviewer.

1. Design names `risk-class: concurrency|transaction|auth|data-integrity` and
   `invariant-model: artifacts/Pn.m/invariant-model.md` in Implementation Rules. Include the model
   in Inputs/Required Reads. Validation names `self-check: artifacts/Pn.m/self-check.json`.
   The model covers affected operations × resources × supported drivers; lock work includes
   acquisition order and pairwise no-cycle arguments, including FK/implicit locks. Data/auth work
   names each invariant, enforcement point and interfering paths. Design review checks missing
   pairs and contradictory rules. Lint checks explicit declarations and the model's existence;
   it cannot prove the model's semantics. Do not add this ceremony to ordinary local work.
2. The executor implements once, runs affected checks and compares all affected paths to the
   model. Its self-check uses `self-check/v1`: `model_sha256`, nonempty `checks` (each has
   `invariant` and `evidence`), and `risks`. Every risk has `risk`, `status` (`fixed|deferred`),
   `evidence`; a deferred risk also has `owner` (accepted D# or declared owning Pn.m) and `reason`.
   Deferral does not waive an acceptance gate. Retain the original test/evidence files.
3. Prepare with `plan-work.py review-packet --plan-dir <dir> --item Pn.m --reviewer grok/grok-4.7
   --executor-session <session> --base <commit> [--evidence <repository-relative log>]`.
   Add adjacent risk paths with `--path`; Files always remain included. The tool writes immutable
   packet.md/review-route.json under `artifacts/Pn.m/owner-review/packet-*/`, digest-binds product,
   spec, model, self-check, explicit evidence and base diff. Pick the pre-implementation base to
   include committed changes; untracked files are included. At most 80,000 UTF-8 bytes are sent.
   Oversized code is replaced by complete repository paths/hashes, never a clipped code section.
   Oversized required model/spec/self-check refuses with a concrete decomposition request.
4. In automatic mode the orchestrating root calls
   `review-run --plan-dir <dir> --manifest <review-route.json> --reviewer grok/grok-4.7`
   for one Grok transport. Native ACP uses `--timeout` as an inactivity timeout (600 seconds
   default), with process/native-route/activity probes every `--heartbeat-interval` (30 seconds).
   Active review has no elapsed deadline. `--max-turns` defaults to 0 (no Task cap); an explicit
   cap is verified against terminal provider usage, never response notification counts.
   Prepare's durable request authorizes this launch from the executor session, not self-review;
   the subprocess has a fresh session and only its provider output can certify the candidate.
   Keep the product stable while it runs. Without automatic selection, persist the existing
   waiting-external checkpoint and exact invocation for a separately requested review deliverable.
   Other providers use an independently routed session and `review-record --plan-dir <dir>
   --manifest <file> --reviewer <provider/model> --output <verdict.json>
   --invocation 'task:review <PLAN-ID> Pn.m --reviewer <provider/model>'`.
   Route is captured from the current provider, never imported from actor prose.
5. The reviewer checks the candidate/model and returns only `review-verdict/v1` JSON:
   `candidate_sha256`, `reviewer`, `verdict` (`GREEN|FINDINGS`), `findings`. Each finding has
   `severity` (`blocker|major|minor|nit`), `risk_class` (`local|concurrency|transaction|auth|data-integrity`),
   stable `area` (subsystem/invariant, shared across files/drivers), `file`, positive `line`,
   demonstrated `scenario` and nonempty `evidence`. GREEN has no findings. Incomplete transport,
   timeout, wrong route/session, stale bytes or invalid JSON is never GREEN.
6. The reviewer ends with its receipt and owning continuation. In automatic mode the root consumes
   it without asking the owner or requiring a second command. The executor resumes one correction,
   reruns only affected checks and prepares the changed candidate. Local re-review checks findings
   plus changed dependency closure; systemic re-review checks the entire affected class/model.
   A second completed round with the same `(risk_class, area)` after repair returns
   `design-required`, even when finding file/fingerprint changed. Establish/revise the common
   model before another local fix; only a new scope/authority choice needs an owner decision.
   The unchanged candidate reuses the verdict. At most two completed rounds per item are admitted;
   incomplete transports consume neither a completed round nor a separate attempt budget. Diagnose
   and repair their cause before retrying; retain receipts and do not start blind retry loops. A real
   stall/cancellation preserves its checkpoint. Completed-round exhaustion retains repair authority
   and requires a bounded owner decision before further completed review rounds. Never
   silently increase the budget, restart it by changing route/candidate, or close with missing
   review. Accepted scope/Validation amendments use existing D# rules; deviations are not a bypass.

One extra completed round can be granted with `review-packet --budget-decision D#`. The accepted,
unsuperseded owner decision targets this item and carries exactly
`[REVIEW-EXTRA-ROUND:Pn.m:<candidate-sha256>:<next-round-number>]`. It admits one candidate/round,
is consumed by that completed receipt, and never resets prior history. Stop or an explicit
Validation amendment are the other owner choices; incomplete evidence can never be waived as GREEN.

Grok uses a fresh session, `--prompt-file` without `-p`, JSON output, read-file/grep/list-dir
tools, explicit shell/edit/write/MCP denies and no nested agents. Permission `plan` alone is not
a read-only boundary. The runner checks end_turn, actual session, complete usage and exact modelUsage;
it archives provider output/stderr separately from the verdict. Hook denials must name their
reason; repair registration/payload defects at harness, never bypass a real authority gate.
Terminal policy admits the owner-review carrier only with the latest complete GREEN verdict bound
to current relevant bytes. Review never closes a phase or grants audit/release authority.
