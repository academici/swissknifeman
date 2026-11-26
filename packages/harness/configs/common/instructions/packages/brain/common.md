<!-- instruction:brain.identity -->
## brain.identity
`brain` is the ecosystem module for the Obsidian vault: it finds the vault, syncs project documents with it and writes notes from ecosystem events; the vault belongs to a person, so brain adds notes and never rewrites their files.
<!-- instruction:brain.layout -->
## brain.layout
Keep `bin/brain` as the launcher, `lib/brain/` as stdlib-only logic on `aicore`, `skills/` for the module's own skills, and temporary-directory tests with the synthetic vault in `tests/fixtures/vault`.
<!-- instruction:brain.module-boundaries -->
## brain.module-boundaries
Import only `brain` and `aicore`; reach planner, maind and skiller through events and their command lines, and take the vault path from `brain vault` resolution (configuration `brain.vault_path`), never from a hardcoded path.
<!-- instruction:brain.vault-safety -->
## brain.vault-safety
Write to the vault only through `brain note` (one new note per event, idempotent by event id, never overwriting a file) and an explicit `brain docs push`; keep notes outside the synced `docs`, `docs-public` and `plans` folders.
<!-- instruction:brain.engineering-invariants -->
## brain.engineering-invariants
Keep Python 3.11 compatibility (aicore.MIN_PYTHON), English diagnostics, `BrainError` codes and the subscriber answer contract: one JSON object on stdout, exit 65 for invalid event data and 75 for temporary failures.
<!-- instruction:brain.validation-release -->
## brain.validation-release
Before a commit run `bash scripts/test.sh` and `bash scripts/validate.sh`, then `python3 scripts/ecosystem-units.py check` and `python3 scripts/ecosystem-units.py standalone brain` from the hub root; use Russian Conventional Commit messages.
