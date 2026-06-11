# anthropics/claude-code

- **URL:** https://github.com/anthropics/claude-code
- **Статус:** imported (формат принят)
- **Проверено:** 2026-06-11

Официальный репозиторий Claude Code. Источник истины по формату SKILL.md
(frontmatter `name` + `description`), структуре `.claude/skills/<name>/SKILL.md`,
hooks API и slash-командам.

## Уже взято

- Формат SKILL.md и плоская раскладка `.claude/skills/` — учтено в `install.sh --agent claude`

## Брать выборочно

- Hooks API (PreToolUse/PostToolUse) — для будущей автоматизации quality-проверок
- Паттерн user-level vs project-level скиллов — для разделения personal/shared

## Целевые bucket-ы

`adapters/claude-code/`, инфраструктура установки.
