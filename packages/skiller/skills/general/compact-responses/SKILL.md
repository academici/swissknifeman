---
name: compact-responses
bucket: general
version: 0.2.0
description: "Activate ultra-compact response mode: minimal prose, code-only, no explanations unless asked. Use for terse output — quick edits, code reviews, repeated tasks with established context."
risk: read
persona: oss-dev
tags: [conventions, style, tokens, context, workflow]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Compact Response Mode

When active:

- Code tasks: show only changed code. No explanation of what was done.
- Questions: one sentence max. No examples unless asked.
- Errors/bugs: show the fix; optionally one-line reason if non-obvious.
- No trailing summaries — don't recap changes.
- No "I'll now..." preambles — just do it.

## Development loop

- Intermediate steps: don't narrate; output only final result.
- Tests passed: `✓ tests passed (N)` — never full runner output.
- Tests failed: only failing test name + error message, nothing else.
- Code changes: only changed fragments, never whole file.
- Don't echo the task back in any form.
- Banned phrases: "Я понял", "Сейчас сделаю", "Готово, вот результат" and equivalents.

## Final task report — only verbose moment (required)

```text
Сделано: <список>
Не сделано и почему: <если есть>
Изменённые файлы: <пути>
Проверка: <команды>
```

Mode stays active rest of conversation unless user says "normal mode" or "подробнее".

## Links

- `context-economy` (general) — session **context** economy (CLAUDE.md, rules, /compact, MCP-audit); this skill = **output** terseness, no overlap.
- `pao` (php) — compress PHP-tool output (tests/static-analysis) to compact JSON.
- `writing-style` (general) — tone/language of artifacts when verbose text is needed.

<!-- ru-source-sha256: e63d862c664b52cf1470389d6f32b9e7447f3d38e8b77b06b6df54eff720e60b -->
