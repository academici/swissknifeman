<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-run.md
Canonical SHA-256: sha256:0d77960f5c4f3a6b4fadcedc8f052e50f9c9490a97ad1d7e783d3a7af85f7944
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

Execute `$ARGUMENTS` by the canonical `task:plan-exec` lifecycle. `plan-run` inherits the current
provider-attested route; it never pins model or effort and it never substitutes config or prose for
route evidence. Capture five v2 carriers once, admit the Routing group or ready subset of a recommended group, persist one
`route-run-receipt/v1`, then reuse route/context evidence until `route_change_boundary()` proves change.

Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` for transient change-impact selection: focused validation and one
commit are normal; declared hard risk widens validation/review; foreign baseline is non-gating unless
its closure intersects; audit is read-only; only changed projections are generated once; one semantic
Next is rendered by `plan_delivery`. A declared Validation carrier needs current GREEN evidence, not
another run at each lifecycle transition: reuse it while relevant product/test/tool/config inputs and
environment are unchanged, rerun the affected delta after change, and rerun a live check at its live
boundary. Follow the complete close and delivery gates from `plan-exec`.

After GREEN acceptance, persist evidence and the terminal journal event, regenerate changed views,
and close the item in this invocation. If it is the last item of a GREEN phase and no audit is
explicitly admitted by `phase_audit_policy`, create the phase closure in this invocation too. Compute
Next only from that post-closure state and dependencies. Never render a launch for `plan-close` of
this result or for another `plan-run`/`plan-exec` of the current item.

For an installed terminal-admission adapter, arm the lease only after this command's run receipt,
refresh it only after material progress or typed owner-wait, and use its check verdict before a
terminal response. It is repository-owned admission evidence, not a claim that an unconfigured
provider transport is intercepted.
