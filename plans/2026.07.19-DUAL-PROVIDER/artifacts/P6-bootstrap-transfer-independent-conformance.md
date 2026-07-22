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
