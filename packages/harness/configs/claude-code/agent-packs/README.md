# agent-packs — версионируемые паки agent-практик

Пак = версионируемый бандл Claude Code артефактов (агенты/воркфлоу/хуки/settings/доки),
который агент устанавливает и обновляет в проекте. **Раздаёт не код, а данные**:
установку/адаптацию/upgrade выполняет агент по `pack.json` + `CHANGELOG.md` + lock,
без Python/Mustache движка (см. скилл `system/agent-packs` в skiller).

## Структура пака

```
<pack>/
  pack.json        # manifest: version, stack-detect, requires, interview[], files[]
  CHANGELOG.md     # per-pack semver + agent-facing Migration notes
  agents/          # шаблоны .md (name: {{PACK_PREFIX}}-<role>)
  workflows/       # шаблоны .js
  hooks/           # review-gate.sh (verbatim) + .env.ini (template)
  settings/        # settings.fragment.json (merge в .claude/settings.json)
  docs/            # guideline-шаблон
```

## Плейсхолдеры

`{{PLACEHOLDER}}` в файлах `kind: template` подставляются из ответов интервью
(`pack.json:interview`). Блоки `<!-- pack:if KEY -->...<!-- pack:endif -->` агент
оставляет/убирает по булеву ответу. Файлы `kind: verbatim` копируются без правок.

## Установка / upgrade

**Детерминированный путь (рекомендуется)** — CLI `harness agent-packs`: резолвит интервью
из `detect:`-проб+дефолтов БЕЗ агента, рендерит, пишет lock. Так `maind sync`/`maind onboard`
раскатывают паки автоматически (профиль типа проекта называет `agent_pack`):

```bash
harness agent-packs list
harness agent-packs render  --auto --pack <pack> --target . [--answer KEY=VAL ...]
harness agent-packs upgrade        --pack <pack> --target .
harness agent-packs doctor  [--pack <pack>]
```

**Агент-driven путь (фолбэк)** — скилл **`system/agent-packs`** (skiller): для неоднозначных
случаев (`needs-agent`/`conflict`) или прозовой адаптации. Оба пути пишут ОДИН формат
`.claude/agent-pack.lock.json` (sha256 отрендеренного) — совместимы. Upgrade — по
CHANGELOG-дельте с 3-way reasoning через sha256, без diff-движка.

## Реестр ролей ревью (`configs/common/agent-packs/review-roles.json`)

Отдельная extension-таблица (не `role-bindings.json` — тот несёт provider-биндинг
`{pack_id, role_id, model_selector, color}` и не трогается, D126) по ключу
`(pack_id, role_id)`, рядом с каноном тел ролей `configs/common/agent-packs/roles.json`.
Пять записей `role_id: "reviewer"` — **индекс** носителя процедуры ревью (не копия правил):
`projection`/`overrides` — пути к `agents/reviewer.md` и `rules/reviewer-overrides.md`
(compatibility-assets, byte-в-byte проекция канона), `required_sections`/`sections` —
четыре обязательные секции и их ФАКТИЧЕСКИЕ заголовки в паке (не приведены к одному виду —
это правка содержания, вне scope), `dimensions` — измерения ревью из закрытого словаря.
`skills` в реестре НЕТ — это дословный дубль `roles.json.skills`, канон читается напрямую.
Валидатор `harness.reviewroles` (`PYTHONPATH=lib python3 -m harness.reviewroles --check`,
шаг `[8/8]` `scripts/validate.sh`) сверяет реестр с диском и с каноном: двусторонний
default-deny (пак на диске без записи И роль канона без записи), существование projection/
overrides, буквальное совпадение заголовков с `roles.json` `content` (а не с проекцией —
расхождение канона и проекции отдельное нарушение), `dimensions` ⊆ словаря,
`roles.json.skills` ∈ `packages/skiller/skills.json`, `review_version` сверен с
зафиксированным отпечатком состава. Найденный дрейф между паками (разные заголовки одной
секции, разный набор `skills`) — не чинится этим механизмом, это фактическая карта
расхождений (см. `plans/2026.07.25-ECO-OPT/findings/P9.2-review-roles-drift.md`).

## Паки

| Пак | Shape | Стек | Версия |
|---|---|---|---|
| `_common` | agnostic | оркестратор (delegate-only) — общий prerequisite | 0.4.0 |
| `backend-laravel` | backend | Laravel/PHP (приложение) | 0.11.1 |
| `laravel-package` | backend | Laravel-composer-пакет (в т.ч. монорепо `packages/*/src`) | 0.1.0 |
| `node-frontend` | frontend | Vue/Vite/TS (SPA/Inertia/Nuxt) | 0.4.1 |
| `dart-flutter` | mobile | Flutter/Dart (mobile/POS/embedded) | 0.4.1 |
| `python-backend` | backend | Python (FastAPI/Django/Flask) | 0.4.1 |
| `role-tech-lead` | role | tech-lead (sprint/делегирование/ревью) | 0.2.1 |
| `role-cto` | role | startup-CTO (архитектура/tech-radar/AI-viability) | 0.1.1 |
| `role-founder` | role | solo-founder (discovery/MVP/cadence) | 0.1.1 |
| `role-maintainer` | role | OSS-maintainer (триаж/ревью/релиз) | 0.2.1 |

Каждый профиль (`packages/skiller/profiles/<type>.json`) называет `agent_pack` (строка ИЛИ
список — **композиция**: стек-пак + `_common`). Fullstack = композиция по концерну
(`backend-laravel` + `node-frontend`). Роли универсальны, стек выбирает профиль; модельные
тиры — из `profile.model_tiers`. PostToolUse-валидаторы (tsc/eslint, dart analyze, ruff) —
advisory (инжектят ошибки, не блокируют).

### Роль-паки (`role-*`) — кросс-стек, по персоне

`role-*` — **персона-паки** (`shape: role`): субагенты под роль, НЕ под стек. Кросс-стек
(нет `stack.project_type`/`detect` → НЕ авто-привязываются по типу проекта). Доставка
(**вариант A+C**): проект объявляет активные роли в `config.json` (`project.roles: ["tech-lead"]`),
а карта хаба `role_packs` (`{"tech-lead":"role-tech-lead", …}`) маппит роль → пак; `maind sync`
добавляет пак аддитивно к стековому паку профиля (`maind/lib/maind/sync.py:_resolve_agent_pack`).
Тонкий выбор одной роли в проект — также через vendor (`roles/<role>`, поле `role_agent_pack`
во frontmatter скилла). Модельные тиры — **литералами** в `model:` агентов (opus — тяжёлые
суждения: архитектура/планирование/валидация; sonnet — рутина: триаж/ревью/cadence), т.к.
standalone-доставка не получает `profile.model_tiers`.
