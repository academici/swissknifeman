# Changelog — node-frontend pack

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/); версии — per-PACK (semver).

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

- Начальный frontend-пак для Vue/Vite (SPA/Inertia/Nuxt):
  - `agents/component-builder.md` (атомарный SFC), `agents/slice-builder.md` (срез
    страницы/фичи), `agents/test-writer.md` (Vitest+test-utils), `agents/reviewer.md`
    (tsc/eslint/типы/a11y), `agents/spec-writer.md` (опц.) — канонические `description`
    с `<example>`, `color`, `model: {{MODEL_*}}` (default `inherit`).
  - `workflows/dev-loop.js` — срез→impl→test→review на одной ветке (хард-кап, circuit-breaker).
  - `hooks/review-gate.sh` (verbatim, общий) + `hooks/review-gate.env.ini` (template,
    user_owned) — SubagentStop-гейт.
  - `hooks/validate-frontend.sh` (verbatim) — PostToolUse tsc/eslint → additionalContext,
    НЕ блокирует.
  - `settings/settings.fragment.json` — SubagentStop + PostToolUse (merge append-if-absent).
  - `rules/{components,state,tests}.md`, `docs/subagents-and-workflows.md`.
- Скиллы — из бакета `frontend` (vue/vite/pinia/inertia-vue/vitest-vue/tailwind…); новых
  скиллов не вводим.

### Migration notes (agent-facing)

- Первая версия — апгрейда нет; install = интервью → рендер → lock с `base_sha256`.
- Рекомендованный профильный пресет тиров: reviewer/spec=opus, component/slice/test=sonnet
  (выставляет `profiles/node-frontend.json:model_tiers`).
- Оркестратор — отдельный пак `_common` (ставить с тем же `PACK_PREFIX`).
