# Migration runbook for plan layout v1 → v2

Use this runbook to prepare a single repository-owned executable plan for the v2 layout.
It does not authorize a migration: the plan owner must approve the target and inspect the dry-run
output before any write.

## Before you start

1. Work from the repository that owns the plan and start with a clean, committed tree.
2. Confirm that the target still uses the legacy layout (its `plan.md` has no `Layout: v2` Meta
   field) and that it is not being executed concurrently.
3. Check that the migration tool is available:

   ```bash
   python3 packages/task/scripts/plan-migrate.py --help
   ```

## Mandatory dry run

Create an explicit temporary output directory. The source plan is read only in this mode.

```bash
PLAN_ID="<PLAN-ID>"
MIGRATION_TMP="$(mktemp -d)"
python3 packages/task/scripts/plan-migrate.py \
  "plans/$PLAN_ID" \
  --dry-run \
  --output "$MIGRATION_TMP/$PLAN_ID" \
  --inventory "$MIGRATION_TMP/$PLAN_ID/artifacts/p2-migration-inventory.json"
python3 packages/task/scripts/plan-lint.py "$MIGRATION_TMP/$PLAN_ID"
```

Green means the migrator prints `MIGRATED: …`, writes the requested inventory, and the generated
output passes `plan-lint`. Inspect the inventory before continuing: every legacy element must be
accounted for, and any warning or missing carrier is a reason to stop and repair the input or the
migrator first.

A legacy plan can convert structurally and still fail current lint because it predates a required
read-budget contract, has a stale phase handoff, or lacks a canonical Decision Log table. Treat
each case as a failed rehearsal: preserve the diagnostic and repair the owning source or migrator
before asking for write authority.

If the dry run fails, keep the temporary directory for diagnosis and do not retry with a write.
The migration is fail-closed; editing generated v2 projections by hand does not repair it.

## Write boundary

The converter deliberately permits an in-place write only for its self-host plan
`2026.08.07-PLAN-ECONOMY`; every other plan is dry-run-only and the tool fails closed if asked to
write it. This protects an owner from treating a successful preview as authority to mutate another
plan.

```bash
python3 packages/task/scripts/plan-migrate.py plans/<PLAN-ID>
# expected for any non-self-host plan: ERROR: inplace-конвертер разрешён только для self-host плана
```

For a non-self-host plan, retain the dry-run output and request a separately designed migration
workflow. Do not copy its generated files into the source plan by hand. Any eventual write must be
owner-approved, reviewable, and separate from content edits, phase execution, or protocol upgrades.

## After the write

1. Preserve the dry-run inventory and lint result with the owner decision.
2. Use the generated output only for review until an approved write workflow exists.
3. If any projection, bundle, lint rule, or required input is stale, stop and repair the input or
   migrator; do not resume execution on an assumed migration.

This procedure migrates plan structure only. It does not change plan scope, decisions, ownership,
or acceptance criteria.
