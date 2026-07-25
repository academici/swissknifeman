# P6 bootstrap-transfer live preflight — RED

**Item:** P6.8  
**Observed:** 2026-07-22  
**Tree:** `f29653a7e9eb5dd342c0780a1d797cebfc2192fb`  
**Authority:** D104 permits only these no-write observations; no apply, repair, rollback or lock
write was attempted.

## Expected admission inventory

The D104 candidate is limited to the existing `.codex/hooks.json` preimage
`sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`, an absent
`.codex/hooks/lifecycle.py`, and an absent
`.swissknifeman/provider-artifacts.lock.json`. If admitted, P6 must compose the preserved memory
`SessionStart` command with exactly one P5 observer `SessionStart` command, then P2 may create
the companion handler and canonical two-record lock.

## Observed live inventory

- `.codex/hooks.json` has exactly the D104 preimage SHA-256 above.
- `.codex/hooks/lifecycle.py` is absent.
- `.swissknifeman/provider-artifacts.lock.json` is absent.

Thus the bytes/inventory alone match the narrow D104 candidate. They do not make a dry-run
admitted: the provider row must also be green and the P6 caller must select the exact transfer.

## Exact permitted no-write commands

```text
./packages/maind/bin/maind sync --project swissknifeman --dry-run --json
./packages/harness/bin/harness hooks --target /home/vostrikov/projects/packages/swissknifeman --provider codex --observer --trusted --dry-run
```

| Command | Exit | Result |
|:--|:--|:--|
| `maind sync` dry-run JSON | 0 | **RED**: its `mcp` row is `failed` with `MAIND_PROVIDER_DEPLOY_REFUSED`; the required Claude instruction provider aggregate is also `non-green`. A process exit of 0 does not override either non-green row. |
| `harness hooks` observer dry-run | 1 | **RED**: `Codex lifecycle deploy refused`; `harness.codex.lifecycle.hooks` is `ownership-conflict → refuse (unmanaged-target)` and the missing handler is only a withheld `create`. |

The direct harness reader is intentionally an ordinary lifecycle plan, not an implicit
bootstrap-transfer selector. Neither result was converted to apply or repair.

## No-write proof

Immediately before the first command and after each command, the executor compared sorted
SHA-256 inventories for every `.codex` file plus the lifecycle-handler absence and P2 lock
absence. Both comparisons were empty: the hooks preimage stayed unchanged, the handler stayed
absent, and no P2 lock appeared. `git diff --name-only 19303e4f..HEAD --
plans/2026.07.18-FOREMAN plans/ACTIVE.md` likewise returned no protected paths.

## Required follow-up boundary

P6.8 is complete as evidence but the live admission is **RED**. Do not start P7.2, P7.3,
FOREMAN, fleet, a tag, push, or a live repair. The bounded next action is a new design pass over
the P2/P5/P6 owning transfer seam to explain why the exact candidate remains refused and to
specify a contract-preserving repair; it must not infer authorization for an apply from the
matching preimage.

## P6.10 independent recheck — 2026-07-22

The two same permitted readers were rerun after P6.9. `maind sync --dry-run --json` now exposes
the split result explicitly: bootstrap `not-selected`, required `claude-code`
`failed / unmanaged-target`, and `provider_aggregate: non-green`. The direct P5 observer reader
still exits nonzero with `harness.codex.lifecycle.hooks: ownership-conflict → refuse
(unmanaged-target)`. Sorted SHA-256 inventories before and after both readers are identical:
the D104 hooks preimage remains `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`,
the lifecycle handler remains absent, and no provider lock exists. This confirms the expected
residual boundary; it does not authorize a live repair or P7.2.
