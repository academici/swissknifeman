<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-close.md
Canonical SHA-256: sha256:45ea434f167828404dfdcd036e9b8e490d2a7f2a5226aaadf9dd898836113966
Adapter: task.codex-command/1.0.18
-->
## Native Codex launch-block — required only at a real user-facing boundary

This generated runtime is the Codex provider projection. Render only the Codex-native launch;
never copy Claude Code slash syntax as the executable invocation and never print both providers.
`$ task:…` is an invocation inside the **current** Codex session, not a fresh launch.
When the typed Context is `continue-root`, keep executing the compatible ready successor within
the owner-authorized scope in this root. If that scope is complete, report the exact successor as a
recommendation for this chat; a final answer does not require a new `codex` process. A command, phase, directory, local repair, or ordinary test failure is not a session
boundary.

At a fresh-session boundary, keep Batch/Model/Thinking/Context/The bottom line in the metadata table,
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
do not reuse the preceding session's route. Current Codex mapping: economy=gpt-5.6-luna, implementation=gpt-6-sol, frontier=gpt-6-astra;
low=low, medium=medium, high=high, xhigh=xhigh. At a fresh-session boundary, keep the provider-neutral Next too; its
`$ task:…` form alone or an unpinned `codex` command is not a native fresh launch.

## Codex current-route binding — provider-specific

Before the first product-journal mutation, capture the effective route for this exact command:

```bash
export TASK_CODEX_PLUGIN_ROOT="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')"
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH="${TASK_CODEX_PLUGIN_ROOT}/lib:${TASK_CODEX_PLUGIN_ROOT}/../.."   python3 -m task.route_evidence_codex capture   --expected-invocation '$ task:plan-close <arguments>' --expected-cwd <repo-cwd>)"
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

Invocation payload: `$ARGUMENTS`.

`task:plan-close <PLAN-ID>` closes the whole plan. Reject phase and item targets (`Pn`, `Pn.m`).
Archive is a separate explicitly requested operation and does not establish plan acceptance.
Execution completes each item in its own invocation; phases group items and acceptance gates.

Use `plan-work.py close-plan --plan-dir <dir> --session-id <actual-session>` to verify all phases,
current item evidence, unresolved owning work, phase/plan Validation and fresh audit evidence.
`phase_audit_policy` remains the sole assurance reducer; it returns acceptance or an owner-admitted
audit, and never compiles acceptance into a phase-close launch. Verify one semantic Next for the plan.
Mandatory phase/plan Validation sections require `acceptance/<Pn|plan>.json` with
`schema_version=plan-acceptance/v1`, `plan_id`, `subject`, `candidate_sha256`,
`validation_sha256` and `checks=[{requirement,status:green,path,sha256}]`. Every declared
Validation bullet (or the complete section when there are no bullets) must have current hashed
evidence. A RED or missing gate, unresolved deviation or absent external authority blocks close.
Reuse unchanged checks; do not start hosted CI, push or other external work without its authority.

The runtime writes an idempotent whole-plan terminal event and `closure/plan.json`.
Regenerate status once, derive `terminal: plan closed`, persist the handoff and verify a
`plan_delivery.build_terminal_receipt(..., 'plan')` before the final response.

Historical phase-close events and `Pn.closed.md` remain readable evidence. For a legacy
phase/item-close Next, use terminal reconciliation to derive the actual successor without
executing the obsolete command. A finished phase alone never permits closing the whole plan.

If a terminal-admission lease applies, `plan-close` provides the freshly rebuilt delivery receipt
and exact machine-authored final fragment to its provider-neutral reducer. A missing, stale or
mismatched lease never fabricates a terminal allow; recovery is a named re-arm/resume action.
