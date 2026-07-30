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
