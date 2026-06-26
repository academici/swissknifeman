# Пресеты: именованные кластеры скиллов

Бакеты крупные (`php` — десятки скиллов), а проекту обычно нужен поднабор: один —
Filament-админка, другой — пакет, третий — чистый API. **Пресет** — именованная группа
скиллов, на которую ссылается проектный `.swissknifeman/config.json`, чтобы не перечислять
скиллы руками.

Пресеты — концепт **vendor-канала** (`skiller sync`): они раскрываются в per-skill набор.
В `connect` бакет атомарен, поэтому пресеты там не действуют.

## Формат

`presets/<name>.json` в реестре (рядом с `profiles/`):

```json
{
  "name": "laravel-admin",
  "description": "Админка на Filament: ресурсы/панели, права, авторизация-атрибуты, медиа, настройки",
  "extends": ["laravel-core"],
  "include": ["laravel-filament/filament", "laravel-auth/laravel-permissions", "laravel-auth/attribute-authorization",
              "laravel-extras/medialibrary", "laravel-extras/spatie-settings"]
}
```

- `name` — kebab-case, совпадает с именем файла.
- `extends` — список родительских пресетов (раскрываются рекурсивно, циклы запрещены).
- `include` — скиллы по `"bucket/rel"` (точно) или по `"name"`.
- `buckets` — (опц.) целые бакеты внутри пресета.

## Как применяется

В проектном `.swissknifeman/config.json`:

```json
{ "mode": "vendor", "presets": ["laravel-admin"], "exclude": ["laravel-extras/medialibrary"] }
```

Итоговый набор = **(presets ∪ buckets ∪ include) − exclude**. Пресеты раскрываются в
`buckets`/`include` ДО вычитания, затем `skiller sync` дотягивает `requires` и пишет
`skills-lock.json`. `exclude` бьёт и пресет, и зависимость (с warning).

```bash
skiller sync --dry-run    # план: что развернётся из пресета
skiller sync              # применить → .claude/skills/ + skills-lock.json
```

## Доступные пресеты

> **PHP и Frontend разбиты на тонкие бакеты.** PHP: ядро `php` + `laravel-{testing,filament,livewire,
> data-layer,auth,architecture,extras}` (+ `php-packages`). Frontend: ядро `frontend` + `frontend-{vue,
> nuxt,tailwind,naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}`. Для **одной** области
> бери **бакет** (`buckets: ["laravel-filament"]`). Пресеты ниже — **сквозные стеки**, компонующие
> несколько бакетов (часто php + frontend).

| Область | Пресет | Состав (компонует бакеты) |
|:--|:--|:--|
| php-стек | `laravel-admin` | php + laravel-filament + laravel-auth + laravel-extras |
| php-стек | `laravel-enterprise` | php + laravel-architecture + laravel-auth |
| php+front | `laravel-inertia` | php + laravel-data-layer + frontend-backend + frontend-wayfinder |
| php+front | `laravel-livewire-stack` | php + laravel-livewire + laravel-data-layer |
| frontend | `vue-spa` | frontend + frontend-vue + frontend-vite + frontend-linting + frontend-tailwind |
| front+arch | `figma-to-frontend` | frontend-figma + architect/figma-mcp-core |
| architect | `agents-eval` · `api-data` · `system-design` · `compliance-security` | агенты/оценка · API/данные · арх./стек/observability · безопасность/комплаенс |
| pm | `pm-discovery` · `pm-strategy` · `pm-delivery` · `pm-metrics` | BRD/PMF · GTM/монетизация · PRD/роадмап · unit-экономика |
| general | `agent-context` · `agent-tasks` · `project-conventions` | контекст-дисциплина · постановка задач · конвенции проекта |
| quality | `code-quality` · `testing-quality` | ревью/рефакторинг/долг · стратегия/мутации/E2E |

## Добавить пресет

1. `presets/<name>.json` (`name` = файл, непустой `description`, валидные `extends`/`include`/`buckets`).
2. `bash scripts/validate.sh` — проверит, что токены резолвятся и нет циклов `extends`.
3. `skiller registry` (если индексируется) → PR.

См. также [Vendor-режим](./vendor-mode) (конфиг и поток sync) и [Профили](./profiles)
(автоподбор бакетов по типу проекта).
