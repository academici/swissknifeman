# Command reference

`brain <command> [options]`. `--project DIR` defaults to the project that contains the working directory (`brain note`
has no default: without `SKM_PROJECT_ROOT` or `--project` the event belongs to the machine).

| Command | What it does |
| --- | --- |
| `brain vault [--json] [--project DIR]` | Print the vault path and where it was found (exit 1 when there is none). |
| `brain project [--project DIR] [--json]` | Print the vault folder of a project (exit 1 when the project has none). |
| `brain docs integrate --project DIR [--dry-run]` | Apply the document sync settings of a project: pull, then write the manual script. |
| `brain docs pull --project DIR [--dry-run]` | Copy vault documents into the project. |
| `brain docs push --project DIR [--dry-run] [--force]` | Copy project documents into the vault. |
| `brain docs script --project DIR` | Write `.claude/sync-brain.sh` (mode 0755). |
| `brain note --event FILE\|- [--project DIR] [--dry-run] [--json]` | The subscriber of `planner.plan.closed`: write the note of a closed plan. |
| `brain doctor [--json]` | Check the vault, the configuration, the notes folder and the subscription; `--json` prints `check-result/v1` documents. |
| `brain version` | Print the version and the library path. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success (including a skipped event). |
| 1 | Failure; `brain: <CODE>: <message>` on standard error. |
| 2 | Usage error. |
| 65 | `brain note`: the event data is wrong (`EVENT_DATA_INVALID`); not retried, set aside as a dead letter. |
| 75 | `brain note`: a temporary failure (`VAULT_UNAVAILABLE`, `NOTE_IO`, `LEDGER_LOCKED`, an invalid configuration); retried by the next delivery. |

## Error codes

`VAULT_NOT_FOUND`, `VAULT_MISSING`, `PROJECT_NOT_IN_VAULT`, `CATALOG_INVALID`, `CATALOG_AMBIGUOUS`, `CONFIG_INVALID`,
`CONFIG_NOTES_FOLDER`, `DOCS_CONFLICT`, `EVENT_DATA_INVALID`, `VAULT_UNAVAILABLE`, `NOTE_IO`, `LEDGER_LOCKED`. The
warnings `BRAIN_LEGACY_CONFIG` and `BRAIN_LEGACY_ENV` mark the deprecated vault sources.

## Answer of `brain note`

Standard output is one JSON object: `{"status": "ok", "note": "<path from the vault root>"}` for a new note, or
`{"status": "skipped", "reason": ...}` with `NOTES_DISABLED`, `EVENT_TYPE_IGNORED`, `VAULT_NOT_CONFIGURED`,
`DUPLICATE_EVENT` or `DRY_RUN`.
