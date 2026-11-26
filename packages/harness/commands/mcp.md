---
description: "Add MCP-servers (context7, playwright, …) in .mcp.json project from Harnes presets, merge-only."
---
Add MCP-servers in `.mcp.json` of the current project from the Harness presets.

1. Show available presets: `harness mcp --list`.
2. Specify the set (for example `context7,playwright`) and target (`--target .`).
3. Suggest `--dry-run`, then apply.

Launch (via Bash):
```
harness mcp --target . --mcp context7[,playwright,…] [--dry-run]
```
Merge-only: other people's posts `mcpServers` are not overwritten, the file is backed up to `*.bak`. User Arguments - «$ARGUMENTS».
