---
description: "Plan protocol: execute plan item Pn.m using the current session model/effort; use for Exec=manual series without repeated session selection."
argument-hint: "<PLAN-ID> Pn.m [Pn.k]"
---
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
Its immutable forms are `block-candidate/v1`, `return-judgement@1.0.0`, and
`packages/task/prompts/return-judgement-rubric-v1.md`; reviewer verdicts remain `JUSTIFIED`,
`AVOIDABLE`, `INSUFFICIENT_EVIDENCE`, `OUT_OF_SCOPE`, and `MALFORMED`. The command identity is
`plan-run`.

Read the v2 five-slot item path only: `plans/<PLAN-ID>/plan.md`,
`plans/<PLAN-ID>/phases/<Pn>/<Pn>.md`, `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.md`,
`plans/<PLAN-ID>/bundles/<Pn.m>.json`, and `plans/<PLAN-ID>/phases/<Pn>/<Pn.m>.state.md`.
`Layout | v2` is mandatory; otherwise return `PLAN_LAYOUT_V1_RETIRED`. Do not use or reread
`handoff.md`.

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
