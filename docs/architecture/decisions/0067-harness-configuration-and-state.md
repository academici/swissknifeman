# ADR 0067: harness hook modes live in the project configuration and a committed carrier

## Status

Accepted

## Context

Hook modes were stored in `<provider>/<hook>.env.ini` files of each project, written by several code paths and read by
many scripts. `safe-dirs.json` lived at the root of the monorepo.

## Decision

- **Settings.** Modes are keys of `[harness.hooks.<hook>]` in `.swissknifeman/config.toml`, with `providers.<id>`
  overrides; they are also allowed in the machine layer as defaults. `policy_profile` is `[harness] policy_profile`;
  provider selection is `[aicore.providers.selection.<id>]`, owned by `aicore.provider`.
- **Carrier.** `harness hooks sync` writes `.swissknifeman/hooks.env` (`<HOOK>_<KEY>[__<PROVIDER>]=value`), a committed,
  generated file that is not edited by hand. Hooks read it first, then the legacy `env.ini`, then their default; they parse
  plain lines and import neither harness nor aicore. `harness hooks show [--json]` prints `hooks-state/v1`.
  The writers of `env.ini` are gone; `--memory` also accepts `maind` and `manual`.
- **safe-dirs.** `<config>/harness/safe-dirs.json` (`SKM_HOME` isolates it), with one ladder shared by the CLI and the hook,
  fail-closed. The former root file and `~/.swissknifeman/safe-dirs.json` stay as legacy steps.
- **Locks stay.** `.swissknifeman/provider-artifacts.lock.json` and `.claude/agent-pack.lock.json` stay where they are:
  committed contracts that hooks read. The code holds only constants (`aicore.artifacts.lock.LOCK_RELATIVE_PATH`).
- **Legacy keys.** The `.swissknife.json` keys `policy_profile` and `providers` are read with one warning
  (`HARNESS_LEGACY_POLICY_PROFILE`, `MAIND_LEGACY_PROVIDERS`) until `swissknifeman upgrade`.

## Alternatives considered

- Hooks reading TOML: rejected, they must run without a Python dependency tree.
- Moving the locks into state: rejected, other tools read the committed files.

## Consequences

- Generated provider dispatchers and the agent-pack review gate read the carrier, so their bytes changed once.
- The mode of a hook is reviewed in git like any other setting.

## Supersedes

None.
