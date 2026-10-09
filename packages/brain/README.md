# brain

The Obsidian vault module of the ecosystem. It finds the vault of the machine, finds the folder of a
project inside it, and checks that both are healthy. It is a small command-line tool built on the `aicore`
foundation (Python 3.9+, standard library only).

It covers vault lookup, the project catalog, document sync, `doctor`, and the subscriber that writes a vault note
when a plan is closed.

## Commands

| Command | What it does |
| --- | --- |
| `brain vault [--json] [--project DIR]` | Print the vault path and where it was found (exit 1 when there is none). |
| `brain project [--project DIR] [--json]` | Print the vault folder of a project (exit 1 when the project has none). |
| `brain docs integrate --project DIR [--dry-run]` | Apply the document sync settings of a project: pull, then write the manual script. |
| `brain docs pull --project DIR [--dry-run]` | Copy vault documents into the project. |
| `brain docs push --project DIR [--dry-run] [--force]` | Copy project documents into the vault. |
| `brain docs script --project DIR` | Write `.claude/sync-brain.sh` (mode 0755). |
| `brain note --event FILE\|- [--project DIR] [--dry-run] [--json]` | The subscriber of `planner.plan.closed`: write the note of a closed plan (see below). |
| `brain doctor [--json]` | Check the vault, the configuration, the notes folder and the subscription; `--json` prints `check-result/v1` documents. |
| `brain version` | Print the version and the library path. |

`--project` defaults to the project that contains the working directory (`brain note` has no default: without
`SKM_PROJECT_ROOT` or `--project` the event belongs to the machine). Exit codes: 0 success, 1 failure
(`brain: <CODE>: <message>` on stderr), 2 usage error; `brain note` also uses 65 and 75 (below).

## Finding the vault

The first rung that is set wins:

1. `brain.vault_path` of the configuration (machine file, `--config` file or flag; a project file cannot set it).
2. The deprecated `memory_brain` object (not a plain string) of the project's `.swissknife.json`, with its `path`.
3. The deprecated `MAIND_BRAIN_VAULT` environment variable.
4. `~/Vaults/Brain`, only when it contains an `.obsidian` folder.

A path that is set but does not exist is reported as `VAULT_MISSING`; it is never replaced by a lower rung.
Set the vault once per machine:

```bash
aicore config set brain.vault_path ~/Documents/MyVault --machine
```

## Finding the project folder

`brain project` matches the project root (compared by real path, `~` expanded) against

1. the generated catalog `<vault>/.projects.json`, when present, then
2. control notes `<vault>/<catalog.projects_dir>/<category>/<Name>/<Name>.md` (or one level less) whose
   frontmatter has `repo: <path to the project>`.

The result says which source matched (`via`: `catalog` or `control-note`).

## Document sync

Documents move between a project and the vault by glob patterns (`docs.patterns`, relative to both roots; by default
`docs/**/*.md` and `README.md`):

- `pull` copies vault files into the project. It only adds or updates files and never deletes.
- `push` copies project files into the vault. A vault file with the same content is left alone; one with different
  content is not replaced and is reported as `DOCS_CONFLICT` (exit 1) unless you pass `--force`. Other files are
  still copied. Nothing is deleted.
- `script` writes `.claude/sync-brain.sh`, a plain bash copy of the same patterns for use outside the tool
  (`bash .claude/sync-brain.sh [pull|push|bidirectional] [--force]`). Its `push` also preserves changed vault
  files and exits 1 with `DOCS_CONFLICT`; pass `push --force` to replace them. Identical files are left alone.
- `integrate` is what `skiller integrate` runs: when sync is on it pulls (for `pull` and `bidirectional`), then writes
  the script; otherwise it prints `doc-sync is off`. `--dry-run` prints what it would do and writes nothing.

