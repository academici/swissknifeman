---
name: mcp-development
bucket: general
version: 0.1.0
description: "Work with MCP servers (Laravel Boost) and agent integrations in this project."
risk: write
persona: oss-dev
tags: [mcp, ai]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# MCP development

## When to use this skill
Use this skill when configuring/diagnosing MCP server connectivity (Cursor/IDE), or when an agent needs to use Boost tools.

## Notes
- MCP server command for this project: `php artisan boost:mcp`.
- If tools aren’t available in the IDE, ensure the MCP server is enabled in MCP settings.
