# Guide

## Finding the vault

The first rung that is set wins:

1. `brain.vault_path` of the configuration (machine file, `--config` file or flag; a project file cannot set it).
2. The deprecated `memory_brain` object (not a plain string) of the project's `.swissknife.json`, with its `path`.
3. The deprecated `MAIND_BRAIN_VAULT` environment variable.
4. `~/Vaults/Brain`, only when it contains an `.obsidian` folder.

A path that is set but does not exist is reported as `VAULT_MISSING`; it is never replaced by a lower rung. Set the
vault once per machine:

```bash
aicore config set brain.vault_path ~/Documents/MyVault --machine
brain vault            # prints the path and where it was found
brain doctor           # checks the vault, the configuration and the notes folder
```

`brain project` finds the vault folder of the current project. It matches the project root against the generated
catalog `<vault>/.projects.json` when present, then against control notes
`<vault>/<catalog.projects_dir>/<category>/<Name>/<Name>.md` whose frontmatter has `repo: <path to the project>`. The
result says which source matched (`via`: `catalog` or `control-note`).

## Document sync

Documents move between a project and the vault by glob patterns (`docs.patterns`, relative to both roots; by default
`docs/**/*.md` and `README.md`):

- `brain docs pull` copies vault files into the project. It only adds or updates files and never deletes.
- `brain docs push` copies project files into the vault. A vault file with the same content is left alone; one with
  different content is not replaced and is reported as `DOCS_CONFLICT` (exit 1) unless you pass `--force`. Other files
  are still copied. Nothing is deleted.
- `brain docs script` writes `.claude/sync-brain.sh`, a plain bash copy of the same patterns for use outside the tool.
- `brain docs integrate` is what `skiller integrate` runs through its host command: when sync is on it pulls (for
  `pull` and `bidirectional`), then writes the script; otherwise it prints `doc-sync is off`.

Sync is on with `docs.enabled = true`, or, for existing projects, when `.swissknife.json` has a `memory_brain` object
(a deprecation warning is printed; the object's `path`, `sync.direction` and `sync.patterns` apply). A key set in the
configuration always wins over the legacy object. A string `memory_brain` names a memory brain and does not enable sync.
`--dry-run` prints what would happen and writes nothing.

## Notes from events

The module subscribes to `planner.plan.closed` (subscription `brain:plan-notes`, declared in `unit.json`). For each
closed plan it writes one Markdown note into the vault and then emits `brain.note.created`
(`{"note", "plan_id", "event_id"}`, caused by the closing event). Only `plan_id` and `title` of the event data are
required; unknown fields are ignored, so the emitter can grow its data without breaking the subscriber.

The note goes into the folder of the project in the vault, in `notes.folder` (default `Ecosystem/Plans`), when the
project is found; otherwise into `notes.fallback_folder` from the root of the vault. `notes.folder` cannot be inside
`docs`, `docs-public` or `plans`, so a two-way document sync never carries a note into the repository. The file is named
`<YYYY-MM-DD> <plan id> closed <first 8 characters of the event id>.md`.

**Repeats are safe.** `aicore` delivers at least once, so a repeat is normal:

- A ledger in the state folder is checked under a lock before anything is written; a repeated or replayed event answers
  `DUPLICATE_EVENT` and writes nothing.
- A note appears whole (temporary file, then a hard link that fails if the name exists). An existing file in the vault
  is never overwritten or removed; a clash gets a ` (2)` suffix.
- If the ledger is lost, a note that is still where it was written is recognised by the `event_id` in its frontmatter.
- A note that you move or rename is not created again as long as the ledger exists. If you move a note *and* delete the
  ledger, a replay creates a second note; delete it or keep the ledger.

**Switching it off.** `brain.notes.enabled = false` makes every event a skip. To stop the delivery itself, set
`[aicore.subscriptions."brain:plan-notes"] enabled = false`; `brain doctor` reports a switched-off subscription as a
warning. A machine without a vault skips the event, so it collects no failed deliveries.

## Configuration

Settings live in the `[brain]` table of the ecosystem configuration; `aicore config explain brain` shows where each
value comes from and `config.example.toml` lists every key.

| Key | Default | Meaning |
| --- | --- | --- |
| `vault_path` | unset | Vault root; machine-wide only. |
| `catalog.projects_dir` | `05-Projects` | Folder of the control notes, relative to the vault. |
| `docs.enabled`, `docs.direction`, `docs.patterns` | `false`, `pull`, `["docs/**/*.md", "README.md"]` | Document sync of a project. |
| `notes.enabled`, `notes.folder`, `notes.fallback_folder` | `true`, `Ecosystem/Plans`, `Ecosystem/Plans` | Notes written for ecosystem events. |

`notes.folder` must be a relative path without `..` and outside `docs`, `docs-public` and `plans`.

## Moving from the old setup

- Set `brain.vault_path` on each machine instead of `memory_brain` in `.swissknife.json` or `MAIND_BRAIN_VAULT`; both
  still work and print a deprecation warning.
- The skill `brain-locator` now comes from the plugin `brain`; its path ladder starts with `brain vault --json`.
- `scripts/cache-brain-docs.sh` moved here from `maind`.
