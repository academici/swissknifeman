<!-- instruction:maind.claude-code.plugin-and-mcp -->
## maind.claude-code.plugin-and-mcp
The Claude Code plugin exposes only `/maind:*` command wrappers; maind MCP tools arrive through the per-project `maind` server in `.mcp.json`.
<!-- instruction:maind.claude-code.workspace-trust -->
## maind.claude-code.workspace-trust
Claude Code workspace trust is managed by `workspace.py` in `.claude/settings.local.json` and remains separate from provider-agnostic hub state.
