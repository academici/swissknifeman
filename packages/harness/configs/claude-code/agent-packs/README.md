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

## Паки

| Пак | Shape | Стек | Версия |
|---|---|---|---|
| `_common` | agnostic | оркестратор (delegate-only) — общий prerequisite | 0.4.0 |
| `backend-laravel` | backend | Laravel/PHP | 0.11.1 |
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
