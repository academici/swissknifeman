<!-- instruction:harness.claude-code.config-surfaces -->
## harness.claude-code.config-surfaces
Claude Code configuration remains under `configs/claude-code/`: settings presets merge into `.claude/settings*.json` and MCP presets merge into `.mcp.json`.
<!-- instruction:harness.claude-code.lifecycle-surfaces -->
## harness.claude-code.lifecycle-surfaces
Claude Code lifecycle surfaces include `PreToolUse` auto-approval, memory, notify, router, run-report, output style, and project `plansDirectory` registrations.
<!-- instruction:harness.claude-code.settings-precedence -->
## harness.claude-code.settings-precedence
Claude Code keeps `outputStyle` in `.claude/settings.local.json`, uses top-level `plansDirectory` in `.claude/settings.json`, and keeps the agent-pack lock at `.claude/agent-pack.lock.json`.
