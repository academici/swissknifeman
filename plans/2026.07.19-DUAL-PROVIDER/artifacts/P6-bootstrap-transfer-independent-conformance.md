# P6 bootstrap-transfer independent conformance

**Item:** P6.8  
**Observed:** 2026-07-22  
**Tree:** `f29653a7e9eb5dd342c0780a1d797cebfc2192fb`  
**Scope:** task-scoped disposable roots only; no live root command appears in this artifact.

## Independently derived D104 oracle

Before observing the temporary-root results, the expected admission was derived from D103/D104:

- decision is exactly `D104`;
- existing target is `.codex/hooks.json` with preimage
  `sha256:7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`;
- created companion is absent `.codex/hooks/lifecycle.py`;
- no P2 lock exists before the transfer, and the transaction writes exactly the two
  `harness.codex.lifecycle.{hooks,handler}` records;
- native JSON retains the sole memory `SessionStart` command and adds exactly the public P5
  observer `SessionStart` command; duplicate, missing, or non-`SessionStart` entries refuse;
- first transfer is followed by ordinary all-`noop` lifecycle checking, managed drift needs an
  explicit repair, rollback restores the exact preimage, and non-admission writes nothing.

## Disposable-root matrix — GREEN

The independent executor ran the public package test layout on the tree above:

```text
PYTHONPATH=packages/maind/lib:packages/maind:. python3 -m unittest discover -v -s packages/maind/tests -p 'test_provider_deploy.py'
PYTHONPATH=packages/maind/lib:packages/maind:. python3 -m unittest discover -s packages/maind/tests -p 'test_deploy.py'
```

The first command passed 21 tests and the second passed 19 tests (both on `f29653a7`, as
reported by the commands). The verbose first suite includes independent temporary-root coverage
for D104 composition followed by ordinary P2 repair, changed-preimage/existing-handler refusal
without writes, interrupted-transaction rollback, facade refusal before MCP write, and a
deterministic foreign-preserving no-write conformance case. The second suite passed with its
temporary fixture diagnostics only. No test targets the live repository root.

## Boundary

This result proves the disposable-root transfer matrix only. It does not attest the live root;
that admission is separately recorded in
`findings/P6-bootstrap-transfer-live-preflight-2026-07-22.md`.

## P6.10 — independent split verdict and zero-write recheck

**Observed:** 2026-07-22T19:09:24+03:00
**Tree:** `cbca1aff` before P6.10 evidence commits
**Mode:** literal D104/D106 oracle before observation; disposable roots and the two permitted
live dry-run readers only.

The independently derived oracle requires the exact-preimage/foreign-MCP case to retain an
`admitted` bootstrap projection while its ordinary row is `failed / unmanaged-target`; it requires
changed preimage, existing handler and existing lock to be bootstrap refusals with no writer call
and an identical root snapshot. Clean targets remain `admitted / planned`. The P6.9 test module
was not imported to generate these expected values.

| Disposable-root case | Observed split result | No-write result |
|:--|:--|:--|
| Exact preimage + foreign `.mcp.json` | bootstrap `admitted` (`update`, `create`); ordinary `failed / unmanaged-target` | dry writer `0`; snapshot equal |
| Changed preimage | bootstrap `refused / bootstrap-preimage-mismatch` | write facade writer `0`; snapshot equal |
| Existing handler | bootstrap `refused / bootstrap-created-target-present` | write facade writer `0`; snapshot equal |
| Existing lock | bootstrap `refused / bootstrap-lock-present` | write facade writer `0`; snapshot equal |
| Clean target | bootstrap `admitted` (`update`, `create`); ordinary `planned` | dry writer `0`; snapshot equal |

The focused public suites passed: `test_provider_deploy.py` (23 tests on `cbca1aff`) and
`test_deploy.py` (21 tests on `cbca1aff`). The former independently covers the selected-Codex,
foreign-MCP write-mode facade with writer `0` and an equal snapshot.

On the live root, `maind sync --dry-run --json` reports bootstrap `not-selected` plus required
`claude-code failed / unmanaged-target` and `provider_aggregate: non-green`; the P5 observer
reader exits nonzero with `ownership-conflict → refuse (unmanaged-target)`. Before/after sorted
SHA-256 inventories agree: hooks preimage
`7d7538d021228e8e61d124f4b60b6db04434f8121de30b8672f05e4bf038c3db`, absent lifecycle handler,
and absent provider lock. This proves the required split/no-write boundary, not live admission;
the unmanaged `.mcp.json` remains a separate authority decision and P7.2 remains closed.
