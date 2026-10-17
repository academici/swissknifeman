# gui security notes: integrity and supply chain

What the hardening of the last phase guarantees and what it does not. The access model (session secret, cookies,
Host/Origin, confirmations) is in `api.md`; the plugin model in `plugins.md`.

## `gui state check|rebuild`

- `gui state check [--json]` opens `gui.db` read-only: `PRAGMA integrity_check`, `foreign_key_check`, `user_version`
  against the version this gui knows, and the row count of every table. Exit 0 when all is well, 1 otherwise. It never
  writes and may run while the backend runs.
- `gui state rebuild [--dry-run] [--json]` takes the backend lock first: with a running backend it stops with
  `BACKEND_RUNNING` and changes nothing. Then, in this order: a backup `gui.db.bak-<UTC>` (SQLite backup API, mode 0600),
  a new database next to the old one (`.gui.db.new-<pid>`, all migrations), every table copied with `INSERT ... SELECT`,
  a comparison of both files row by row (same count, no row on one side only), `integrity_check` and `foreign_key_check`
  of the new file, a checkpoint of the old WAL, `os.replace`. Any error before the swap removes the new file and leaves
  `gui.db` byte for byte as it was; the backup stays.
- The operator's decisions (plugins, plugin events, grants) live only in SQLite (decision D22). The rebuild copies them like
  every other table and fails rather than lose a row. `--dry-run` reads the old file and writes nothing (it may leave
  the `-wal`/`-shm` files of a read-only WAL reader; `gui.db` keeps its bytes and mtime).
- A database that SQLite cannot read at all cannot be rebuilt: the command fails, `gui.db` stays, restore the backup of
  an earlier rebuild or move the file away (the canonical SKM files are the source of truth, the index is created again).
  A database written by a newer gui is refused (`STATE_INCOMPATIBLE`).
- Run logs stay in `runs/<id>/`; a run row without a log folder is not deleted.

## Digest of the sidecar

`sidecar/build.sh` writes `gui-backend.digest` into the onedir folder: `{v, version, files: [{path, sha256}], tree}`,
`files` sorted and without the digest file, `tree` the sha256 of that list. `gui serve --sidecar` checks the tree before
it reads the handshake and before any socket exists; the files are read in blocks of 1 MiB (500 files of 4 KiB take well
under 2 s). A changed, added or removed file, a changed symlink target, or a damaged digest file prints
`SIDECAR_TAMPERED: <file> (<reason>)` to stderr and exits 3.

Limits, stated plainly:

- The digest is **not signed**. An attacker who can write the tree can rewrite the digest file too. It detects accidents
  and partial tampering (a replaced library, an added file), not a full replacement of the installation.
- If `gui-backend.digest` is **absent**, the check is skipped silently: that is how a run from sources works. Deleting the
  file therefore disables the check. The application bundle is protected by the platform signature and the updater
  signature (owner steps, `desktop-release.md`), which is what covers a swapped tree.
- Only a frozen sidecar is checked (`sys.frozen`); `python3 -m gui.sidecar_digest verify DIR` checks any folder by hand.

## SBOM

`python3 packages/gui/scripts/sbom.py [--out FILE]` writes CycloneDX 1.5 JSON (stdlib only): one component per entry of
`requirements.lock` (pypi, sha256), of `frontend/package-lock.json` (npm, integrity), of `desktop/src-tauri/Cargo.lock`
(cargo, checksum) and the digest of a built sidecar. Without a `Cargo.lock` (the owner creates it at the first build) the
crates are read from the `Cargo.toml` requirements and marked `skm:locked=false`. The output is sorted, the serial number
derives from the content and the only time is `SOURCE_DATE_EPOCH` (default 1970-01-01T00:00:00Z), so two runs are
byte-equal.

## Performance budget

`npm --prefix packages/gui/frontend run budget` after `build`: initial JS ≤ 190 kB gzip, initial CSS ≤ 12 kB, every JS
chunk ≤ 400 kB, and no initial script carries xterm (the terminal loads its own chunk on `/terminal`).

## Accessibility

Dialogs take the focus when they open and give it back to the element that had it when they close; Escape closes the ones
that can be cancelled safely (not the conflict dialogs, where both choices change data). Navigations carry names. The test
`frontend/src/a11y.test.tsx` renders the real screens and checks names, ids, one `h1`, heading order and landmarks.

## Not claimed

Plugin processes of the GUI run without a sandbox, so permissions stay advisory (decision D23); the terminal is a shell with
the rights of the backend user and is off by default (`[gui.terminal] enabled`).
