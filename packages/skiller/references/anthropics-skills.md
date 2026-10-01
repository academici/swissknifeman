# anthropics/skills

- **URL:** https://github.com/anthropics/skills
- **License:** Apache-2.0 (© 2026 Anthropic, PBC)
- **Status:** imported
- **Checked:** 2026-07-11 (HEAD `9d2f1ae`)

Official collection of skills from Anthropic (Claude/Claude Code team). Different from
`anthropics/claude-code` (format specification SKILL.md) — are ready-made applied skills.
We take it selectively, specifically for our scenarios - we do not fork the entire repository.

## Taken

| anthropics/skills | our target | strategy |
|---|---|---|
| mcp-builder | `ai/mcp-builder` | replace (mirror as-is, `reference/` → `references/`) |

## Take selectively (candidates)

Other skills of the repository (`skills/*`) — as needed, by separate import
each, with their own assessment of the intersection with our existing skills (anti-bloat,
see `CONTRIBUTING.md`).

## Targets bucket-s

`ai/` (agent tools/MCP), pointwise others - for a specific skill.
