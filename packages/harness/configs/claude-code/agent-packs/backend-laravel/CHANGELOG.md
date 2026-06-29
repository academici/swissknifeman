# Changelog — backend-laravel pack

Версии per-PACK (одна версия — один changelog). Формат Keep a Changelog. Каждая
запись помечает затронутый install-файл, чтобы апгрейдящий агент сопоставил
изменение с конкретным файлом проекта.

## [0.4.0] - 2026-06-29

### Changed

- **AI-гайд переехал из публичного `docs/` в `.claude/guidelines/`.** `DOCS_DIR` по
  умолчанию теперь `.claude/guidelines` (было `docs/05_AI/guidelines`). Гайд
  `subagents-and-workflows.md` — внутренний артефакт для агентов, не публичная
  VitePress-документация пакета: в open-source PHP-пакете `docs/` публикуется, и
  машинному гайду там не место (а doc-sync затягивал его в Brain-валт). Затронут
  install-файл `{DOCS_DIR}/subagents-and-workflows.md`.
- **Убран ошибочный Brain-frontmatter из шаблона** `docs/subagents-and-workflows.md`
  (`parent: [[05_AI]]`, tags, created) и вики-ссылка `[[agent-system-references]]` —
  Obsidian-вики-ссылки сломали бы wikilink-гейт, попади гайд в публичную `docs/`.

> **Миграция (upgrade установленных проектов):** новый гайд появится в
> `.claude/guidelines/`; **старый файл в `docs/05_AI/guidelines/` не удаляется
> автоматически** (движок не чистит при смене target) — удалите его вручную.

## [0.3.0] - 2026-06-28

### Changed

- **Шаблоны деуниверсализованы — убрана зашитая среда одного проекта** (agents/slice-builder,
  agents/test-writer, rules/tests, workflows/dev-loop, docs/subagents-and-workflows). Тест-фреймворк
  теперь параметричен через `{{TEST_FRAMEWORK}}` (раньше игнорировался — хардкод «PHPUnit-native, НЕ
  Pest»). Удалены machine-specific утверждения (`php8.5`/`pgsql`/`Postgres поднят`/`/usr/bin/php8.4`)
  и ложные для большинства проектов («phpstan не установлен — не звать», «миграции не добавлять —
  схема полная»). Идентичность slice-builder смягчена до «Laravel/REST API или пакет поверх моделей
  проекта» (раньше — «поверх готового 8-доменного слоя моделей»). Статическая проверка теперь
  ссылается на `{{CHECK_CMD}}`. Затронуты install-файлы: `.claude/agents/{prefix}-slice-builder.md`,
  `{prefix}-test-writer.md`, `.claude/rules/tests.md`, `.claude/workflows/{prefix}-dev-loop.js`,
  `docs/.../subagents-and-workflows.md` — апгрейд перерендерит их.

## [0.2.0] - 2026-06-24

### Added

- Канонические `description` всех агентов в формате авто-делегирования Claude Code
  («Use this agent when…» + 2–3 `<example>` Context/user/assistant/`<commentary>`,
  placeholder-safe) — `agents/{reviewer,slice-builder,test-writer,spec-writer}.md`.
- Поле `color` каждому агенту (reviewer=yellow, slice-builder=green, test-writer=cyan,
  spec-writer=magenta) и стек-агностичному оркестратору (пак `_common`, blue).
- Модельные тиры через плейсхолдеры: `model: {{MODEL_REVIEWER|MODEL_SLICE_BUILDER|`
  `MODEL_TEST_WRITER|MODEL_SPEC_WRITER}}` (дефолт каждого — `inherit`, поведение не
  меняется; профиль типа проекта пре-заполняет тиры через `model_tiers`).
- Квантованные гейты в `agents/reviewer.md`: `{{GATE_MAX_CRITICAL}}`/
  `{{GATE_COVERAGE_MIN}}`/`{{GATE_MAX_COMPLEXITY}}` — вердикт по порогам, не «на глаз».
- `stack.project_type: "laravel-project"` — канонический детект по ссылке на
  `core.project` (legacy `detect.all_of` сохранён для агент-driven скилла).

### Changed

- `hooks/review-gate.sh` — обобщённый missing-tool guard (путь → исполняемость,
  bare-команда → PATH), теперь verbatim-переиспользуем любым стек-паком.

### Migration notes (agent-facing)

- WATCH на 4 файлах агентов: если frontmatter правлен локально (изменён `model`/добавлены
  скиллы) — апгрейд пометит `conflict`, новый рендер ляжет рядом `*.pack-new`, оригинал не
  затирается; смержи вручную.
- Новые интервью-поля `MODEL_*` (default `inherit`) и `GATE_*` (80/0/10) — на апгрейде
  доспрашиваются авто из дефолтов; рекомендованный профильный пресет: reviewer/spec=opus,
  slice/test=sonnet (его выставляет `profiles/laravel-project.json:model_tiers`).
- `review-gate.sh` (verbatim) — safe-apply, если не правлен локально.

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
