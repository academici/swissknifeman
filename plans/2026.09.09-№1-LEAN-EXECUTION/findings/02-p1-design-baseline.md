# P1 design baseline — 2026-09-09

RAG:— (local source and preflight observations).

## Preflight

- Route evidence: `gpt-5.6-sol/high`, class `frontier`, provider-thread-state, exact invocation and
  repository cwd matched before mutation.
- `codex doctor --json` and corrected `packages/maind/bin/maind health --cwd --json` were green.
- Codex SessionStart hook path exists; a complete synthetic payload returned the expected observer
  message. The first incomplete probe returned exit 2 because mandatory payload keys were omitted;
  this was procedural input error, not hook exit 127 or a registration defect.
- Initial plan-lint was red: legacy `Version`/`Update Log` still lived in v2 plan core and P3–P6
  phase indexes were absent. P1 design repairs these plan-bookkeeping/schema gaps without treating
  them as product failure.

## Current seams

- `plan-views.py history` prints to stdout only when `--stdout` is absent, while its own global CLI
  still requires `--plan-dir`; `plan_item_state.py` emits a history command without that required
  argument. The historic `--stdout` mismatch changed form but the caller contract remains broken.
- `task_contract._find_routing_row()` resolves only model class/effort for one item. Batch is parsed
  later by plan-lint for handoff consistency, so admission has no authoritative pre-journal batch
  verdict or durable suffix receipt.
- `plan_requests._continuation()` preserves `resume-root`, but `PlanNextCarrier` uses the older
  `same-session|cold-start` pair and `PlanProviderInvocation.codex_launch()` always renders a fresh
  process. Continuity meaning can therefore be lost between reducer, renderer and delivery.

## Design verdict

Use three ordered vertical items: complete input, authoritative batch admission, then continuity.
Derive batch authority from `plan.md §3 Routing` (D6) and keep provider UI/final transport outside P1
under D5. No external RAG is required for these repository-local facts.
