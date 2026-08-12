# Task migration runbook for plan layout v1 → v2

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
4. Obtain the repository-owned, validated migration-policy manifest. A target absent from that
   closed manifest, or any source-tree digest drift, is a hard stop.

## Mandatory dry run

Create an explicit temporary output directory. The source plan is read only in this mode.

```bash
PLAN_ID="<PLAN-ID>"
MIGRATION_TMP="$(mktemp -d)"
POLICY="plans/<POLICY-OWNER>/artifacts/P1/layout-v1-migration-policy-v1.json"
python3 packages/task/scripts/plan-migrate.py \
  "plans/$PLAN_ID" \
  --policy "$POLICY" \
  --dry-run \
  --output "$MIGRATION_TMP/$PLAN_ID" \
  --inventory "$MIGRATION_TMP/$PLAN_ID/artifacts/p2-migration-inventory.json"
python3 packages/task/scripts/plan-lint.py "$MIGRATION_TMP/$PLAN_ID"
```

Green means the migrator prints `MIGRATED: …`, writes the requested inventory, preserves exact
byte-identical copies of the complete legacy plan tree in `artifacts/migration-source-v1/` with
its SHA-256 manifest, and the generated output passes `plan-lint`. Inspect both the inventory and
that source archive before continuing: every legacy element and every source byte must be accounted
for, and any warning or missing carrier is a reason to stop and repair the input or the migrator first.

A policy preview imports terminal current state without pretending that synthetic rows are
chronology. A legacy `In progress` flag without a canonical execution event becomes resumable
`Not started`; both it and every legacy pending item remain explicit in the migration inventory.
Those items receive migration-pending admission until a post-migration execution event exists;
that first event removes the transition and restores normal fail-closed D2 admission. The semantic
handoff therefore points to the next resumable item or skeleton rather than claiming completion.

A legacy plan can still fail rehearsal because it has an unclassified defect, a stale preimage,
or a semantic invariant mismatch. Preserve the diagnostic and repair the frozen policy or owning
tool before asking for write authority. Never add a target-name conditional.

If the dry run fails, keep the temporary directory for diagnosis and do not retry with a write.
The migration is fail-closed; editing generated v2 projections by hand does not repair it.

## Controlled write boundary

A green preview is still not write authority. Controlled apply requires the same frozen policy,
an explicit preview, and an unchanged full-tree preimage digest. It verifies that the preview's
byte-exact source archive matches the target, stages a sibling tree, swaps atomically, checks the
post-write Layout-v2/archive invariants, and restores the preimage before returning any failure.

```bash
python3 packages/task/scripts/plan-migrate.py plans/<PLAN-ID> \
  --policy "$POLICY" \
  --apply \
  --preview "$MIGRATION_TMP/<PLAN-ID>"
```

Do not run that command during policy authoring or preview admission. It belongs to the separately
authorized fleet-cutover step. A target that is already Layout v2 returns a digest-checked no-op;
its preview is never applied as a hidden repair. Do not copy generated files into the source plan
by hand.

## After the write

1. Preserve the policy row, dry-run inventory, source archive and lint result with the owner decision.
2. Revalidate the source digest immediately before controlled apply.
3. Check generated views and plan-lint after the swap; a failure must have restored the preimage.
4. If any projection, bundle, lint rule, or required input is stale, stop and repair the input or
   migrator; do not resume execution on an assumed migration.

This procedure migrates plan structure only. It does not change plan scope, decisions, ownership,
or acceptance criteria.
