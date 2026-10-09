# brain

The Obsidian vault module of the ecosystem. It finds the vault of the machine, finds the folder of a
project inside it, and checks that both are healthy. It is a small command-line tool built on the `aicore`
foundation (Python 3.9+, standard library only).

This is the first version of the module: it covers vault lookup, the project catalog, document sync and `doctor`.
Notes written from ecosystem events are a separate command that arrives later.

## Commands

| Command | What it does |
| --- | --- |
| `brain vault [--json] [--project DIR]` | Print the vault path and where it was found (exit 1 when there is none). |
| `brain project [--project DIR] [--json]` | Print the vault folder of a project (exit 1 when the project has none). |
| `brain docs integrate --project DIR [--dry-run]` | Apply the document sync settings of a project: pull, then write the manual script. |
| `brain docs pull --project DIR [--dry-run]` | Copy vault documents into the project. |
| `brain docs push --project DIR [--dry-run] [--force]` | Copy project documents into the vault. |
| `brain docs script --project DIR` | Write `.claude/sync-brain.sh` (mode 0755). |
| `brain doctor [--json]` | Check the vault, the configuration and the notes folder; `--json` prints `check-result/v1` documents. |
| `brain version` | Print the version and the library path. |

`--project` defaults to the project that contains the working directory. Exit codes: 0 success, 1 failure
(`brain: <CODE>: <message>` on stderr), 2 usage error.

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
  (`bash .claude/sync-brain.sh [pull|push|bidirectional]`).
- `integrate` is what `skiller integrate` runs: when sync is on it pulls (for `pull` and `bidirectional`), then writes
  the script; otherwise it prints `doc-sync is off`. `--dry-run` prints what it would do and writes nothing.

Sync is on with `docs.enabled = true`, or, for existing projects, when `.swissknife.json` has a `memory_brain`
object (a deprecation warning is printed; the object's `path` and `sync.direction` / `sync.patterns` apply). A key
set in the configuration always wins over the legacy object. A string `memory_brain` names a memory brain and does
not enable sync. `pull`, `push` and `script` work whether or not sync is enabled.

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
