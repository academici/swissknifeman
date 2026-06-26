# mattpocock/skills

- **URL:** https://github.com/mattpocock/skills
- **Лицензия:** MIT (© 2026 Matt Pocock)
- **Статус:** imported
- **Проверено:** 2026-06-26 (HEAD `5d78bd09`)

Battle-tested инженерные скиллы Matt Pocock (TotalTypeScript). Сильная методология
(Ousterhout «Philosophy of Software Design», Feathers «Working Effectively with Legacy Code»),
а не шаблоны. Ориентация — Node/TS и один мейнтейнер; у нас мульти-стек (PHP/Laravel, Dart/Flutter,
embedded, финтех). Прямая замена невозможна — берём методологию точечно, локализация примеров (PHP/Dart)
отдельной волной (faithful-first).

Ключевая находка источника — явная **двухъярусная активация** (`skills/engineering/README.md`):
скиллы делятся на **user-invoked** (`disable-model-invocation: true` — только явный вызов) и
**model-invoked** (богатый `description` → авто-триггер). Эту классификацию переносим один-в-один
в наши условия активации.

## Что взято (первая волна → upstream.json, strategy notify)

| mattpocock | наш таргет | активация |
|---|---|---|
| diagnosing-bugs | `quality/diagnosing-bugs` | model-invoked (авто) |
| tdd | `quality/tdd-discipline` | model-invoked (авто) |
| codebase-design | `architect/codebase-design` | model-invoked (авто) |
| domain-modeling | `architect/domain-modeling` | model-invoked (авто) |
| implement | `general/implement` | **user-invoked** (пишет код) |
| to-issues | `oss-dev/to-issues` | **user-invoked** (постит в GitHub) |
| triage | `oss-dev/issue-triage` | **user-invoked** (через агента) |
| grill-with-docs | `general/grill-with-docs` | **user-invoked** (явная сессия) |
| resolving-merge-conflicts | `oss-dev/resolving-merge-conflicts` | model-invoked (авто) |

Под-файлы источника (DEEPENING/DESIGN-IT-TWICE, CONTEXT-FORMAT/ADR-FORMAT, AGENT-BRIEF/OUT-OF-SCOPE,
tests/mocking, HTML-REPORT) → наши `snippets/` (ярус-2 on-demand).

## Точечно (EXTEND, без отдельного скилла)

- **to-prd** → усиливает `general/spec-interview` (грилинг-строгость) + форма PRD остаётся `pm/prd-from-brd`.
- **improve-codebase-architecture** → HTML-REPORT.md как опциональный snippet в `architect/codebase-design`;
  ссылка из `quality/refactoring-plan`. Отдельный скилл не делаем (дубль refactoring-plan + codebase-design).
- **grill-with-docs** — у источника тонкий враппер «`/grilling` + `/domain-modeling`»; у нас =
  `spec-interview` (наш грилинг) + `architect/domain-modeling`, строит CONTEXT.md/ADR инлайн.

## В harness, не скилл

- **git-guardrails-claude-code** — у нас хуки/permissions принадлежат пакету `harness`.
  Скрипт `block-dangerous-git.sh` + PreToolUse-пресет → `packages/harness/configs/claude-code/hooks/`,
  раздаётся через `harness hooks` (+ опц. тонкий `general/git-safety`, `lifecycle:init`).

## Не брать

- **setup-pre-commit** — Husky/lint-staged, JS-специфика (отложено; позже PHP-аналог в `devops`).
- **prototype** — частично покрыто; отложено, заметка в `implement`/`spec-interview`.
- **scaffold-exercises**, **migrate-to-shoehorn**, **ask-matt** — обучение/личные инструменты/персональный роутер.
- **setup-matt-pocock-skills** — bootstrap его репо; изучить как образец будущего `setup-swissknifeman`.

## Целевые бакеты

`quality/`, `architect/`, `general/`, `oss-dev/` (методология, fold-in, без нового бакета).
Раздача — opt-in через `presets/` (`agent-tasks`, `code-quality`, `system-design`, новый
`engineering-workflow`), НЕ в CORE.

## Цепочка (встраивание, не папки)

`spec-interview → grill-with-docs(+domain-modeling) → to-issues → implement → tdd-discipline → code-review`;
`diagnosing-bugs → code-review`; `codebase-design → refactoring-plan/architecture`. Рёбра — через
`requires/produces_for`, агенты грузят через `skills:` (issue-triager←issue-triage, sprint-planner←to-issues,
review-gatekeeper←diagnosing-bugs/tdd-discipline).
