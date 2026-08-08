# Cross-phase finish after early-package correction

## Owner directive — 2026-08-04

Run `task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR finish` as a design-only cross-phase
reconciliation after the early-package correction.

Required inputs:

- `plan.md` D85–D88;
- `phases/P3.md` P3.8;
- `phases/P4.md`;
- `phases/P5.md`;
- `phases/P6.md`.

Required scope:

1. Verify the P3.8 package producer and its handoff into P4/P5.
2. Verify the P4/P5 evidence chain into P6 public integration.
3. Verify that successful P6 completion yields the finished standalone and umbrella product
   without a second runtime migration.
4. Hand the reconciled plan to a cold independent design audit.

Protected anti-scope:

- do not reopen frozen P1/P2;
- do not rewrite terminal P3.1–P3.4 history;
- do not execute any implementation item;
- do not touch unrelated dirty worktree paths.

RAG:— (direct repository-owner command in the active 2026-08-04 session).
