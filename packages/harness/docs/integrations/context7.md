# Context7 MCP

## What is this

Context7 from Upstash — MCP-server that pulls up on the fly **current documentation
libraries** straight into context Claude Code. Resolves version drift: model training data
have cutoff-date, and Flutter/Dart, Laravel, Node and other ecosystems are being updated
permanently. C Context7 agent gets alive docs with reference to version.

- Repository: <https://github.com/upstash/context7>
- Transport: remote HTTP, endpoint `https://mcp.context7.com/mcp` (without local installation)

## Installation

`context7` — **dev-default**: installed in any development environment (everything except obsidian-vault)
without flag:

```bash
skiller integrate
```

Preset - `configs/claude-code/mcp/context7.json`:

```json
{
  "type": "http",
  "url": "https://mcp.context7.com/mcp"
}
```

::: tip API-key optional
Without a key, the server works with rate-limit. For higher limits, get a key to
`context7.com/dashboard` and add the header:

```json
{
  "type": "http",
  "url": "https://mcp.context7.com/mcp",
  "headers": { "CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}" }
}
```
:::

## Usage

Activation - string **`use context7`** at the end of the request:

```
How to implement chunked-processing Eloquent current Laravel? use context7
```

The server exports two tools that the agent calls itself:

| Tool | Purpose |
|---|---|
| `resolve-library-id` | search for library by name → context7-compatible ID |
| `get-library-docs` | documentation for ID + topic |

## Limitations

- Highly specialized/closed libraries may not be indexed - for them
  will come in handy [fetch](./fetch) or direct reading of sources.
- Side cache Upstash: the newly released patch may arrive with a delay.
- Dependency on external service (uptime Upstash).
