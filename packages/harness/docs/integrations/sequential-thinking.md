# sequential-thinking MCP

## What is this

Official (Anthropic / Model Context Protocol) server: tool for **step by step
structured reasoning** — agent breaks a complex task into explicit steps with
the possibility of revisions and branches.

- Repository: `modelcontextprotocol/servers` (`src/sequentialthinking`)
- npm: `@modelcontextprotocol/server-sequential-thinking`

## Installation

Preset (opt-in):

```bash
skiller integrate --mcp sequential-thinking
```

Preset - `configs/claude-code/mcp/sequential-thinking.json`:

```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
}
```

## When useful

Multi-step tasks with non-obvious decomposition: complex refactoring, dependency parsing,
architectural forks. Modern models Claude can extended thinking and so - server
provides an explicit, observable protocol of steps that is easy to audit.
