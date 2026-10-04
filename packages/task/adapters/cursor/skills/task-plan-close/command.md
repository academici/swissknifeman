<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-close.md
Canonical SHA-256: sha256:03098a126a5da720830263c8e5149e0f082b227c9a02261c107b2fdf20ad386a
Adapter: task.cursor-command/1.0.18
-->
## Native Cursor launch-block — required only at a real user-facing boundary

This generated runtime is the Cursor provider projection. Render only the Cursor-native launch;
never copy Claude slash syntax or Codex `$ task:` as the executable invocation.

At a fresh-session boundary print `**Native Cursor command:**` and a fenced `bash` block which
explicitly pins the repository workspace, mapped model, and autonomy flags:

```bash
agent --workspace <repo-cwd> --model <model-selector> --force --sandbox disabled --trust --approve-mcps 'task:<command> <arguments>'
```

`auto` never substitutes a fixed frontier or implementation pin. Current Cursor mapping: economy=composer-2.5-fast, implementation=composer-2.5, frontier=claude-opus-5-thinking-high.

---
disable-model-invocation: true
description: "Reconcile GREEN Task items or phases; ordinary execution already closes inline."
argument-hint: "<PLAN-ID> <Pn.m|Pn|archive ID>"
model: sonnet
effort: low
---
Invocation payload: `$ARGUMENTS`.

Read `runtime/plan-protocol/references/common-principles.md` and
`runtime/plan-protocol/references/execution-mode.md` from the configured Task package root.
The full schema canon and snippets are on-demand references, not mandatory reconciliation context.

Reconcile only declared terminal evidence. `task_contract` owns both write-site predicates and the sole
exact executable Routing compiler;
`plan_assurance.evaluate()` is the sole assurance/impact reducer behind `phase_audit_policy`: GREEN
evidence direct-closes by default, while an audit needs a bounded residual-risk question and fresh
owner consent bound to its target phase, material candidate and audit run. Legacy
`required`/`auto`/`light` remains readable as advisory migration input and never admits audit;
missing or RED evidence returns owning repair. For an admitted post-GREEN audit, impact reduction
classifies `gate-rebind|delta|full|gather-evidence|owner-review` from a runtime-built candidate but
does not authorize another audit: affected validation is native repair, and a new audit needs fresh
candidate/run-bound owner consent;
`plan_projection` regenerates
only changed carriers once; `plan_continuity` owns context; and `plan_delivery` owns one semantic Next
and provider-native launch rendering. Do not use a command name, bookkeeping drift, Routing Review,
item count, or historical deviation as a full-replay/fresh-root trigger. Unknown impact blocks close
with its exact continuation; it never implicitly authorizes full replay.
For a post-audit phase close, consume the persisted `audit-finalization/v1` bound to the rebuilt
candidate; absence or a non-allow close admission refuses closure.

Normal close is one scoped commit. A second commit requires a real ownership/session boundary or digest-input collision. A red
carrier remains owning repair work; an audit product finding returns its exact continuation.
Explicitly invoked standalone `plan-close` remains supported. Execution commands close their own
GREEN item and eligible last-item phase before handoff; they never launch this command for the result
they just produced. Reuse unchanged product evidence, rerun only a changed relevant delta or a live
gate at its boundary, then compute Next from the post-closure state.

If a terminal-admission lease applies, `plan-close` provides the freshly rebuilt delivery receipt
and exact machine-authored final fragment to its provider-neutral reducer. A missing, stale or
mismatched lease never fabricates a terminal allow; recovery is a named re-arm/resume action.
