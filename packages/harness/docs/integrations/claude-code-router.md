# Claude Code Router

::: warning Tool in doubt
This page is a confirmation that the tool exists. Implementation into the workflow
swissknifeman **not recommended by default** — for the reasons below. Preset in
`configs/claude-code/mcp/` is not supplied for it (this is not MCP-server, and proxy).
:::

## What is this

Claude Code Router (musistudio) — local proxy that intercepts requests Claude
Code and **redirects them to different models** (OpenRouter, DeepSeek, Gemini, Ollama, any
OpenAI-compatible endpoint) according to the rules. The idea is to save: expensive tasks for top
model, routine for cheap.

- Repository: <https://github.com/musistudio/claude-code-router>
- npm: `@musistudio/claude-code-router` (CLI `ccr`), license MIT, community-project

```bash
npm install -g @musistudio/claude-code-router
ccr code     # run Claude Code via router
ccr ui       # web config editor ~/.claude-code-router/config.json
```

## Why in doubt

- **Breaks some features.** Extended thinking, native tool-use and prompt-caching
  are designed for Anthropic API; through third-party providers work partially or not at all.
- **Third-party traffic proxy.** All requests go through community-proxy - trust model
  changes; Provider secret keys live in its config (do not commit).
- **Instability.** Active changes API; typical examples of configs quickly become outdated -
  including model names embedded in them.
- **Debug opacity.** It is not obvious which model a particular request went through.
- **+latency** for each request.

## When it still makes sense

A very large volume of similar cheap tasks, where the savings cover the loss of quality and
risks, and you are ready to commit the version and test it thoroughly. To optimize your selection
models *inside* Claude Code without proxy - skill `general/context-economy` (routing
models using standard tools).
