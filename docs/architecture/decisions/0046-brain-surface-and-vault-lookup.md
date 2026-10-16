# ADR 0046: The surface of brain and the vault lookup

## Status

Accepted

## Context

The module `brain` needs a command line, a configuration and a way to find the vault of the machine. The vault already
has an external command line with the names `sync`, `status`, `list`, `hook` and `watch`, and `maind` and the old
`.swissknife.json` have their own ways to find it.

## Decision

- **Commands.** `bin/brain` has `vault`, `project`, `docs`, `note`, `doctor` and `version`; none of the external names.
- **Configuration.** The `[brain]` table: `vault_path` (machine-wide only), `catalog.projects_dir`, `docs.*`, `notes.*`.
- **Ladder.** `brain.vault_path`, then the deprecated `memory_brain` object of `.swissknife.json`, then the deprecated
  `MAIND_BRAIN_VAULT`, then `~/Vaults/Brain` with an `.obsidian` folder. The deprecated sources print a warning. A path
  that is set but missing is `VAULT_MISSING`, not a step down the ladder.
- **Plugin.** The Claude Code plugin `brain` delivers the skill `brain-locator`.
- **Maind unchanged.** `maind` keeps its own lookup until it moves onto `aicore`.

## Alternatives considered

- Move `maind` onto `brain vault` and name the sync command `brain sync` at once: rejected, it changes `maind` outside
  its phase and clashes in meaning with the two-way sync of the external command line.

## Consequences

- Two implementations of the vault lookup exist until `maind` is moved; both follow the same ladder.
- The vault path is a machine setting, as the architecture requires.

## Supersedes

Refines [ADR 0007](0007-brain-module-scope.md).
