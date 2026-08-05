# HANDOFF — 2026-08-05 — after P3.7

**Next:** run-items: task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.8

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Context | continue (/clear) — ручной item |
| Суть | Promote the verified runtime into the Artifex package through the exact D95 generator transaction |
| Команда | — |

**Done:** `27bd2f0d` removes the stale Task-cardinality assumption. Task validation passed 486 tests, full supervisor discovery passed 58 tests, the temporary real probe produced two schema-valid rows, and adapter/parity, plan-lint and strict-citation gates passed; P3.6 carriers remained clean.

**Remaining:** Execute P3.8, then close P3 under the two-pass audit cap.

**Sources of truth:** phases/P3.md P3.7 Completion Notes · plan.md D95/D98 · roadmap.md · `27bd2f0d`.

**Open risks:** P3.5's foreign `scheduler.py` path remains a material deviation; P3.8 must refuse any missing/revoked D86/D95 grant, generator action mismatch, or non-green stage gate.

**Workarounds/Deferred/Open questions:**

- workarounds: P3.7 probe used repository-local `TMPDIR` because the probe correctly confines output beneath the explicit project root; D98 forbids audit 11;
- deferred: P4.6 owns hook repair;
- open_questions: none.

```text
$ task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P3.8

РЕЖИМ: manual implementation/high item; start at stage 1 only
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/plan.md · phases/P3.md P3.8 · handoff.md · D86/D95 exact grants
СКОУП: exact Harness instructions plan→apply→check transaction, then mandatory package-cwd continuation
НЕ ТРОГАТЬ: P3.6 carriers, root router/installer, unrelated dirty worktree, D98 audit prohibition
```
