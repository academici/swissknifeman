<!-- Generated Codex runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-design.md
Canonical SHA-256: sha256:d5d75c7d162f7221c1057b2970b1e4e4026cd06e8f835a9f580479ecd788fc9c
Adapter: task.codex-command/1.0.15
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
export TASK_CODEX_ROUTE_EVIDENCE="$(PYTHONPATH="$(codex plugin marketplace list --json | python3 -c 'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item["root"] for item in data.get("marketplaces", []) if item.get("name")=="swissknifeman" and (pathlib.Path(item["root"])/"packages/task/lib/task").is_dir()]; len(roots)==1 or sys.exit("task runtime unavailable: expected one marketplace root with packages/task/lib/task"); print(roots[0]+"/packages/task")')/lib"   python3 -m task.route_evidence_codex capture   --expected-invocation '$ task:plan-design <arguments>' --expected-cwd <repo-cwd>)"
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

Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/design-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory execution context.

Design creates a v2 plan contract, not a second execution protocol. Read repository evidence,
declare `Phase Assurance | v1` in every new phase (impact, named seams, live/irreversible,
audit intent, rationale), Routing Batch/Review, Required Reads, Files, Validation and Deliverables, then generate
owned views. Use `task.plan_lifecycle.select(task.plan_lifecycle.LifecycleInput())` as the normal-path vocabulary: focused validation,
selective projections, one semantic Next, and a measured context boundary.

For an existing phase, inspect its item carriers and state before designing. If its items are already
detailed and an unfinished item is execution-ready, return `task:plan-exec` for that item rather
than redrafting the phase. “Next/new phase”, item count, local repair, or an ordinary failed check
does not justify design; only new/from-draft scope or a concrete `design-required` contract decision
does.

Назначай Short ID и оформляй ссылки по `runtime/plan-protocol/references/work-references.md`
из установленного пакета Task (`PLAN1.D35`, `PLAN1.P2.3`; legacy: `<PLAN-ID> <local-ID>`).

Design completion records exactly one semantic Next. A bounded remediation does not manufacture a
fresh audit/root; only a concrete context-budget, capability, owner-pause, independent review,
public/authority, or material-risk boundary does. `DESIGN-ROOT-TERMINAL` remains a design-result
handoff boundary: it must not execute or spawn a successor in the same design invocation.

An applicable terminal-admission lease is a provider adapter concern: design supplies only typed
continuity and delivery carriers, never free-prose terminal authorization.

For new ordinary Routing groups, start Почему with `recommended:`; ready subsets may execute.
Use `required:` for an explicit atomic/owner-mandated group. Historical unmarked groups stay
exact until changed through their existing decision carrier.
