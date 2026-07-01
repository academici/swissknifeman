# Changelog — python-backend pack

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

## [0.3.0] - 2026-07-01

### Changed

- **dev-loop resilience (rate-limit incident 2026-07-01).** Затронут install-файл
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`: статус `infra-failed` в enum схемы
  (инфра-отказ не маскируется под `deferred`); fail-fast на терминальный
  `agent()===null` (СТОП прогона); дефолт батча 3 → 2; heartbeat `log()` на каждом
  шаге; текст-маркер `===SLICE-RESULT=== status=…` как запасной путь возврата.
- In-script `withDeadline` **не добавляем** (песочница не даёт `Date.now()`/`setTimeout`/
  cancel); затяжной hang ловит внешний supervisor — см. пак `_common` и
  `docs/skiller/workflows/background-agents.md` → «Устойчивость».

## [0.2.0] - 2026-06-29

### Changed

- **AI-гайд переехал из публичного `docs/` в `.claude/guidelines/`.** `DOCS_DIR` по
  умолчанию теперь `.claude/guidelines` (было `docs/05_AI/guidelines`):
  `subagents-and-workflows.md` — внутренний артефакт для агентов, не публичная
  документация проекта. Затронут install-файл `{DOCS_DIR}/subagents-and-workflows.md`.

> **Миграция (upgrade):** новый гайд в `.claude/guidelines/`; старый файл в
> `docs/05_AI/guidelines/` не удаляется автоматически — удалите вручную.

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
