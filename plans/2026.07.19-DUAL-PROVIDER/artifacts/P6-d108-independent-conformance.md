# P6.12 D108 independent conformance — RED

**Observed:** 2026-07-22  
**Tree:** `d1a7c6ea` (P6.11 bookkeeping anchor)  
**Mode:** frozen-input oracle, disposable roots, then real-root read-only planning with a
writer spy. No live apply, repair or rollback was invoked.

## Independent oracle

Before running the P6.11 implementation, the frozen D108 inputs require all of the following:

- project carrier adds/enables `claude-code` and `codex` at
  `.swissknife.json#/providers` only;
- the exact live `.mcp.json` preimage is
  `cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283`;
- the exact live D104 hooks preimage is
  `7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
- planning must form both provider projections, D104 and the chained three-record lock before
  a writer is reachable; a dry reader must therefore classify this root or fail only at a
  frozen candidate check, never at package-root identity or a missing Codex projection.

The P2.7 public regression suite independently passed `26` tests at this worktree:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python3 -m unittest discover -v -s core/tests -p 'test_provider_lock.py'
```

It includes the exact D108 chained-admission mutation, stale-precondition, every-write-boundary
rollback, ordered-three-record-lock and second-plan-noop cases. The P6.11 package-local suite
also passed `46` tests:

```text
cd packages/maind
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../..:lib:../harness/lib \
  python3 -m unittest -v tests.test_provider_deploy tests.test_deploy
```

Those passing disposable-root regressions do not make the real-root reader conformant.

## Real-root dry-reader reproduction — RED

The following read-only reproducer uses the effective project configuration and the public
P6 provision facade. `dry=True` suppresses `apply_d108_operation`; a mock at that writer seam
records its call count. The explicit inventory is hashed before and after.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/maind/lib:packages/harness/lib:. python3 -c '<see P6.12 Completion Notes for the exact command carrier>'
```

Observed results:

| Reader | Result | Writer calls | Protected inventory |
|:--|:--|:--:|:--|
| direct `plan_d108_operation(..., expected_root=<repo root>)` | `MAIND_PROVIDER_DEPLOY_REFUSED` | 0 | unchanged |
| public `deploy_project(..., d108=True, dry=True)` | `MAIND_D108_FOREIGN_PROJECT` | 0 | unchanged |

The direct decomposition proves two independent owning-seam faults before any write:

1. `provider_projection_context` resolves the current root before the planned D108 carrier.
   It supplies only `claude-code`; after the carrier correctly selects both providers,
   `plan_provider_deploy` has no Codex base projection and returns a failed row. This becomes
   `MAIND_PROVIDER_DEPLOY_REFUSED`.
2. The public facade passes `expected_root=env.root`; under the worktree-local maind launcher
   that value is `packages/maind`, not the selected project root
   `/home/vostrikov/projects/packages/swissknifeman`. The canonical-project gate consequently
   returns `MAIND_D108_FOREIGN_PROJECT` before it can classify the exact candidate.

The before/after sorted SHA-256 inventory was identical:

```text
.codex/config.toml 68df0b5bcc069ce64c24aeb63c2bb08773219dff83526398ddba247dee6fb2bc
.codex/hooks.json 7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db
.mcp.json cf4537196c3fefd6fd3980221bd3677f74e7867392ad49364e1e891e1f7c8283
```

Absent before and after: `.swissknife.json`, `.codex/hooks/lifecycle.py`, and
`.swissknifeman/provider-artifacts.lock.json`.

## Required bounded repair

Reopen only P6.11's project-operation seam. Its fix must construct provider base projections
for the D108 planned dual selection before asking `plan_d108_operation`, and pass the canonical
project root (not the maind package root) as `expected_root`. Add a focused real-facade
temporary-root regression that proves the exact D108 plan reaches the three-record chain,
fault injection still restores bytes, and dry live reading returns the exact candidate with
writer count `0`. Do not change P2 ownership, frozen D108 values, live carriers, P7.2, FOREMAN,
fleet, tag or push.
