# P1.3 — frozen policy and full-fleet preview admission

## Contract

`artifacts/P1/layout-v1-migration-policy-v1.json` is the closed admission manifest owned by
`validate-layout-v1-migration-policy.py`. Its 54 rows cover the exact 15-target
`migration_order`, full source-tree and `plan.md` SHA-256 preimages, defect class, transform,
semantic invariant and rollback. The manifest validator finished `POLICY-OK targets=15 rows=54`
after the final preview tail, proving that no source digest changed during rehearsal.

The migrator has no target-ID branches. Policy dispatch is limited to the closed classes:
Routing normalization, canonical current-state import, reversible decision-ID mapping, skeleton
preservation, frozen read-budget carrier, semantic handoff and already-v2 admission. Raw v1 trees
remain byte-exact in `artifacts/migration-source-v1/`.

Legacy pending items are not silently D2-ready. The migration inventory marks them as transitional
`migration_pending_redesign`; terminal state is imported before the single canonical
`item_id=layout-v2` activation boundary. A first post-activation execution event removes that hold
and restores normal fail-closed D2. This required a narrow owning-module expansion to
`task/plan_admission.py` and `test_plan_admission.py`, which were missing from the P1.3 `Files`
enumeration; keeping the original list would have forced either false `Not started` state or a
misleading green lint.

## Preview ledger

| # | Target | Items | Inventory elements | plan-lint |
|:--|:--|--:|--:|:--|
| 1 | `2026.07.17-AXIOMA-ORCHESTRA` | 34 | 630 | 0 ERROR · 6 WARN |
| 2 | `2026.08.04-ROCKET-PRODUCTION-HARDENING` | 17 | 416 | 0 ERROR · 0 WARN |
| 3 | `2026.07.17-DTEREMA-UX` | 46 | 1081 | 0 ERROR · 128 WARN |
| 4 | `2026.07.23-DTEREMA-PROD-P0` | 30 | 694 | 0 ERROR · 96 WARN |
| 5 | `2026.08.06-EDUFY-BUILD` | 112 | 2349 | 0 ERROR · 2 WARN |
| 6 | `FLEX-2` | 68 | 1232 | 0 ERROR · 29 WARN |
| 7 | `2026.07.12-SEMANTIC-CORE` | 50 | 828 | 0 ERROR · 94 WARN |
| 8 | `AGENTOOLS` | 119 | 2471 | 0 ERROR · 1 WARN |
| 9 | `ERP-IMPL` | 64 | 1144 | 0 ERROR · 2 WARN |
| 10 | `LOQUM-DEV` | 37 | 654 | 0 ERROR · 10 WARN |
| 11 | `AUDIT-VLT` | 30 | 530 | 0 ERROR · 10 WARN |
| 12 | `VLT-HSEAM` | 5 | 111 | 0 ERROR · 4 WARN |
| 13 | `VLT-LOAD` | 27 | 535 | 0 ERROR · 11 WARN |
| 14 | `2026.07.27-RESP-CHTZ` | 79 | 1621 | 0 ERROR · 14 WARN |
| 15 | `2026.07.30-SITE-HARDENING` | 58 | 1096 | 0 ERROR · 0 WARN |

Warnings are preserved legacy portability/optional-document diagnostics; P1.3 admission requires
zero ERROR, not warning erasure or semantic redesign.

## Evidence integrity

The execution PTY twice ended a long fleet loop after target 13 without printing its final trailer.
The final proof was therefore split deliberately into targets 1–8 and 9–15. During the second
chunk, concurrent work changed target 15 and its frozen preimage correctly failed closed; targets
9–14 were green. A first target-15 retry reached 0 ERROR but its post-preview policy check caught
another concurrent preimage change, so it was rejected as final evidence. After three equal digest
samples across 20 seconds, the owning generator refreshed the exact preimage, target 15 was rerun
green, and the post-preview 15-target validator returned `POLICY-OK targets=15 rows=54`.
This is disclosed as an environmental execution/concurrency defect, not represented as one
uninterrupted command.

During P1.3, target `2026.07.30-SITE-HARDENING` was independently converted to Layout v2 by its
owning repository (`eeeaed6`) and carried unrelated dirty plan changes. Policy classifies its exact
current digest as already-v2, rebuilds only a disposable admission preview from the archived v1
preimage, moves legacy `Version`/`Last Updated` Meta rows to v2 ownership, and guarantees controlled
apply is a no-op. P1.3 did not write any of the 15 sources and did not invoke controlled apply.

Package validation compiled all Python/Bash surfaces and ran 849 tests green (one skipped);
`plan-lint --conflicts` reported zero drift. The aggregate root plans lint remains red only for
seven pre-existing closed-grammar Routing rows in three archived plans
(`2026.07.10-SKM-ROADMAP-005`, `2026.07.13-PLAN-PROTOCOL-GAP`, `2026.07.18-FOREMAN`). Active
TASK-RESILIENCE bundle drift was repaired through `plan-views`; the archive rows are outside the
P1.3 policy/tooling/15-target write scope, so the full `validate.sh` acceptance cannot truthfully be
reported green.
