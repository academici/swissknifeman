# ADR 0074: swissknifeman install with profiles; install.sh is a wrapper

## Status

Accepted

## Context

`install.sh` looped over four named modules. A user could not choose a smaller set, and modules without an installer
(planner, brain, orch) were not installed at all.

## Decision

- **Manifest.** `unit/v1` gains, as a minor change, `provides.install`: an argv run from the module root that accepts
  `--bin-dir DIR` and `--force`.
- **Profiles.** `configs/install-profiles.json` (`install-profiles/v1`, schema `configs/install-profiles.schema.json`):
  `minimal` (aicore, skiller, planner), `standard` (the default; adds harness, brain, orch) and `full` (adds maind and
  analyst). A profile lists module ids and optional per-module installer arguments.
- **Order and checks.** Modules install in `requires` order; a profile that omits a required module is refused
  (`PROFILE_REQUIRES_MISSING`). `--units a,b` installs a list plus its requires.
- **Steps.** A module with `provides.install` runs it; a module with only `provides.cli` gets symlinks; the last step is the
  `swissknifeman` link. A link made earlier by the hub is replaced silently, a foreign file needs `--force`.
- **Dry run.** `--dry-run` prints the plan and writes nothing; `--json` prints `umbrella-install/v1`.
- **install.sh.** A thin wrapper over `install --profile full` with the former flags.

## Alternatives considered

- Profiles in code: rejected, a profile is a choice of the user and the project, not logic.
- An interactive installer: rejected, the install must be scriptable and testable in a temporary `HOME`.

## Consequences

- Every module is installable with one command; a custom profile is a data edit.
- A module that needs an installer declares `provides.install` instead of being named in the root.

## Supersedes

None.
