# Repository configs

Every config in the repository has **one owner** and **at least one consumer**.
The inventory lives in [`configs/config-inventory.json`](../../configs/config-inventory.json);
this page does not copy it.

## Rule

- Owner: `root`, `core`, or a `packages/*` directory. The canonical file lives in the owner's tree.
- Consumer: existing code, script or workflow that reads the file (or `user:<description>` for examples).
- No duplicated copies: a second copy is allowed only as a generated file with a `--check`.
- Shared paths resolve through `core.shared_config_path(name)`, which returns the owner path without fallback.

## Check

`python3 scripts/test-config-inventory.py` runs in CI hygiene. It fails when a tracked config in
`scope` has no entry, an entry matches nothing, an owner is invalid, or a consumer is missing or does not reference the file.

## Add a config

1. Put the file in the owner's tree.
2. Add an entry (`path` or `glob`, `owner`, `consumers`, `released`; optional `dynamic`, `note`) to the inventory.
3. If other packages read it, register the name in `core/config_paths.py`.
4. Run the check above.
