# ADR 0047: Document sync moves to brain and is called through a host command

## Status

Accepted

## Context

The sync of project documents with the vault lived in `skiller` (`brain_sync`) and ran inside `skiller integrate`. A
module may reach another one only through a bridge or an event, so `skiller` cannot import `brain`.

## Decision

- **Move with parity.** The code moves to `brain` as `brain docs integrate|pull|push|script`; behaviour of the old
  sync is kept, with two corrections: `pull` and `push` need a vault (`VAULT_NOT_FOUND`) instead of copying nothing,
  and the generated script also matches a file directly below the folder for `/**/` patterns.
- **Host command.** The step of `skiller integrate` runs `brain docs integrate` as the host command `brain_docs`
  (the program from `SKM_BRAIN_BIN` or `PATH`), the same mechanism that `harness` uses. Without `brain` installed the
  step is skipped with a warning.
- **Settings.** `[brain.docs]` of the configuration; the legacy `memory_brain` object still turns sync on, with a
  warning, until the file is migrated.
- **Safety.** `push` is an explicit command: it leaves a vault file with different content alone
  (`DOCS_CONFLICT`) unless `--force`, copies the other files, and never deletes.

## Alternatives considered

- Keep a copy in `skiller`: rejected, two owners of one piece of code.

## Consequences

- `skiller` has no import of `brain`; the boundary check stays clean.
- A machine without `brain` loses document sync in the setup wizard until `brain` is installed.

## Supersedes

None.
