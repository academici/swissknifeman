# P1.2 — full-fleet Layout v1 admission matrix

## Provenance

Read-only reconnaissance on 2026-08-12 exercised the exact 15-target `migration_order` from
`artifacts/P1/active-layout-inventory-v1.json`. Every target was copied to a distinct disposable
directory below `/tmp/task-p12-design-probe-exact.Wfubq8`; the worktree-local migrator ran only
with `--dry-run --output`, and its source-hash guard preserved every source. The disposable paths
are provenance only, not execution inputs. RAG:— (repo-grounded:
`artifacts/P1/active-layout-inventory-v1.json`, `packages/task/lib/task/plan_migrate.py`).

```bash
python3 packages/task/scripts/plan-migrate.py "$target" \
  --dry-run --output "$tmp/$n/$plan_id" \
  --inventory "$tmp/$n/$plan_id/artifacts/p2-migration-inventory.json"
python3 packages/task/scripts/plan-lint.py "$tmp/$n/$plan_id"
```

## Result

| # | Target | Migrator | Output admission |
|:--|:--|:--|:--|
| 1 | `2026.07.17-AXIOMA-ORCHESTRA` | OK | 4 ERROR: comma-list Routing; 6 WARN |
| 2 | `2026.08.04-ROCKET-PRODUCTION-HARDENING` | OK | 6 ERROR: terminal-state projection; read-budget |
| 3 | `2026.07.17-DTEREMA-UX` | FAIL | journal line 21 has unknown `result` |
| 4 | `2026.07.23-DTEREMA-PROD-P0` | OK | terminal `Next` while items remain nonterminal |
| 5 | `2026.08.06-EDUFY-BUILD` | OK | invalid/missing read-budget contract |
| 6 | `FLEX-2` | OK | prose Routing row; read-budget |
| 7 | `2026.07.12-SEMANTIC-CORE` | FAIL | Decision Log has no D-records |
| 8 | `AGENTOOLS` | OK | terminal-state projection; read-budget |
| 9 | `ERP-IMPL` | OK | read-budget |
| 10 | `LOQUM-DEV` | FAIL | missing `journal.jsonl` |
| 11 | `AUDIT-VLT` | FAIL | missing `journal.jsonl` |
| 12 | `VLT-HSEAM` | FAIL | missing `journal.jsonl` |
| 13 | `VLT-LOAD` | FAIL | unsupported/noncanonical Decision Log table |
| 14 | `2026.07.27-RESP-CHTZ` | OK | non-item Routing rows; terminal-state projection; read-budget |
| 15 | `2026.07.30-SITE-HARDENING` | FAIL | phase without a migratable item |

Nine targets migrate structurally, six fail before lint, and zero pass the required output lint.
The first target's exact rejected `Items` cells are `P0.1–P0.3, P0.5`,
`P1.1–P1.5, P6.1–P6.3`, `P3.1, P3.3–P3.8`, and `P5.2–P5.3, P6.4–P6.5`.
`plan_migrate._render_core()` copies legacy Routing unchanged, while both plan-lint and Task
Contract intentionally accept only one item or one ascending same-phase range per cell.
RAG:— (repo-grounded: `packages/task/lib/task/plan_migrate.py`,
`packages/task/lib/task/plan_lint_checks/engine.py`, `packages/task/lib/task/task_contract.py`).

## Independent write-boundary contradiction

P1.2 requires owning-tool in-place migration, but `migrate_safely()` rejects every non-dry-run
invocation and the runbook deliberately declares the fleet path dry-run-only. A green rehearsal
therefore would still not authorize or provide the required write workflow. RAG:—
(repo-grounded: `packages/task/lib/task/plan_migrate.py`,
`packages/task/docs/plan-migration-runbook.md`, `phases/P1/P1.2.md`).

## Verdict

The applied owner action `DR-P1.2-layout-migration-contract` is enough for deterministic Routing
normalization and focused tests, but not for a truthful `all 15 + zero_active_v1` acceptance.
The unresolved choices change declared scope and legacy-state interpretation; they require a new
bounded owner decision. No source target was changed. RAG:— (owner/repo-grounded:
`decisions/queue.jsonl`, this matrix).
