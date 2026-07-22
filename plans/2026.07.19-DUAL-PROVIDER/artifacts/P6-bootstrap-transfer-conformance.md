# P6 bootstrap-transfer conformance

**Item:** P6.7
**Decision:** D104
**Scope:** disposable roots only; no live root command was run.

## Exact admission

The mAInd caller requests the P2 `bootstrap-transfer` admission only when the selected
provider projections include Codex, `.codex/hooks.json` exists, and the P2 lock is absent.
It supplies exactly the D104 target pair, artifact IDs and preimage:

- `.codex/hooks.json` — `sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
- `.codex/hooks/lifecycle.py` — absent before transfer;
- `harness.codex.lifecycle.hooks` and `harness.codex.lifecycle.handler`;
- decision `D104` and the canonical P2 lock path.

Composition parses the preimage as native Codex JSON, preserves its sole memory
`SessionStart` command, and appends only the P5 public observer fragment. P5 validates the
two-command document before P2 planning. No Claude bytes or text replacement are inputs.

## Temporary-root matrix

| Case | Evidence |
|:--|:--|
| First transfer | P2 plan is `update` + `create`; handler and recoverable backup are created. |
| Second deploy | The lock suppresses a second bootstrap request; ordinary P2 classification is all `noop`. |
| Explicit drift repair | A local hooks-byte change is refused by ordinary check and returns to green only through explicit repair. |
| Rollback | A simulated P2 interruption restores the exact preimage and leaves no handler or lock. |
| Foreign preservation | An unrelated temporary-root file remains byte-identical through transfer and ordinary deploy/repair. |
| Refusal negatives | Changed preimage and pre-existing handler produce only `refuse`; the facade returns `MAIND_PROVIDER_DEPLOY_REFUSED` before MCP output is written. |

## Commands

The focused P6 tests run through the package import layout:

```text
PYTHONPATH=packages/maind/lib:packages/maind:. python3 -m unittest discover -s packages/maind/tests -p 'test_provider_deploy.py'
PYTHONPATH=packages/maind/lib:packages/maind:. python3 -m unittest discover -s packages/maind/tests -p 'test_deploy.py'
```

The plan-prescribed `PYTHONPATH=.` variants do not import the package test layout; this is
recorded in P6.7 Known Deviations and does not change a target, lock or live root.

## P6.9 preflight and split projection

The P6 facade now projects the D104 bootstrap result separately from the ordinary provider
aggregate. `not-selected` means Codex is not effective; `admitted` retains the P2 dry-run
actions; `refused` retains a stable refusal diagnostic. None of those bootstrap results changes
the ordinary provider aggregate.

For every selected operation, mAInd constructs the ordinary provider plan/check and the exact
D104 transfer plan before its first write. The initial ordinary check never includes transfer
artifacts against the unchanged root. Only after an admitted transfer is applied does mAInd
replan the ordinary artifacts with the actual transfer records, before any MCP artifact write.

| Temporary-root case | Bootstrap | Ordinary provider result | Write proof |
|:--|:--|:--|:--|
| Claude-only D104-shaped hooks | `not-selected` | ordinary Claude dry plan | no target created |
| Selected Codex exact preimage + foreign `.mcp.json` | `admitted` with P2 `update` + `create` actions | `failed` / `unmanaged-target` | writer spy `0`; before/after snapshot identical |
| Selected Codex changed hooks preimage | `refused` | separately planned ordinary projection | no lifecycle or MCP target created |
| Selected Codex clean targets | `admitted` | ordinary plan follows the completed transfer and remains idempotent on the second run | normal transfer then ordinary apply |

This evidence remains disposable-root only. It neither adopts `.mcp.json` nor changes provider
selection, and it does not authorize a live apply, repair, rollback, P7.2, phase close or audit.
