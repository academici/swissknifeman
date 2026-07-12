# Changelog — dart-flutter pack

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

## [0.5.2] - 2026-07-12

### Changed

- **Диета `description` всех агентов пака** (P4.1, план CONTEXT-ECONOMY): frontmatter
  `description:` каждого `agents/*.md` сокращён до cap 600B — 1 показательный `<example>`
  вместо 2-3, анти-триггер сведён к одной фразе прозой. Затронуты install-файлы
  `.claude/agents/{PACK_PREFIX}-*.md` (все агенты пака).

## [0.4.1] - 2026-07-02

### Added

- **Ось `generated-core-edited` (HIGH) в `agents/reviewer.md`** — дифф, трогающий файл
  с header `swissknifeman:generated`, репортится как HIGH: правку перенести в override,
  core восстановить рендером. Затронут install-файл `.claude/agents/{PACK_PREFIX}-reviewer.md`.
- **Overlay-скаффолд `rules/reviewer-overrides.md`** (user_owned, `role:override`) →
  `.claude/rules/{PACK_PREFIX}-reviewer-overrides.md`: легальная зона проектных осей ревью;
  reviewer читает его финальным блоком «Проектные оверрайды» ПОВЕРХ общих осей.
- **HARD_GATES в `workflows/dev-loop.js`**: generated `.claude/agents|workflows|hooks`
  не редактировать — оверрайды в `.claude/rules/*-overrides.md`.
- Provenance-headers в rendered-файлы добавляет ДВИЖОК agent-packs (harness), не шаблоны
  пака. Контекст: SKM-MASTER-002 фаза E.

## [0.4.0] - 2026-07-02

### Changed

- **dev-loop: `agent({schema})` throw (schema-noncompliance) больше не роняет прогон
  (azguard overnight-инцидент 2026-07-02).** Затронут install-файл
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`: все вызовы `agent()` обёрнуты в
  `safeAgent()` — если сабагент завершился без вызова StructuredOutput (throw
  `subagent completed without calling StructuredOutput`), исключение гасится в `null`
  вместо всплытия наверх; дальше штатная деградация `if (!result)` (infra-failed →
  fail-fast → Verify/отчёт), как уже было для терминальных API-ошибок. Раньше throw
  ронял ВЕСЬ workflow (потеря прогресса, ручной resume).

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
