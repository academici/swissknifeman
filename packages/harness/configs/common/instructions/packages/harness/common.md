<!-- instruction:harness.identity -->
## harness.identity
`harness` configures project environments with permissions, MCP, hooks, output styles, plan-directory settings, and agent packs.
<!-- instruction:harness.semantic-source -->
## harness.semantic-source
Keep `configs/claude-code/` as the current Claude compatibility source and keep common/provider semantic catalogs explicit rather than inferring settings from target files.
<!-- instruction:harness.layout -->
## harness.layout
Keep `bin/harness` as the thin launcher, `lib/harness/` as stdlib-only logic, `configs/` as source configuration, and `tests/` isolated in temporary directories.
<!-- instruction:harness.command-surface -->
## harness.command-surface
Keep the CLI surface `permissions`, `mcp`, `hooks`, `router`, `agent-packs`, `safe-dirs`, and `doctor`, with explicit `--target` and dry-run behavior where defined.
<!-- instruction:harness.agent-pack-lifecycle -->
## harness.agent-pack-lifecycle
Agent packs render templates, upgrade only safe managed files, write conflicts as `*.pack-new`, and remove only unmodified managed files; their lock records preserve ownership.
<!-- instruction:harness.engineering-invariants -->
## harness.engineering-invariants
Keep `lib/harness/` stdlib-only, pass frozen `Env` explicitly, use merge-only project writes with `*.bak` backups, and emit Russian diagnostics.
<!-- instruction:harness.cross-package-boundaries -->
## harness.cross-package-boundaries
Keep memory state ownership with `skiller`, retain `.swissknife.json:memory_brain`, and let `skiller` delegate environment operations to the worktree-local `harness` launcher.
<!-- instruction:harness.validation-release -->
## harness.validation-release
Run `bash scripts/test.sh` and `bash scripts/validate.sh` before release; regenerate the umbrella registry after changing harness plugin commands.
