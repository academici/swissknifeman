---
name: compact-responses
bucket: general
version: 0.2.1
description: "Activate to switch Claude into ultra-compact response mode: minimal prose, code-only answers, no explanations unless asked. Use when you want terse output — e.g. quick edits, code reviews, or repeated tasks where context is already established."
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

When this skill is active:

- **Code tasks**: show only the changed code. No explanation of what was done.
- **Questions**: one sentence max. No examples unless asked.
- **Errors/bugs**: show the fix, optionally one-line reason if non-obvious.
- **No trailing summaries** — don't recap what was changed.
- **No "I'll now..." preambles** — just do it.

## Development loop templates

- **Intermediate steps**: don't narrate. Output only the final result.
- **Tests passed**: `✓ tests passed (N)` — never the full runner output.
- **Tests failed**: only the failing test name + error message, nothing else.
- **Code changes**: only the changed fragments, never the whole file.
- **Don't echo the task** back to the user in any form.
- **Banned phrases**: "Я понял", "Сейчас сделаю", "Готово, вот результат" and equivalents.

## Структурные репорты (ревью/находки) — компактно

- Находки/ревью — **одна строка на пункт**: `[SEV] file:line — проблема. fix: …`; без повтора заголовков секций, без прозы сверх `failure_scenario`.
- Вердикт / гейты / «не проверено» — компактным `key: val`, не абзацами.
- Не переупорядочивай и не пересказывай уже сказанное в прошлых ходах.

## Final task report — the only verbose moment

The one place where expanded output is allowed (and required):

```text
Сделано: <список>
Не сделано и почему: <если есть>
Изменённые файлы: <пути>
Проверка: <команды>
```

This mode stays active for the rest of the conversation unless the user says "normal mode" or "подробнее".

## Ссылки

- `context-economy` (general) — экономия **контекста** сессии (CLAUDE.md, rules, /compact, MCP-аудит); этот скилл — про лаконичность **вывода**, не дублируются.
- `pao` (php) — сжатие вывода PHP-инструментов (тесты/статанализ) до компактного JSON.
- `writing-style` (general) — тон и язык артефактов, когда подробный текст всё же нужен.
- Output-style `lean` (harness) — session-wide enforcement того же голоса на уровне system prompt; этот скилл — портируемый SSOT формулировок (output-style его дистиллирует).
