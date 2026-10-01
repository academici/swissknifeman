# fetch MCP

## What is this

Official (Anthropic / Model Context Protocol) server: pulling URL and returns the contents as
markdown. It is useful to have the agent itself read external documentation or pages.

- Repository: `modelcontextprotocol/servers` (`src/fetch`)
- Package: `mcp-server-fetch` (**Python**, PyPI) — is launched via `uvx`

::: warning Runtime — Python/uv
Unlike other recruitment servers, this **not npm**-package. Needed
[uv](https://github.com/astral-sh/uv) (`uvx`). If uv is not installed - install it or
use [Context7](./context7) for library documentation.
:::

## Installation

Preset (opt-in):

```bash
skiller integrate --mcp fetch
```

Preset - `configs/claude-code/mcp/fetch.json`:

```json
{
  "command": "uvx",
  "args": ["mcp-server-fetch"]
}
```

## Limitations

- robots.txt is respected by default; Some sites need a flag `--ignore-robots-txt`.
- Large pages are given in chunks (there are length and start parameters).
- B Claude Code is native WebFetch — server is needed when fetch is required as
  MCP-tool (for subagents, workflow or other client).
