# anthropics/skills

- **URL:** https://github.com/anthropics/skills
- **Лицензия:** Apache-2.0 (© 2026 Anthropic, PBC)
- **Статус:** imported
- **Проверено:** 2026-07-11 (HEAD `9d2f1ae`)

Официальная коллекция скиллов от Anthropic (Claude/Claude Code team). Отличается от
`anthropics/claude-code` (спецификация формата SKILL.md) — это готовые прикладные скиллы.
Берём выборочно, точечно под наши сценарии — не форкаем весь репозиторий.

## Взято

| anthropics/skills | наш таргет | strategy |
|---|---|---|
| mcp-builder | `ai/mcp-builder` | replace (зеркало as-is, `reference/` → `references/`) |

## Брать выборочно (кандидаты)

Остальные скиллы репозитория (`skills/*`) — по мере необходимости, отдельным импортом
каждый, с собственной оценкой пересечения с существующими нашими скиллами (анти-bloat,
см. `CONTRIBUTING.md`).

## Целевые bucket-ы

`ai/` (агентные тулы/MCP), точечно другие — по конкретному скиллу.
