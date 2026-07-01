# Changelog — dart-flutter pack

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

- Начальный пак для Flutter/Dart (mobile / POS / embedded):
  - `agents/slice-builder.md`, `agents/test-writer.md`, `agents/reviewer.md`
    (POS/embedded-aware), `agents/ffi-reviewer.md` (опц., под FFI), `agents/spec-writer.md`
    (опц.) — канонические `description` с `<example>`, `color`, `model: {{MODEL_*}}`
    (default `inherit`).
  - `workflows/dev-loop.js`, `hooks/review-gate.sh` (verbatim) +
    `hooks/review-gate.env.ini` (template, user_owned), `hooks/validate-flutter.sh`
    (PostToolUse `dart analyze` → additionalContext, не блокирует).
  - `settings/settings.fragment.json` (SubagentStop+PostToolUse),
    `rules/{widgets,state,ffi,tests}.md`, `docs/subagents-and-workflows.md`.
- Интервью: `STATE_MGMT`, `HAS_FFI`, `TARGET_KIND` (mobile/pos-embedded/desktop),
  `FLUTTER_BIN`/`DART_BIN`/`ANALYZE_CMD`/`FORMAT_CMD`. FFI-блоки под `pack:if HAS_FFI`.

### Migration notes (agent-facing)

- Первая версия — апгрейда нет.
- Бакет `mobile` тонкий (1 скилл): архитектура/state/FFI/POS — в промптах агентов и
  `rules/`, без новых портируемых скиллов (анти-bloat). Кандидат на будущее (по реальному
  переиспользованию): `mobile/flutter-testing`.
- Рекомендованный профильный пресет тиров: reviewer/spec=opus, slice/test=sonnet.
- Оркестратор — отдельный пак `_common`.
