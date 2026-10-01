<!-- instruction:harness.identity -->
## harness.identity
`harness` configures project environments with permissions, MCP, hooks, output styles, plan-directory settings, safe-dirs, statusline, and agent packs.
<!-- instruction:harness.semantic-source -->
## harness.semantic-source
Keep `configs/claude-code/` as the current Claude compatibility source and keep common/provider semantic catalogs explicit rather than inferring settings from target files.
<!-- instruction:harness.layout -->
## harness.layout
Keep `bin/harness` as the thin launcher, `lib/harness/` as stdlib-only logic, `configs/` as source configuration, and `tests/` isolated in temporary directories. Also, the safe-dirs verdict core lives in the hook, not in the CLI wrapper, and settings audits stay read-only.
<!-- instruction:harness.command-surface -->
## harness.command-surface
Keep the CLI surface `permissions`, `mcp`, `hooks`, `router`, `agent-packs`, `safe-dirs`, `instructions`, and `doctor`, with explicit `--target` and dry-run behavior where defined.
<!-- instruction:harness.agent-pack-lifecycle -->
## harness.agent-pack-lifecycle
Agent packs render templates, upgrade only safe managed files, write conflicts as `*.pack-new`, and remove only unmodified managed files; their lock records preserve ownership. A pack file entry may declare `src_pack` to share content from another pack without copying it, and the review-role registry indexes roles without copying their rules, as an extension table alongside the canonical `roles.json`.
<!-- instruction:harness.engineering-invariants -->
## harness.engineering-invariants
Keep `lib/harness/` stdlib-only, pass frozen `Env` explicitly, use merge-only project writes with `*.bak` backups, and emit English diagnostics.
<!-- instruction:harness.cross-package-boundaries -->
## harness.cross-package-boundaries
Keep memory state ownership with `skiller`, retain `.swissknife.json:memory_brain`, and let `skiller` delegate environment operations to the worktree-local `harness` launcher. Also, never break paths already installed on consumers.
<!-- instruction:harness.validation-release -->
## harness.validation-release
Run `bash scripts/test.sh` and `bash scripts/validate.sh` before release; regenerate the umbrella registry after changing harness plugin commands.
