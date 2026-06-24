# Changelog — python-backend pack

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

## [0.1.0] - 2026-06-24

### Added

- Начальный пак для Python web-бэкенда (FastAPI/Django/Flask):
  - `agents/slice-builder.md`, `agents/test-writer.md`, `agents/reviewer.md`,
    `agents/type-checker.md` (узкий mypy-проход), `agents/spec-writer.md` (опц.) —
    канонические `description` с `<example>`, `color`, `model: {{MODEL_*}}` (default `inherit`).
  - `workflows/dev-loop.js` (impl→test→type-check→review), `hooks/review-gate.sh`
    (verbatim) + `hooks/review-gate.env.ini` (template, user_owned),
    `hooks/validate-python.sh` (PostToolUse ruff → additionalContext, не блокирует).
  - `settings/settings.fragment.json` (SubagentStop+PostToolUse),
    `rules/{endpoints,typing,tests}.md`, `docs/subagents-and-workflows.md`.
- Интервью: `WEB_FRAMEWORK`, `PKG_MANAGER` (uv/poetry/pip), `PY_BIN` (venv-aware),
  ruff/mypy/pytest-команды.

### Migration notes (agent-facing)

- Первая версия — апгрейда нет.
- Бакет `python` тонкий (2 скилла): канон фреймворков/pytest — в промптах агентов и
  `rules/`, без новых скиллов (анти-bloat). Кандидат: `python/pytest-conventions`.
- Рекомендованный профильный пресет тиров: reviewer/spec=opus, slice/test/type-checker=sonnet.
- Оркестратор — отдельный пак `_common`.
