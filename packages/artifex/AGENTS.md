<!-- swissknifeman:instructions:artifex:codex:common:begin -->
<!-- semantic:artifex.identity -->
<!-- semantic:artifex.layout -->
<!-- semantic:artifex.runtime-boundaries -->
<!-- semantic:artifex.provenance -->
<!-- semantic:artifex.engineering-invariants -->
<!-- semantic:artifex.validation-release -->
<!-- instruction:artifex.identity -->
## artifex.identity
`artifex` is the standalone deterministic supervisor package; its package runtime is the sole live implementation after G1.
<!-- instruction:artifex.layout -->
## artifex.layout
Keep `bin/artifex` as a thin launcher, `lib/artifex/` as the runtime, `tests/` as isolated evidence, and `scripts/test.sh` plus `scripts/validate.sh` as package gates.
<!-- instruction:artifex.runtime-boundaries -->
## artifex.runtime-boundaries
Keep provider adapters additive over one shared supervisor contract; use bounded fresh processes and never make package runtime import `plans/**`.
<!-- instruction:artifex.provenance -->
## artifex.provenance
Keep generation and source hashes explicit; plan-local runtime remains immutable non-importable evidence rather than a package dependency.
<!-- instruction:artifex.engineering-invariants -->
## artifex.engineering-invariants
Keep `lib/artifex/` stdlib-only, resolve roots explicitly, use Russian diagnostics, and preserve one implementation rather than a plan-local duplicate.
<!-- instruction:artifex.validation-release -->
## artifex.validation-release
Before release run `bash scripts/test.sh` and `bash scripts/validate.sh` and use Russian Conventional Commit messages.
<!-- swissknifeman:instructions:artifex:codex:common:end -->

<!-- swissknifeman:instructions:artifex:codex:extension:begin -->
<!-- semantic:artifex.codex.package-scope -->
<!-- instruction:artifex.codex.package-scope -->
## artifex.codex.package-scope
Codex package work starts with `codex -C packages/artifex`; package guidance is additive over the shared Artifex contract and does not replace it.
<!-- swissknifeman:instructions:artifex:codex:extension:end -->