Sync is on with `docs.enabled = true`, or, for existing projects, when `.swissknife.json` has a `memory_brain`
object (a deprecation warning is printed; the object's `path` and `sync.direction` / `sync.patterns` apply). A key
set in the configuration always wins over the legacy object. A string `memory_brain` names a memory brain and does
not enable sync. `pull`, `push` and `script` work whether or not sync is enabled.

## Notes from events

The module subscribes to the event `planner.plan.closed` (subscription `brain:plan-notes`, declared in `unit.json`;
the event is delivered by `aicore`, which runs `brain note --event -` with the event on standard input). For each
closed plan it writes one Markdown note into the vault and then emits `brain.note.created`
(`{"note", "plan_id", "event_id"}`, caused by the closing event).

**What is read.** The `event/v1` envelope (`specversion` `1.0`) and its `data`: `plan_id` and `title` are required;
`short_id`, `status`, `goal`, `closed_at` (RFC 3339), `repository`, `phases` (`{id, title, status}`) and `counts`
(`items`, `done`, `done_with_deviations`, `cancelled`) are optional; unknown fields are ignored. The expectation is
recorded in `tests/fixtures/events/`. Events of another type are skipped.

**Where it goes.** Into the folder of the project in the vault, in `notes.folder` (default `Ecosystem/Plans`), when the
project is found (see above); otherwise into `notes.fallback_folder` from the root of the vault. The project is
`SKM_PROJECT_ROOT` (set by `aicore` for a project journal) or `--project`. The file is named
`<YYYY-MM-DD> <plan id> closed <first 8 characters of the event id>.md`; the date is the UTC date of `closed_at`
(the event time when absent). `notes.folder` cannot be inside `docs`, `docs-public` or `plans`, so a two-way document
sync never carries a note into the repository.

**What the answer means.** Standard output is one JSON object: `{"status": "ok", "note": "<path from the vault root>"}`
for a new note, or `{"status": "skipped", "reason": ...}` with `NOTES_DISABLED`, `EVENT_TYPE_IGNORED`,
`VAULT_NOT_CONFIGURED` (a machine without a vault collects no failed deliveries), `DUPLICATE_EVENT` or `DRY_RUN`.
Exit 65 (`EVENT_DATA_INVALID`) means the event itself is wrong, exit 75 (`VAULT_UNAVAILABLE`, `NOTE_IO`,
`LEDGER_LOCKED`, an invalid configuration) a temporary failure; `aicore` keeps the event, retries it on the next
delivery and sets it aside as a dead letter after the configured number of attempts (`aicore events replay
brain:plan-notes --event ID` delivers it again).

**Writing is idempotent and never destroys anything.** `aicore` delivers at least once, so a repeat is normal:

- A ledger `<state>/brain/notes.jsonl` (one line per note: event id, path, vault, time) is checked under a lock
  (`notes.lock`) before anything is written; a repeated or replayed event answers `DUPLICATE_EVENT` and writes nothing.
- A note appears whole: it is written to a temporary file in the same folder and hard-linked to its name, which fails
  if the name exists. An existing file in the vault is never overwritten or removed; if a file of a person has the
  same name, the note is written as `<name> (2).md`.
- If the ledger is lost, a note that is still where it was written is recognised by the `event_id` in its frontmatter.
- A note that you **move or rename** is not created again as long as the ledger exists. If you move a note *and*
  delete the ledger (or reset the machine state), a replay of the event creates a second note; delete it or keep the
  ledger.

**Switching it off.** `brain.notes.enabled = false` makes every event a skip. To stop the delivery itself, put
`[aicore.subscriptions."brain:plan-notes"]` with `enabled = false` into the configuration; `brain doctor` reports a
switched-off subscription (`brain.subscription`) as a warning. Check the chain end to end in a throwaway home with
`scripts/e2e-plan-note.sh VAULT PROJECT`.

## Configuration

Settings live in the `[brain]` table of the ecosystem configuration; see [`config.example.toml`](config.example.toml)
for every key (generated from [`configs/config.schema.json`](configs/config.schema.json)) and run
`aicore config explain brain` to see where each value comes from.

| Key | Default | Meaning |
| --- | --- | --- |
| `vault_path` | unset | Vault root; machine-wide only. |
| `catalog.projects_dir` | `05-Projects` | Folder of the control notes, relative to the vault. |
| `docs.enabled`, `docs.direction`, `docs.patterns` | `false`, `pull`, `["docs/**/*.md", "README.md"]` | Document sync of a project. |
| `notes.enabled`, `notes.folder`, `notes.fallback_folder` | `true`, `Ecosystem/Plans`, `Ecosystem/Plans` | Notes written for ecosystem events. |

`notes.folder` must be a relative path without `..` and outside `docs`, `docs-public` and `plans`.

## Development

```bash
bash scripts/test.sh       # unit tests against a throwaway HOME and a copy of the fixture vault
bash scripts/validate.sh   # structure checks, then the tests
```

The tests never touch a real vault or the real home directory. The module imports only the standard
library and `aicore`; other modules reach it through its command line.
