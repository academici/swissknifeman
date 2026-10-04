<!-- Generated Cursor runtime projection; do not edit as source.
Canonical source: packages/task/commands/plan-close.md
Canonical SHA-256: sha256:45ea434f167828404dfdcd036e9b8e490d2a7f2a5226aaadf9dd898836113966
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
description: "Verify acceptance and close the whole Task plan."
argument-hint: "<PLAN-ID> [archive]"
model: sonnet
effort: low
---
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
