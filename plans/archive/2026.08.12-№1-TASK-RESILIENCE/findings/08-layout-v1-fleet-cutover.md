# P1.4 — controlled Layout v1 fleet cutover

## Result

The frozen P1.3 policy was applied in its declared 15-target order. Fourteen targets returned
`APPLY: installed; preview-installed`; `2026.07.30-SITE-HARDENING`, already converted by its
owning repository, returned the policy-defined digest-checked `APPLY: no-op; already-v2`.
Every target was processed as `fresh dry-run preview → preview plan-lint → controlled apply →
live plan-lint → state/status/decisions --check`. All live lints reported zero errors. The
remaining 408 warnings are the preserved legacy portability/optional-carrier diagnostics already
admitted by P1.3, not silent semantic repairs.

The machine ledger is `artifacts/P1/layout-migration-ledger-v1.json`. It binds each result to the
frozen source digest and records `installed=14`, `no_op=1`, `failed=0`,
`rollback_failures=0`, and `zero_active_v1=true`.

## Owner-gated registry and invalid-root repair

Fresh inventory before apply still contained four unreachable `/tmp` maind registrations and
three invalid candidates. The bounded preserving action was materialized and resolved as
`DR-P1.4-bounded-registry-invalid-repair`:

- the four missing `/tmp` registrations were removed atomically through maind's sole config
  writer;
- the incomplete non-active `2026.07.24-LEAD-FORMS-AND-CTA` tree was moved byte-for-byte under
  the owning repository's archive;
- the duplicate `corex/plans/archive/COREX-CORE` symlink was removed while its canonical Brain
  archive remained present;
- incomplete active `VLT-MUT` was moved byte-for-byte under the owning repository's archive and
  its active pointer was cleared.

No invalid-plan semantics were invented. These external working-tree changes remain uncommitted,
as required by P1.4; they are not mixed into the swissknifeman item commit.

## Zero-live proof

The final fresh inventory reports the three blocking classes separately:

```text
registered=80 roots=23 reachable=23 plans=72 archive=53
invalid=0 unreachable=0 v1-active=0 v2=19 unclassified=0
```

`migration_order` is empty. The checked ledger derives `zero_active_v1=true` only when that list
is empty and `v1-active`, `invalid`, and `unreachable` are all zero; its `inventory_sha256` binds
the exact snapshot. Unregistered filesystem locations were not scanned.

## Rollback and dirty-worktree evidence

The fault-injection unit test
`PlanMigrateTests.test_controlled_apply_rolls_back_byte_exact_on_post_write_failure` passed and
proved byte-identical restoration after a synthetic post-write failure. No real apply failed, so
no fleet target required rollback.

Previously present unrelated dirty files in ERP-SDK, Vaulter and Insiders were checked after the
cutover and remained present. The migrator wrote only the declared plan subtrees; no external
repository was committed or pushed.

## Commands

```text
python3 artifacts/P1/validate-active-layout-inventory.py --write
python3 packages/task/scripts/plan-migrate.py <target> --policy <policy> --dry-run --output <preview> --inventory <inventory>
python3 packages/task/scripts/plan-migrate.py <target> --policy <policy> --apply --preview <preview>
python3 packages/task/scripts/plan-lint.py <target>
python3 packages/task/scripts/plan-views.py state --plan-dir <target> --all --check
python3 packages/task/scripts/plan-views.py status --plan-dir <target> --check
python3 packages/task/scripts/plan-views.py decisions --plan-dir <target> --check
PYTHONPATH=packages/task/lib python3 -m unittest packages.task.tests.test_plan_migrate.PlanMigrateTests.test_controlled_apply_rolls_back_byte_exact_on_post_write_failure
python3 -m json.tool artifacts/P1/layout-migration-ledger-v1.json
```
