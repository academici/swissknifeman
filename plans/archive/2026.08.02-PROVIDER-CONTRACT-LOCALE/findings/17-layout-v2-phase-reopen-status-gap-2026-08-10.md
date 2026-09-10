# Layout v2 phase-reopen status carrier gap — 2026-08-10

## Observation

`packages/task/lib/task/plan_status.py` derives a phase status exclusively from the generated
states of its item specs. A phase-level journal event such as the mandatory
`plan-design --item P0 --result in-progress` is retained in the Update Log but is not an input to
`_phase_status()`. When a terminal v2 phase is reopened by adding forward-remediation items, those
new items have truthful generated state `⬜ Not started`; the owner status view therefore projects
the reopened phase as `⬜ Not started`, not the v1 four-step literal `🟡 In progress`.

RAG:— (repo-grounded: `packages/task/lib/task/plan_status.py:_phase_status`,
`packages/task/lib/task/plan_item_state.py:RESULT_STATUS`, and the `task:plan-design Pn` journal
contract in `packages/task/commands/plan-design.md`).

## Safety verdict

Do not hand-edit `status.md` or `*.state.md`, and do not append a false P0.5 execution-start event
merely to obtain the desired colour. This P0 pass keeps the phase nonterminal, records the exact
P0.5 Next carrier, and accepts `⬜ Not started` as the truthful v2 projection until P0.5 execution
actually begins. The carrier mismatch is a protocol/runtime debt, not permission to widen P0 into
Task package implementation.
