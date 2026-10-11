<!-- swissknifeman:instructions:orch:claude-code:common:begin -->
<!-- semantic:orch.identity -->
<!-- semantic:orch.module-boundaries -->
<!-- semantic:orch.engineering-invariants -->
<!-- semantic:orch.validation-release -->
<!-- instruction:orch.identity -->
## orch.identity
`orch` is the engine-neutral orchestration module: it owns the `exec/v1` and `conductor/v1` contracts, the Engine Port, run-policy packs and the launch catalog; it prepares runs and drives a work source, and its conductor (`scripts/conduct.py`) starts the roles of a run as child processes.
<!-- instruction:orch.module-boundaries -->
## orch.module-boundaries
Import only `orch` and `aicore`; never name partner modules in the core: planner, skiller and harness are reached only through the bridges under the hub `bridges/` and the `orch:work-source` extension point.
<!-- instruction:orch.engineering-invariants -->
## orch.engineering-invariants
Keep Python 3.9 compatibility, English diagnostics, `PortError` codes in the order of `docs/engine-port.md`, pure `prepare` and reducer functions, and change `exec/v1` only by optional fields proven by `aicore schema compat`.
<!-- instruction:orch.validation-release -->
## orch.validation-release
Before a commit run `bash scripts/test.sh` and `bash scripts/validate.sh`, then `python3 scripts/ecosystem-units.py check` and `python3 scripts/ecosystem-units.py standalone orch` from the hub root; use Russian Conventional Commit messages.
<!-- swissknifeman:instructions:orch:claude-code:common:end -->

<!-- swissknifeman:instructions:orch:claude-code:extension:begin -->

<!-- swissknifeman:instructions:orch:claude-code:extension:end -->
