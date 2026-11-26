# GitHub MCP

## What is this

Official GitHub MCP-server: control Issues, Pull Requests, repositories and Actions
directly from the agent, without switching to `gh`.

- Repository: <https://github.com/github/github-mcp-server>
- Options: **remote** (hosts GitHub, `https://api.githubcopilot.com/mcp/`) or local
  Docker (`ghcr.io/github/github-mcp-server`)

## Installation

Preset (opt-in) — supplied remote-option (without Docker and tokens in the file):

```bash
skiller integrate --mcp github
```

Preset - `configs/claude-code/mcp/github.json`:

```json
{
  "type": "http",
  "url": "https://api.githubcopilot.com/mcp/"
}
```

Authentication - OAuth on first call (or Bearer-PAT via header
`Authorization`). Local option - Docker with `GITHUB_PERSONAL_ACCESS_TOKEN`.

## Limitations and alternative

- Remote-server requires access to GitHub and an account with the necessary rights.
- In projects academici git-process has already been closed by skills `oss-dev/github-flow` +
  `oss-dev/gh-review` on top `gh` CLI. GitHub MCP is useful when you need to give the agent direct
  tools GitHub without shell — suspension vs. usual `gh`.
