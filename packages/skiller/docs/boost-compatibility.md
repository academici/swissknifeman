# Матрица доверия Laravel Boost

**Политика.** Laravel Boost — доверенный источник версионно-специфичных скиллов и гайдлайнов: он поставляется с пакетами, знает установленные версии (`boost:update`) и обновляется вместе с экосистемой. Наш реестр **не дублирует** Boost, а **дополняет** его архитектурой, проектными конвенциями и практиками, которых в Boost нет. Версионно-специфичная тема → Boost; архитектура/процессы/инфраструктура → swissknifeman.

Дата ревизии: 2026-06-15.

> **Следующий шаг.** Есть проекты, где Boost хотят оставить **только как MCP**, а раздачу
> локального `.ai/` контента на провайдеров (CLAUDE.md/AGENTS.md/Cursor) увести в skiller — см.
> [Раздача локального `.ai/` на провайдеры (dev-план)](./multi-provider-distribution).

**Где живёт Boost:**

- Репозиторий: https://github.com/laravel/boost — скиллы/гайдлайны в [`/.ai/`](https://github.com/laravel/boost/tree/main/.ai) (`*/core.blade.php` и `*/skill/*/SKILL.blade.php` по пакетам и версиям); документация: https://laravel.com/docs/boost
- В установленном проекте: `vendor/laravel/boost/.ai/` (обновляются с composer-пакетом); выбор — `boost.json` проекта; рендер в CLAUDE.md/AGENTS.md — `php artisan boost:update`
- Third-party гайдлайны приходят из самих пакетов через `boost.json::packages` (filament/filament, spatie/laravel-medialibrary, …)
- Карточка источника в реестре: [references/laravel-boost.md](https://github.com/academici/swissknifeman/blob/main/references/laravel-boost.md)

## Таблица 1. Доверенные Boost-скиллы/гайдлайны

| Boost-скилл / гайдлайн | Что это | Статус |
|:---|:---|:---|
| laravel core + 11/12 | базовые и версионные правила фреймворка | trusted |
| php/8.2–8.5 | версионные возможности и правила PHP | trusted |
| pest 3/4 (core + skill) | синтаксис и приёмы Pest по версиям | trusted |
| inertia-laravel + inertia-vue 1/2 | серверная и Vue-часть Inertia по версиям | trusted |
| inertia-react / inertia-svelte | React/Svelte-адаптеры Inertia | trusted, не используем в наших стеках |
| livewire 2/3/4 | версионные правила Livewire | trusted |
| tailwindcss 3/4 | версионные правила Tailwind CSS | trusted |
| wayfinder | генерация типизированных роутов | trusted |
| volt | однофайловые Livewire-компоненты | trusted |
| folio | file-based routing | trusted |
| pennant | feature flags | trusted |
| fluxui free/pro | UI-компоненты Flux | trusted |
| mcp | Laravel MCP (серверы, инструменты) | trusted |
| herd | локальное окружение Herd | trusted |
| sail | Docker-окружение Sail | trusted |
| pint | code style fixer | trusted |
| foundation/enforce-tests | требование тестов на изменения | trusted |
| third-party: filament/filament | гайдлайны Filament из пакета | trusted |
| third-party: spatie/laravel-medialibrary | гайдлайны medialibrary из пакета | trusted |
| third-party: spatie/guidelines-skills | гайдлайны кода Spatie из пакета | trusted |

## Таблица 2. Наши скиллы × Boost

### use-boost — наши дубли удалены из реестра (2026-06-12)

| Был наш скилл | Используем вместо него |
|:---|:---|
| `php/livewire` | Boost livewire 2/3/4 |
| `frontend/tailwindcss` | Boost tailwindcss 3/4 |
| `general/mcp-development` | Boost mcp |

### complementary — Boost даёт версионную базу, наш скилл даёт дельту

| Наш скилл | Boost-источник | Наша дельта |
|:---|:---|:---|
| `php/laravel-best-practices` | laravel-best-practices (Boost) | полный свод для проектов **без** Boost; с Boost — используем Boost-версию |
| `frontend-backend/inertia-vue` | inertia-vue-development | слоистая организация `resources/js/`, проектные конвенции размещения файлов |
| `frontend-wayfinder/wayfinder` | wayfinder-development | ESLint-границы импортов, слой actions/composables |
| `laravel-filament/filament` | filament/filament (third-party) | структура ресурсов, проектные паттерны админки |
| `laravel-extras/medialibrary` | spatie/laravel-medialibrary (third-party) | самодостаточный вариант для проектов без Boost |
| `laravel-testing/laravel-testing` | pest-testing | изоляция тестовой БД, детект окружения, coverage gate |
| `frontend-tailwind/tailwind-conventions` | tailwindcss 3/4 | v4 CSS-first: токены `@theme`, тёмная тема `.dark`+`useAppearance`, `cn()` (clsx+tailwind-merge), сортировка классов Prettier, дисциплина отступов |
| `laravel-data-layer/laravel-data` | spatie/laravel-data (third-party) | авторский паттерн поверх версионного API: вложенные `DataCollection`, casts, `from(request)`, отдача в Inertia/API, `#[TypeScript]` |
| `laravel-extras/spatie-settings` | spatie/laravel-settings (third-party) | самодостаточно для проектов без Boost; привязка формы (Filament) к классу настроек |
| `laravel-livewire/livewire-blade-attributes` | livewire 2/3/4 | дельта-гочизы: атрибуты Blade-компонентов (нет `@if`/`@js()` в списке атрибутов, `ComponentAttributeBag`) |

### ours-only — аналога в Boost нет

`php/laravel-structure`, `php/repositories`, `php/dependency-injection`, `azguard/azguard`, `php/database`, `laravel-architecture/enum-attributes`, `laravel-data-layer/laravel-broadcasting`, `laravel-testing/laravel-dusk`, `php/code-style-spatie`, `php/static-analysis`, `php/laravel`, `laravel-auth/laravel-permissions`, `php/php-patterns`, `laravel-architecture/modular-architecture`, `botkit/botkit`, все `php/laravel-package-*` (scaffold, testing, docs, release, service-provider, compatibility, generate-skill, expressive) и `php-packages/laravel-packages`, `laravel-testing/test-isolation-guard`, `laravel-auth/attribute-authorization`, `laravel-testing/health-checks`, все `devops/docker-*` (а также `devops/ci-cd`, `devops/gitops`, `devops/makefile`, `devops/node-pnpm-preflight`, `devops/db-test-preflight`), `frontend-vite/vite-multi-build`, `frontend-vite/vite-module-loader`, `frontend-vue/vitest`, `frontend-linting/js-code-style`, `frontend-vue/vue-composition-api`, `frontend-backend/backend-type-sync`, `frontend-linting/eslint-flat-config`, `frontend-reka/reka-ui-cva`, `frontend-tailwind/dark-mode`, `frontend-naive-ui/naive-ui-theming`, `frontend-backend/laravel-echo-client`, `frontend/filepond-upload`, `frontend-vue/vue-dynamic-icons`, `frontend-vue/pinia-stores`, и все не-Laravel бакеты целиком: `architect/*`, `blender/*`, `founder/*`, `general/*`, `imported/*`, `operator/*`, `oss-dev/*`, `pm/*`, `python/*`, `quality/*`, `roles/*`.

## Как применять

При старте Laravel-проекта с Boost:

1. Установить Boost-скиллы как есть (`boost.json`, `php artisan boost:update`) — они версионно-специфичны и приоритетны.
2. Наши **complementary**-скиллы подключать ради их дельты (структура, границы, изоляция БД и т.п.) — каждый содержит строку-границу «**Laravel Boost**: …» в секции «Контекст», объясняющую разделение.
3. **use-boost**-скиллы не устанавливаются — они уже удалены из реестра.
4. В проектах **без** Boost complementary-скиллы работают самодостаточно.

Приоритеты источников и роутинг задач — см. [routing](/routing).
