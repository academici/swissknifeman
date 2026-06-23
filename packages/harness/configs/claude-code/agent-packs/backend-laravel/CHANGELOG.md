# Changelog — backend-laravel pack

Версии per-PACK (одна версия — один changelog). Формат Keep a Changelog. Каждая
запись помечает затронутый install-файл, чтобы апгрейдящий агент сопоставил
изменение с конкретным файлом проекта.

## [0.1.0] - 2026-06-23

### Added

- Начальный пак, обобщён из overnight-артефактов memster:
  - `agents/slice-builder.md`, `agents/test-writer.md`, `agents/reviewer.md` —
    роли с `skills:` preload + self-load fallback; стек-специфика через плейсхолдеры.
  - `workflows/dev-loop.js` — срез→impl→test→review на одной ветке; уроки зашиты:
    один branch/прогон, хард-кап `DEFAULT_MAX` литералом (переживает resume),
    circuit-breaker.
  - `hooks/review-gate.sh` (verbatim) + `hooks/review-gate.env.ini` (template,
    user_owned) — SubagentStop-гейт off|warn|strict.
  - `settings/settings.fragment.json` — регистрация SubagentStop (merge append-if-absent).
  - `docs/subagents-and-workflows.md` — guideline.
  - `agents/spec-writer.md` (опц.) — пишет `docs/specs/<feature>.md` на крупные фичи.
  - `rules/{api-controllers,migrations,tests}.md` — path-scoped правила (`.claude/rules/`,
    нативная авто-загрузка по путям); тонкие триггеры → ссылаются на скиллы.
- Плейсхолдеры: `{{PACK_PREFIX}}`, `{{PROJECT_DIR}}`, `{{PHP_RUNNER}}`,
  `{{TEST_RUNNER_CMD}}`, `{{TEST_DB}}`, `{{CHECK_CMD}}`.

### Migration notes (agent-facing)

- Первая версия — апгрейда нет. На install: интервью (см. `pack.json:interview`),
  рендер плейсхолдеров, lock с `base_sha256` отрендеренного.
- SAFE-APPLY-семантика появится со второй версией: SAFE-APPLY (база изменилась,
  файл не правлен локально) / WATCH (правлен локально — показать дельту, не
  перезатирать) / OPTIONAL (новое, по желанию).
