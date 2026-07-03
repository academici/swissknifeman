# Changelog — laravel-package pack

Версии per-PACK (одна версия — один changelog). Формат Keep a Changelog. Каждая
запись помечает затронутый install-файл, чтобы апгрейдящий агент сопоставил
изменение с конкретным файлом проекта.

## [0.1.1] - 2026-07-02

### Fixed

- **BC-строка Verify в `workflows/dev-loop.js`** (T6а, SKM-MASTER-003 P2.5) — пункт 6
  списка Verify обёрнут в `<!-- pack:if BC_CHECK_CMD -->…<!-- pack:endif -->` /
  `<!-- pack:ifnot BC_CHECK_CMD --> … <!-- pack:endif -->`: при незаданной `{{BC_CHECK_CMD}}`
  рендер больше не несёт сырой плейсхолдер с двойным пробелом («если задана  — прогони
  её…») — вместо этого явный текст «команда не задана — отметь «BC-чекер не установлен,
  пропуск»» (шаг не исчезает молча, семантика прежняя). Затронут install-файл
  `.claude/workflows/{PACK_PREFIX}-dev-loop.js`. Не shared-блок (пак-уникальная строка,
  дубля в других паках нет) — `test_agentpacks_shared.py` не затронут.

## [0.1.0] - 2026-07-02

Первый релиз. Отдельный пак для **Laravel-ПАКЕТОВ** (composer library / монорепо
пакетов), не приложений — у reviewer'а заменяется ~60% тела относительно
`backend-laravel`, идентичность юнита у slice-builder другая («фича пакета»).
Контекст: мастер-план SKM-MASTER-002, фаза F; roadmap `php-package-stack-pack.md` →
«реализовано». Bool-режим (`IS_LARAVEL_PACKAGE`) пробовали и выпилили в
backend-laravel@0.9.0 — сюда не возвращается.

### Added

- **`agents/reviewer.md`** — центр «публичный контракт пакета»: оси Public API/BC-SemVer
  (Contracts-дифф, `getFacadeAccessor`, удалённый публичный метод без MAJOR → CRITICAL,
  `{{BC_CHECK_CMD}}` против latest tag при наличии roave/backward-compatibility-check),
  ServiceProvider register-vs-boot (I/O в register → HIGH), publishables
  (`pack:if HAS_MIGRATIONS`), `env()` вне config → HIGH, composer-констрейнты
  (dev-инструменты в require → CRITICAL; laravel/framework вместо illuminate/* → MED),
  Testbench (`use App\` в tests → HIGH), multi-version matrix.
  Install-файл `.claude/agents/{PACK_PREFIX}-reviewer.md`.
- **`agents/slice-builder.md`** — юнит = «фича пакета» (контракт → реализация →
  регистрация в provider → publishables → фасад); канон минимальной публичной
  поверхности (`@internal`/`final`). Install-файл `.claude/agents/{PACK_PREFIX}-slice-builder.md`.
- **`agents/test-writer.md`** — Testbench (пакетный TestCase/getPackageProviders,
  in-memory sqlite `{{TEST_DB}}`), матрично-чувствительные `version_compare`-ветки.
- **`agents/api-surface.md`** — новый recon-агент ({{MODEL_RECON}}): карта диффа
  публичной поверхности (added/changed/removed + SemVer-намёк). route-mapper/blade-review
  app-пака в этом паке отсутствуют.
- **`agents/{spec-writer,test-verifier,security-review}.md`** — форки с пакетной прозой
  (security-review: + секреты в publishable config, md5/sha1 для токенов; app-оси
  policy/IDOR/middleware убраны).
- **`rules/{public-api,service-provider,package-migrations}.md`** (verbatim) +
  **`rules/tests.md`** (template) — path-scoped правила пакетного канона.
- **`rules/reviewer-overrides.md`** (user_owned, `role:override`) →
  `.claude/rules/{PACK_PREFIX}-reviewer-overrides.md` — легальная зона проектных осей.
- **`workflows/dev-loop.js`** — форк backend-laravel: lanes/risk-adaptive без изменений,
  `+'public-api'` в risk_markers, HARD_GATES под пакет, preflight
  `composer validate --strict` + PDO sqlite, Verify + grep `env(` + `{{BC_CHECK_CMD}}`.
- **`src_pack`-реюз**: `hooks/review-gate.sh`, `settings/review-gate.env.ini`,
  `settings/settings.fragment.json` берутся из `backend-laravel` байт-в-байт
  (движковая ссылка `src_pack`, копий в каталоге пака нет).
- **Интервью/детект** (safe-пробы): `PACKAGE_SRC_ROOT` (src | packages/*/src),
  `PACKAGE_NAMESPACE` (psr-4 из composer.json c фолбэком на `packages/*/composer.json`,
  кратчайший префикс — монорепо-кейс), `TEST_FRAMEWORK`/`TEST_RUNNER_CMD`/`CHECK_CMD`/
  `HAS_MIGRATIONS`/`BC_CHECK_CMD` (пусто = ось прозой). app-проект (artisan) →
  используйте `backend-laravel`.

### Known limitations

- `stack.detect.none_of` — информационный (движок agent-packs detect-матчинг не читает).
- ~~При пустом `BC_CHECK_CMD` в Verify-подсказке dev-loop остаётся двойной пробел
  (нет `pack:if`-обёртки) — косметика, follow-up.~~ Исправлено в 0.1.1.
