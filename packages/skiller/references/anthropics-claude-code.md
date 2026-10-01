# anthropics/claude-code

- **URL:** https://github.com/anthropics/claude-code
- **Status:** imported (format accepted)
- **Checked:** 2026-06-11

Official repository Claude Code. Source of truth by format SKILL.md
(frontmatter `name` + `description`), structure `.claude/skills/<name>/SKILL.md`,
hooks API and slash-commands.

## Already taken

- Format SKILL.md and flat layout `.claude/skills/` — included in `install.sh --agent claude`

## Take selectively

- Hooks API (PreToolUse/PostToolUse) — for future automation quality-checks
- Pattern user-level vs project-level skills - for separation personal/shared

## Targets bucket-s

`adapters/claude-code/`, installation infrastructure.
