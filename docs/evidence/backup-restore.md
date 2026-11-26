# Backup and staging restore rehearsal

P15.01.b archives the PostgreSQL control plane and referenced immutable blobs. The coordinator
holds a read-only repeatable-read transaction while `pg_dump` uses its exported snapshot. The
manifest records row counts, byte sizes, checksums and opaque external dependency identities. The
blob inventory header binds the inventory record length and the checksum of
`snapshot-closure.json`. Verification extracts the final blob references from the dump's table data
and compares them with the archived inventory. Staging checks the complete closure again against
the restored database before writing a runnable profile.

## Rehearsal

The [PostgreSQL recovery suite](../../tests/recovery/test_backup_restore.py) exercises these cases.

| Scenario | Assertion |
|---|---|
| Concurrent writes and a staged upload | The archive contains the final blob visible to the exported snapshot. A missing required blob prevents publication of the complete manifest. |
| Forged inventory and closure, corrupt blob or newer schema | Verification refuses each archive. The emitted manifest validates against the product schema and the normative example. |
| Restore authorization and target isolation | A valid token without `admin.storage` leaves the staging DB and files uncreated. An existing target catalog is refused. |
| Production settings and credentials in the environment | `local up` rejects the restored profile before launching PostgreSQL. `serve` opens the staging DSN with startup migrations disabled. The hook declines access to inherited HTTP credentials and caches. |
| Token rotation and activation interrupted after database commit | Restored bearer tokens and embedded grants are revoked. The marker keeps the profile quarantined across both token-file and activation-receipt failures. |
| Active runs, Git effect and pending webhook | Activation owner-pauses the nonterminal runs once and stops autopilot. The webhook remains pending with zero attempts. Configured vault destinations appear as opaque writer dependencies. |
| Fresh host, real Git checkout and shipped worker | The rebind CLI requires matching repository identity and an existing target branch. The worker uses the verified binding to observe the exact effect. The Git checkout and workflow cursor stay unchanged during inspection. Current prerequisites govern subsequent owner resume and autopilot start. |

## Running the rehearsal manually

Use `skm backup create --output DIR` with the source profile and an unused output directory. Use
`skm backup verify DIR` to check the archive with the installed PostgreSQL tools. Use archives from
the source operator, since archive checksums establish file consistency.

Run `skm backup restore DIR --target-database-url URL --yes` under the source profile with
`admin.storage` on the archived instance. The target requires an unused database name and a
PostgreSQL role that can create it through the server's `postgres` catalog. The report returns the
new profile path. Its `secrets` directory contains the staging DSN, new token pepper and recovery-owner
credential. Use `skm --bootstrap PROFILE storage verify` to check the restored storage.

Register the recovery host with `skm --bootstrap PROFILE host register` and run
`skm --bootstrap PROFILE backup rebind EFFECT_ID --checkout DIR` on that host. A current binding
records the checked-out repository and the effect's target branch. The command reads Git locally
and records verification in staging. Run `skm --bootstrap PROFILE backup activate --yes` to
publish the activation receipt. A fresh worker can then take an effect-specific reconciliation
assignment. Current verified bindings and effect outcomes govern admission, and an owner
explicitly resumes the run or starts autopilot. External delivery remains blocked pending its own
verified configuration.
