<!-- swissknifeman:instructions:harness:claude-code:common:begin -->
<!-- semantic:harness.identity -->
<!-- semantic:harness.semantic-source -->
<!-- semantic:harness.layout -->
<!-- semantic:harness.command-surface -->
<!-- semantic:harness.agent-pack-lifecycle -->
<!-- semantic:harness.engineering-invariants -->
<!-- semantic:harness.cross-package-boundaries -->
<!-- semantic:harness.validation-release -->
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
Keep the CLI surface `permissions`, `mcp`, `hooks`, `router`, `agent-packs`, `safe-dirs`, and `doctor`, with explicit `--target` and dry-run behavior where defined.
<!-- instruction:harness.agent-pack-lifecycle -->
## harness.agent-pack-lifecycle
Agent packs render templates, upgrade only safe managed files, write conflicts as `*.pack-new`, and remove only unmodified managed files; their lock records preserve ownership. A pack file entry may declare `src_pack` to share content from another pack without copying it, and the review-role registry indexes roles as an extension table alongside the canonical `roles.json` without duplicating its rules.
<!-- instruction:harness.engineering-invariants -->
## harness.engineering-invariants
Keep `lib/harness/` stdlib-only, pass frozen `Env` explicitly, use merge-only project writes with `*.bak` backups, and emit Russian diagnostics.
<!-- instruction:harness.cross-package-boundaries -->
## harness.cross-package-boundaries
Keep memory state ownership with `skiller`, retain `.swissknife.json:memory_brain`, and let `skiller` delegate environment operations to the worktree-local `harness` launcher. Also, never break paths already installed on consumers.
<!-- instruction:harness.validation-release -->
## harness.validation-release
Run `bash scripts/test.sh` and `bash scripts/validate.sh` before release; regenerate the umbrella registry after changing harness plugin commands.
<!-- swissknifeman:instructions:harness:claude-code:common:end -->
<!-- swissknifeman:instructions:harness:claude-code:extension:begin -->
<!-- semantic:harness.claude-code.config-surfaces -->
<!-- semantic:harness.claude-code.lifecycle-surfaces -->
<!-- semantic:harness.claude-code.settings-precedence -->
<!-- semantic:harness.claude-code.safe-dirs -->
<!-- instruction:harness.claude-code.config-surfaces -->
## harness.claude-code.config-surfaces
Claude Code configuration remains under `configs/claude-code/`: settings presets merge into `.claude/settings*.json` and MCP presets merge into `.mcp.json`. Also, installed Claude hooks live under `~/.claude/hooks/`, reading state owned by `skiller` under `~/.swissknifeman/`.
<!-- instruction:harness.claude-code.lifecycle-surfaces -->
## harness.claude-code.lifecycle-surfaces
Claude Code lifecycle surfaces include `PreToolUse` auto-approval, memory, notify, agent-router, run-report, output style, statusline, review-gate on `SubagentStop`, and project `plansDirectory` registrations; a global mode may only lower a strict check to warn, never raise it.
<!-- instruction:harness.claude-code.settings-precedence -->
## harness.claude-code.settings-precedence
Claude Code keeps `outputStyle` in `.claude/settings.local.json`, uses top-level `plansDirectory` in `.claude/settings.json`, and keeps the agent-pack lock at `.claude/agent-pack.lock.json`.
<!-- instruction:harness.claude-code.safe-dirs -->
## harness.claude-code.safe-dirs
The `PreToolUse` auto-approve hook lets `rm`/`rmdir` inside trusted directories pass `deny_hard`: the safe-dirs allowlist is machine-owned and its verdict is fail-closed, and a project-level hook override never affects the allowlist.
<!-- swissknifeman:instructions:harness:claude-code:extension:end -->
