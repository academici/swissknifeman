# Local re-review of the round-1 corrections (P7.4 + P7.5) - round 2

Reviewer: grok/grok-4.7/500k/high, headless read-only session 01a12059-b751-7160-a02c-ce231de59464 (contextWindowTokens 500000, reasoning_effort high, from the session record).
Executor verification: both findings are valid; corrected (`_unlink_if_ours`, `_ledger_name`) with two new tests (brain 207 tests OK). The review budget (two completed rounds, one owning correction) is now spent; no third round without a new owner request.

**RED.** The three round-1 fixes hold for the cases they targeted, and the brain tests and the harness check pass. Two regressions remain in the new write path.

## Findings

### 1. Medium — a failed in-place write unlinks whatever name is at the note path

`packages/brain/lib/brain/notes.py:275`

On `ENOSPC` (and any other error from `_write_all`), the fallback deletes `path` by name. The ledger lock stops another `brain note` from creating that name. It does not stop anything else. If the exclusive file is renamed away and another file is created at the same name before the `unlink`, that other file is removed.

Reproduction: hard links raise `EPERM`, the temporary write completes, and the in-place `os.write` renames the new file to `*.ours`, writes `USER-REPLACEMENT do not delete` at the note path, then raises `ENOSPC`.

```text
raised NOTE_IO: the note cannot be written: no space left on device
left ['2026-10-09 2026.01.15-DEMO-PLAN closed 0f1e2d3c.md.ours']
```

The replacement file is gone. Unlink only when the directory entry is still the inode this call opened.

### 2. Medium — an existing note whose real path is outside the vault is stored as `null` and appended again on every delivery

`packages/brain/lib/brain/notes.py:301`, read back at `203–208`, returned at `380`

`record()` stores `vault_relative()`. That returns `None` when the directory entry is inside the vault and the file it points at is not. `json.dumps` writes `"note": null`. `_read_ledger` keeps a line only when `note` is a string, so the line never deduplicates. Each delivery appends another null line. The answer omits `note`. The user file and the symlink stay in place.

A catalog folder outside the vault is fine: the note is the fallback path `Ecosystem/Plans/...`, one ledger line, and the outside directory stays empty. A symlink to another file inside the vault stores that file's relative path and does not grow the ledger.

Reproduction: a user file occupies the note name, and `name (2).md` is a symlink to an outside file whose frontmatter has this event id.

```text
result {'status': 'skipped', 'reason': 'DUPLICATE_EVENT'}
ledger [{"event_id": "0f1e2d3c4b5a69788796a5b4c3d2e1f0", "note": null, ...}]
retry {'status': 'skipped', 'reason': 'DUPLICATE_EVENT'}
ledger lines 2
user file unchanged; symlink still True
```

Before this change, `Path.relative_to` on that same entry returned `Ecosystem/Plans/... (2).md`. If `vault_relative` is `None`, keep a lexical path that is still inside the vault, and do not append a null `note`.

## Checked, and holding

- Symlinked vault plus `.projects.json`: one note, ledger `note` is `05-Projects/03-Packages/Demo/Ecosystem/Plans/...`, retry is `DUPLICATE_EVENT` with one line. Opening the same vault by its real path adds a second ledger line and does not write a second file.
- Short in-place writes finish the note file (602 bytes) and leave no `.tmp-` file. A pre-existing `*.tmp-<pid>` and a colliding `*.tmp-<pid>-deadbeef` are left untouched. The failed-write and link-error paths in `test_notes.py` also assert no temporary files.
- Under the ledger lock, the 2-process test writes 20 notes and 20 ledger lines. `_append_ledger` is still one `os.write` (I6). The only other `os.write` in `packages/brain/lib` is that append. `relative_to` remains in `docs.py` and `cli.py` for document sync, not for the note ledger. No other `.tmp-` creator exists under `packages/brain/lib`.
- `bash packages/brain/scripts/test.sh`: `tests: OK (Ran 205 tests)`.
- Contract lines 10 and 29 now say seven package scopes and eight scope IDs, matching the eight-row scope table. `harness instructions check` in sandbox `/tmp/skm-sandbox-rr3626181` (removed afterward): `OK — 32 targets`, all `clean/noop`.
