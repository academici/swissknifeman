# Review of P7.4 (commit d4017257) - round 1

Reviewer: grok/grok-4.7/500k/high, headless read-only session 01a12047-edf0-76e0-99f7-84e16da3a01a (contextWindowTokens 500000, reasoning_effort high, from the session record).
Executor verification: each finding was reproduced by the executor's own run (new failing tests / document text) before correction.

**RED.** Three confirmed defects in `d4017257`. Unrelated vault files are left untouched. A symlinked vault plus `.projects.json` never completes a note, and the no-hardlink fallback can publish a partial note or a second file.

### 1. High — catalog path and the ledger path are not the same path

`packages/brain/lib/brain/notes.py:288` (called from 295 and 299). `packages/brain/lib/brain/cli.py:274`.

`catalog.find_project` stores `os.path.realpath` of the `.projects.json` folder. The vault root kept by `resolve_vault` is only `os.path.abspath`. After the note is created, `record()` does `note.relative_to(vault)`. That raises `ValueError` when the vault path contains a symlink. `main` only catches `BrainError` and `ConfigError`, so the subscriber exits 1 with a traceback and empty stdout. The ledger line is not written, so every retry raises in the same place. `brain.note.created` is never emitted. After the default 3 attempts the event is a dead letter. `replay --event` fails the same way.

A control-note match does not realpath the folder, so the same symlink vault succeeds if `.projects.json` is absent. No test uses a non-canonical vault path with a catalog entry.

Reproduction (throwaway `HOME`, vault symlink, `.projects.json` `vault_path` `05-Projects/Demo` pointing at the project):

```text
aicore events emit --source planner --type planner.plan.closed \
  --subject demo-plan --data-file data.json --project "$PROJECT" --delivery sync
```

```text
deliveries.jsonl: "outcome": "failed", "exit": 1, "code": "PROCESS_EXIT"
stderr_tail: ValueError: '.../vault-real/05-Projects/Demo/Ecosystem/Plans/2026-10-09 demo-plan closed f2ef33d7.md' is not in the subpath of '.../vault-link'
status after 1 attempt: lag 1, pending.attempts 1, last_error PROCESS_EXIT
status after 3 attempts: lag 0, dead_letters 1, pending null
vault md count: 1
brain.note.created: {"events": []}
replay brain:plan-notes --event f2ef33d7ab1e48bb8cceaf0c7fb40a6e → exit 1, dead_letters stays 1
```

Suggested fix: store the ledger path with `vault_relative` (realpath on both sides) and key ledger rows by the vault realpath. The repair branch at line 295 needs the same change.

### 2. Medium — no-hardlink fallback can commit a partial note or a second file

`packages/brain/lib/brain/notes.py:256-266`.

The temp file is written in a loop until `os.write` returns every byte. The fallback (`os.link` raises `EPERM` / `ENOTSUP` / `ENOSYS` / `EMLINK`) does one `os.write` and treats any positive count as success. A short write is recorded in the ledger and later deliveries return `DUPLICATE_EVENT`, so the truncated note stays. If that write raises, the `O_EXCL` file is left in place (only the temp name is unlinked). It has no `event_id`, so the retry skips it as a foreign file and writes `name (2).md`. `test_no_hard_links_falls_back_to_an_exclusive_create` only covers a full successful write.

Reproduction: `os.link` raises `EPERM`, and the second `os.write` of the note body returns 160 bytes. `notes.handle` on a canonical vault with no project:

```text
first: status ok, file size 160
file text ends at: event_source: "urn:swissknifeman:module:planner"
retry: skipped DUPLICATE_EVENT, size still 160, one md file
```

Same setup with the second note `os.write` raising `ENOSPC`:

```text
first: BrainError NOTE_IO: the note cannot be written: no space left on device
file left behind: ...closed 01234567.md, size 0
retry: status ok, note ...closed 01234567 (2).md
md files: both the empty file and the (2) note
```

Suggested fix: loop `os.write` until the full text is stored, and `fsync` before returning true. If that write fails, unlink the file this call created with `O_EXCL` before raising, so the retry reuses the same name.

### 3. Medium — a pre-existing vault file at the temp name is deleted

`packages/brain/lib/brain/notes.py:238-239`.

If `O_EXCL` on `N.tmp-<pid>` raises `FileExistsError`, that path is unlinked and replaced. The occupant does not have to be a temp file this process created. `test_a_stale_temporary_file_of_the_same_process_is_replaced` expects this for a leftover `half` file, so a person’s file at that name is removed too.

Reproduction: write `USER-VAULT-FILE do not delete` to `<note-path>.tmp-<pid>`, then `notes.handle` for that event.

```text
victim before: .../2026-10-09 demo-plan closed 01234567.md.tmp-<pid>
status ok Ecosystem/Plans/2026-10-09 demo-plan closed 01234567.md
victim exists False
```

Suggested fix: on `FileExistsError`, pick a new temp name (`N.tmp-<pid>-<token>`) with `O_EXCL`. Leave the existing directory entry in place.
