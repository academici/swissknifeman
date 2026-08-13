# P1.2 — Layout v1 Routing normalization

## Contract

`plan_migrate` splits a legacy Routing `Items` comma-list only when every
comma-delimited token already belongs to the closed v2 grammar: one item
`Pn.m` or one ascending same-phase range `Pn.a–Pn.b`. The projection preserves
token order and copies every non-`Items` cell byte-for-byte. Prose, mixed
tokens, cross-phase ranges, descending ranges, and empty tokens fail closed
with `MigrationError`.

The v2 runtime grammar was not widened: plan-lint continues to reject a
comma-list or descending range in one `Items` cell.

## Source/output mapping

The dry-run for registered target
`/home/vostrikov/Vaults/Brain/plans/2026.07.17-AXIOMA-ORCHESTRA` produced the
following ordered mapping:

| Source `Items` cell | Rendered v2-legal rows |
|:--|:--|
| `P0.1–P0.3, P0.5` | `P0.1–P0.3` → `P0.5` |
| `P1.1–P1.5, P6.1–P6.3` | `P1.1–P1.5` → `P6.1–P6.3` |
| `P3.1, P3.3–P3.8` | `P3.1` → `P3.3–P3.8` |
| `P5.2–P5.3, P6.4–P6.5` | `P5.2–P5.3` → `P6.4–P6.5` |

Every route/model/effort/exec/reason cell remained identical to its source
row. The migrator reported `MIGRATED: 34 items; inventory 630 elements`.

## Verification

```bash
PYTHONPATH=packages/task/lib:. python3 -m unittest \
  packages/task/tests/test_plan_migrate.py \
  packages/task/tests/test_plan_lint_routing.py
```

Result: `Ran 72 tests ... OK`.

```bash
python3 packages/task/scripts/plan-migrate.py \
  /home/vostrikov/Vaults/Brain/plans/2026.07.17-AXIOMA-ORCHESTRA \
  --dry-run --output <new-temporary-output> \
  --inventory <new-temporary-output>/artifacts/p2-migration-inventory.json
python3 packages/task/scripts/plan-lint.py <new-temporary-output>
```

Result: `plan-lint: OK (1 план(ов), 0 ошибок, 6 предупреждений)`; all warnings
are pre-existing portability/index diagnostics unrelated to Routing. The
source-hash guard passed, and no in-place write was attempted.
