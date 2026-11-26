# filesystem MCP

## What is this

Official (Anthropic / Model Context Protocol) file system access server - gives
agent reads and writes to **explicitly allowed** directories.

- Repository: `modelcontextprotocol/servers` (`src/filesystem`)
- npm: `@modelcontextprotocol/server-filesystem`

## Installation

Preset (opt-in):

```bash
skiller integrate --mcp filesystem
```

Preset - `configs/claude-code/mcp/filesystem.json` (default - project root):

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
}
```

Allowed directories are specified by arguments - add the necessary paths:

```json
"args": ["-y", "@modelcontextprotocol/server-filesystem", "./src", "./docs"]
```

## Limitations

- Access strictly to listed directories is a security boundary; don't expand it to
  secrets (`.env`, keys, `~/.ssh`).
- B Claude Code already have native ones Read/Write/Edit; server is useful when a separate
  isolated FS scope for agent/subagent or other MCP-client.
