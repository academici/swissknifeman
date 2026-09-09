<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:e3a0cbcf68bb567a661d729e2499cf8b921a2a4e37c3f63b16e131578dbe484a
Adapter: task.codex-command/1.0.11
-->
## Native Codex launch-block — mandatory for every executable handoff

This generated runtime is the Codex provider projection. Render only the Codex-native launch;
never copy Claude Code slash syntax as the executable invocation and never print both providers.
`$ task:…` is an invocation inside the **current** Codex session, not a fresh launch.

Keep Batch/Model/Thinking/Context/Суть in the metadata table, but never put the command in a table
cell or column. Immediately after the table print `**Native Codex command:**` and a fenced `bash`
block which explicitly pins the repository cwd, mapped model, reasoning effort, approval policy,
and sandbox:

```bash
codex -C <repo-cwd> -m <model-selector> -c 'model_reasoning_effort="<effort-selector>"' -a never -s danger-full-access '$ task:<command> <arguments>'
```

Prefer one physical command line. If intentional formatting uses multiple shell lines, terminate
every continued line except the last with `\`; never rely on Markdown visual wrapping.

**Final-response guard:** when an executable Next exists, do not stop after a completion summary,
`Delivery receipt`, or `PHASE-CLOSED`. Before final, verify that the copyable native Codex `bash`
block is present after the metadata table. Only a genuinely terminal Next with no executable
successor may omit it.

Derive the class and effort from the next item's Routing before rendering it; for `plan-run`,
do not reuse the preceding session's route. Current Codex mapping: economy=gpt-5.6-luna, implementation=gpt-5.6-terra, frontier=gpt-5.6-sol;
low=low, medium=medium, high=high, xhigh=xhigh. Keep the provider-neutral launch-block too, but never hand off only
`$ task:…` or an unpinned `codex` command.

## Codex current-route binding — provider-specific

Before the first product-journal mutation, capture the effective route for this exact command:

```bash
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib"   python3 -m task.route_evidence_codex capture   --expected-invocation '$ task:plan-run <arguments>' --expected-cwd <repo-cwd>)"
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

Capture the v2 five-carrier context before analysis with `task.plan_context.capture()`. Set both
the nested `exec_command.max_output_tokens` and the outer `// @exec: {"max_output_tokens": ...}`
budget high enough for the current immutable byte chunk; never treat a successful shell exit as a
complete read. Every chunk must retain `snapshot_sha256`, byte `offset`/`next_offset`, and the
terminal marker. A missing terminal marker, a cursor gap, visible transport truncation, or a
live/snapshot digest mismatch is `PLAN_CONTEXT_TRUNCATED`/`PLAN_CONTEXT_DIGEST_MISMATCH` before
the product journal starts. Continue only from the same snapshot; never reread a live carrier to
replace a lost chunk.

Execute the master-plan item with the owner's current session route (D18); this is the third
`plan-exec` mode and has no fixed `model`/`effort`. Input: `$ARGUMENTS`.

## Inherited execution contract

Use the `DecisionRequest`, `isolated-child-return`, and `block-confirmation:v1` rules from
`task:plan-exec` unchanged. In particular, free prose is never authorization; only the closed
`delegated`/`approval_required`/`denied` result from `task.plan_authority.authorize()` is valid;
review is one fresh distinct `isolated-child-return`; and only a distinct `JUSTIFIED` result may
lead through `task.plan_blocking.evaluate()` to `terminal-block`.

The inherited **Continue-first block gate (v1)** keeps `local-repair`, `block-candidate`,
`routing-rejected`, and `ROUTE-UNVERIFIABLE`; the latter is never an attempt/status transition.

Read the v2 five-slot item path only: `plans/<PLAN-ID>/plan.md`,
`plans/<PLAN-ID>/phases/<Pn>/<Pn>.md`, `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md`,
`plans/<PLAN-ID>/bundles/<Pn.m>.json`, and `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md`.
`Layout | v2` is mandatory; otherwise return `PLAN_LAYOUT_V1_RETIRED`. Capture these five members
once through `task.plan_context.capture()` before exposing their content; consume byte chunks only
from its immutable snapshot and require its receipt, contiguous cursors, and terminal marker before
product-journal mutation. `PLAN_CONTEXT_TRUNCATED` or `PLAN_CONTEXT_DIGEST_MISMATCH` stops before
an attempt/status transition. Do not use or reread `handoff.md`.

Resolve and read the canonical `task:plan-exec` source through
`task.command_catalog.package_command_path("task:plan-exec")`; execute its steps 1–8 exactly,
with these three differences:

- Current-session model/effort are inherited, never pinned.
- At pre-mutation and pre-final use
  `task.route_evidence.capture_launch(expected_invocation="task:plan-run <arguments>", expected_cwd="<repo-cwd>")`.
  The provider is selected from session identity and only an additive adapter reads raw state. Codex adapter
  verifies native `-C`, `-m`, effort, `-a never`, and `-s danger-full-access` and binds `cli-flag`
  provenance to the owning thread. Claude Code adapter reads only current `CLAUDE_CODE_SESSION_ID`, exact
  `<command-name>` + `<command-args>`, and the following route-bearing assistant event. No config,
  actor, handoff prose, or self-attestation fallback is valid. `ROUTE_LAUNCH_UNAVAILABLE`,
  `ROUTE_LAUNCH_MISMATCH`, or any unknown axis is `ROUTE-UNVERIFIABLE`: return a fresh launch
  before product-journal start.

  Build `route-run-receipt/v1` with `task.route_evidence.build_run_receipt(...)`, use
  `task.route_evidence.start_decision(receipt)` in the `in-progress` record, and before terminal
  append reload it by `run_id`, capture fresh evidence, and call
  `verify_run_receipt(..., current_evidence=<fresh>)`. Any model/effort/thread/cwd/invocation
  mismatch or expired receipt requires a fresh dispatch; a route change never gets a new receipt.
- The routing gate compares launch provenance with §3 Routing. Undershoot appends the non-transition
  provenance event `--result routing-rejected --friction routing-blocked`, prints the exact provider
  launch block, and stops only the dispatch. Overshoot executes and is recorded in Known Deviations.
  `Exec = plan-design` stops for redesign. Route correction never creates `blocked|escalated`.

Codex `cli-flag` proves a fresh native launch; Claude Code `provider-thread-state` proves the
route-bearing event. Both feed one provider-neutral record contract; no canonical command reads
provider-private state.

Every inherited journal append carries
`--session-id "$(python3 packages/task/scripts/plan-session.py current --id)"`. Resolve exactly one
provider adapter or do not append. Before start compute
`run_id = task.journal.derive_run_id(plan_id=plan_id, item_id=item_id, attempt=attempt, session_id=session_id)`;
use that nonempty `--run-id` for start and terminal. A repeated terminal close returns its existing
pointer and writes no second journal entry.

For a multi-item invocation, run the inherited pre-journal batch admission once over the exact
requested list. Persist `task.task_contract.build_batch_receipt(...)` as optional
`--batch-receipt-json` evidence when a completed prefix leaves a suffix; its Routing/spec digests
must still match before that suffix can resume.
