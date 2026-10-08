# Architecture

Durable description of how the repository is divided into modules, why, and which contracts hold the modules together.
Everything here is kept in the repository so that it outlives any working plan.

| Page | What it answers |
| --- | --- |
| [Ecosystem](ecosystem.md) | principles, layout, module contract, `aicore`, configuration and state, extensibility, what each module owns, skill and service-file distribution, migration discipline, transition, risks |
| [Contracts](contracts.md) | inventory of contracts with owners and gaps, versioning and the evolution policy of each contract |
| [Ownership map](ownership.md) | generated table of modules and of files that move to another module (do not edit by hand) |
| [Decisions](decisions/README.md) | numbered architecture decision records with context, alternatives and consequences |

## Keeping it current

- `ownership.md` is generated: `python3 scripts/ecosystem-units.py render` rewrites it and `render --check` (run in CI)
  fails when it drifts from `configs/ecosystem-units.json` and the `unit.json` manifests.
- A decision is never edited silently. A change of direction is a new record that supersedes the old one
  ([format](decisions/README.md#format)).
- When code and this description diverge, the divergence is reported first and the pages are updated by the change that
  resolves it.
- Module-level documentation lives in each module's `docs/`; these pages cover only what spans modules.

How to run the checks that guard this architecture is described in [development](../develop.md#ecosystem-split-branch-temporary).
