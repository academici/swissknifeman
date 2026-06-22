# Реестр скиллов swissknifeman

<!-- GENERATED `skiller registry` — не редактировать вручную -->

Источник истины портируемых скиллов (машинный реестр — `skills.json`). Раздача в проекты: `skiller connect` (плагины-бакеты) / `vendor` (физ. перенос). CORE-набор токен-скиллов (`general`/`oss-dev`) раздаётся по умолчанию — см. `connect`/`vendor`.

Всего: 184 скиллов в 17 бакетах.

## Скиллы по бакетам

### architect — Architecture, API and data design, security, observability, tech stack selection (11)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `agent-design` | Проектирование агентов, agentic loop, tool contracts, harness, permission gates | `agentic`, `architecture`, `security`, `validation` |
| `api-design` | Проектирование REST/GraphQL API, эндпоинтов, контрактов, версионирования, аутентификации | `api`, `architecture`, `rest`, `contracts` |
| `architecture` | Архитектура системы, выбор стека, ADR, C4-диаграммы, deployment, scalability | `architecture`, `adr`, `c4`, `scalability`, `deployment` |
| `data-schema` | Схема данных, сущности, атрибуты, связи. Агностично к СУБД — только markdown-таблицы | `data`, `architecture`, `schema`, `entities`, `erd` |
| `eval-design` | Оценка качества LLM/AI-выводов — eval-set, метрики, regression-харнес, automated + human … | `agentic`, `validation`, `llm`, `metrics`, `testing` |
| `figma-mcp-core` | Дисциплина работы с официальным Figma Dev Mode MCP: реальные инструменты (get_metadata, g… | `figma`, `mcp`, `design-system`, `design-tokens`, `dev-mode`, `code-connect`, `ui` |
| `legal-compliance` | GDPR, CCPA, AI Act, DMCA, COPPA, DSA — чеклист регуляторных требований до запуска | `compliance`, `gdpr`, `privacy`, `ai-act`, `regulatory` |
| `observability-design` | Logging, metrics, tracing, alerting. SLO/SLI, error budget, runbooks для прод-готовности | `observability`, `logging`, `metrics`, `tracing`, `alerting`, `slo`, `runbook` |
| `package-contribution-protocol` | Гейт против раздувания зависимого пакета из проекта-потребителя: Rule of Three, proposal→… | `governance`, `package`, `monorepo`, `contribution`, `semver`, `anti-bloat`, `boundary` |
| `security-design` | Классификация данных, auth-стратегия, RBAC/ABAC, OWASP Top 10, GDPR, STRIDE threat modeli… | `security`, `compliance`, `auth`, `owasp`, `threat-modeling`, `rbac`, `gdpr`, `privacy`, `stride` |
| `tech-stack-selection` | Выбор технологического стека с trade-off матрицей до архитектурного дизайна. ADR-первый ш… | `stack-choice`, `architecture`, `adr`, `trade-off` |

### blender — Universal Blender bpy+MCP tooling: MCP workflow primitives, viewport modes, camera helper, version gotchas (2)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `mcp-blender` | MCP Blender: инструменты (execute_blender_code, get_object_info, get_viewport_screenshot,… | `blender`, `mcp`, `python`, `3d`, `bpy`, `viewport`, `camera`, `screenshot`, `orchestration` |
| `version-gotchas` | Известные breaking changes и ловушки Blender 5.0 API | `blender`, `api`, `bpy`, `3d`, `python`, `gotchas`, `advisory`, `version` |

### blender-modeling — Parametric CAD modeling in Blender for FDM/SLA: config-driven dataclasses, profile/revolve geometry, threading clearances, config & scene conventions, model-rules template, generic build loop (6)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `build-loop` | Дисциплина цикла параметрического моделирования через MCP Blender: анализ задачи → провер… | `blender`, `cad`, `parametric`, `workflow`, `bpy`, `mcp`, `3d`, `fdm`, `sla` |
| `config-conventions` | Соглашения параметрического CAD-конфига: одна сущность — один dataclass; именование перем… | `blender`, `cad`, `parametric`, `dataclass`, `config`, `cross-config`, `conventions`, `bpy`, `fdm`, `sla` |
| `model-rules` | Шаблон models/{name}/ai/rules.md — моделе-специфичные правила, читаемые агентом перед люб… | `blender`, `template`, `rules`, `3d`, `cad`, `conventions` |
| `parametric-config` | Параметрическое 3D-моделирование в Blender (bpy) на основе конфига-данных: dataclass-пара… | `blender`, `bpy`, `parametric`, `dataclass`, `cad`, `fdm`, `sla`, `geometry`, `units`, `python`, `3d` |
| `scene-conventions` | Соглашения сцены параметрической модели: префиксы объектов (MESH_/CRV_/LGT_/MTL_), иерарх… | `blender`, `cad`, `parametric`, `naming`, `scene`, `materials`, `parenting`, `bpy` |
| `threading` | Резьба на FDM/SLA-деталях: материал, физика печати, радиальные зазоры по типу посадки | `blender`, `3d`, `fdm`, `sla`, `threading`, `geometry`, `bpy` |

### devops — Docker environments, CI/CD pipelines, GitOps (11)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `ci-cd` | GitHub Actions / GitLab CI пайплайны для Laravel: lint, тесты, build, release + security-… | `ci`, `github-actions`, `gitlab-ci`, `laravel`, `devops`, `release`, `security`, `coverage` |
| `db-test-preflight` | Пре-флайт проверка тестовой БД (Postgres в Docker) ПЕРЕД запуском тестов: контейнер подня… | `postgres`, `docker`, `testing`, `preflight`, `devops`, `ci`, `isolation` |
| `docker` | Advanced Docker containerization expertise: container optimization, security hardening, m… | `docker`, `devops` |
| `docker-dev-prod` | Разнесение docker-compose на dev (build + bind-mount) и prod (готовый образ + named volum… | `docker`, `devops`, `compose`, `laravel` |
| `docker-php` | Production-ready PHP Docker образ: alpine-fpm или всё-в-одном serversideup/php (FPM+Nginx… | `docker`, `php`, `devops`, `laravel` |
| `docker-postgres` | PostgreSQL в Docker: healthcheck pg_isready, named volume данных, init-скрипт создания те… | `docker`, `devops`, `postgres`, `testing` |
| `docker-services` | Полный сервисный стек Laravel из одного образа: app (fpm-nginx), queue, scheduler, reverb… | `docker`, `devops`, `compose`, `laravel`, `queue`, `websocket` |
| `docker-vite` | Vite dev server отдельным compose-сервисом для Laravel: named volume для node_modules, HM… | `docker`, `devops`, `vite`, `frontend`, `laravel` |
| `gitops` | Командная Git-стратегия: модель веток (main/develop/feature/hotfix), PR-workflow, защита … | `git`, `gitops`, `github` |
| `makefile` | Makefile как единая точка входа: help, .PHONY, алиасы Docker-команд; паттерн делегирующег… | `make`, `devops`, `docker` |
| `node-pnpm-preflight` | Проверка доступности Node/pnpm на хосте перед командами и git hooks, которые используют p… | `node`, `pnpm`, `devops`, `preflight`, `ci` |

### founder — Idea discovery, competitive analysis, risk assessment, pitch decks (9)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `adversarial-check` | Структурированный «адвокат дьявола» — 3 сильнейших контраргумента, failed competitors, не… | `validation`, `market` |
| `competitive-analysis` | Анализ рынка, конкурентов, JTBD, незанятая ниша, вектор атаки. Использует Perplexity sear… | `discovery`, `market`, `gtm` |
| `customer-discovery` | Систематическое discovery — target profile, interview framework (прошлое не будущее), pos… | `discovery`, `validation`, `market` |
| `defensibility` | Moat-анализ для Scale-стадии — accumulated depth, data flywheel, workflow lock-in, domain… | `market`, `validation` |
| `idea-discovery` | Структурированный опрос по сырой идее — JTBD, problem statement, hypothesis, перед compet… | `discovery`, `requirements`, `market` |
| `new-project` | Запуск нового стартап-проекта: концепция, конкуренты, риски, полная структура папок | `discovery`, `requirements`, `market`, `gtm` |
| `pitch-deck` | 10-слайдовая инвесторская дека по канону YC/Sequoia на основе готовых артефактов проекта | `gtm`, `market`, `monetization` |
| `risk-assessment` | 5 категорий рисков, Risk Matrix, RAID-лог, pre-mortem для критичных рисков | `validation`, `compliance`, `security` |
| `startup-lifecycle` | 4 стадии AI-native стартапа (Idea→MVP→Launch→Scale) с exit-criteria, failure modes и анти… | `validation`, `requirements`, `market` |

### frontend — Frontend development: Vite, Vue Composition API, Tailwind CSS, Inertia (35)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `antfu` | Anthony Fu's opinionated tooling and conventions for JavaScript/TypeScript projects. Use … |  |
| `backend-type-sync` | Синхронизация типов backend→frontend через spatie/laravel-typescript-transformer: #[TypeS… | `typescript`, `laravel`, `spatie`, `types`, `enum`, `dto`, `frontend`, `type-sync`, `ci` |
| `dark-mode` | Тёмная тема light\|dark\|system на Vue 3: composable useDarkMode (matchMedia prefers-colo… | `dark-mode`, `theme`, `vue`, `composable`, `ssr`, `tailwind`, `matchmedia`, `localstorage` |
| `document-writer` | Use when writing blog posts or documentation markdown files - provides writing style guid… |  |
| `eslint-flat-config` | ESLint flat config (eslint.config.js) для Vue 3 + TypeScript: defineConfigWithVueTs/types… | `eslint`, `prettier`, `flat-config`, `vue`, `typescript`, `stylistic`, `tooling`, `code-style`, `frontend` |
| `figma-to-vue` | Маппинг дизайна из Figma Dev Mode MCP в Vue + Tailwind v4: Auto-layout → flexbox/grid, to… | `figma`, `vue`, `tailwind`, `tailwindcss-v4`, `cva`, `design-tokens`, `dark-mode`, `auto-layout` |
| `filepond-upload` | Загрузка файлов через FilePond в Vue + Laravel: регистрация vue-filepond и плагинов (vali… | `filepond`, `vue`, `laravel`, `file-upload`, `frontend`, `forms`, `image-preview`, `inertia`, `uploads` |
| `inertia-vue` | Inertia + Vue в Laravel: страницы, формы, навигация и слоистая организация resources/js (… | `inertia`, `vue`, `laravel`, `frontend`, `architecture`, `structure` |
| `js-code-style` | Стиль JS/TS по Spatie: 4 пробела, ширина 120, одинарные кавычки, const-first, строгое ===… | `javascript`, `typescript`, `code-style`, `spatie`, `prettier`, `vue` |
| `laravel-echo-client` | Фронтовый realtime-клиент Laravel Echo (Reverb/Pusher) во Vue 3: настройка Echo из runtim… | `laravel-echo`, `reverb`, `pusher`, `websockets`, `realtime`, `vue`, `broadcasting`, `frontend` |
| `motion` | Use when adding animations with Motion Vue (motion-v) - provides motion component API, ge… |  |
| `naive-ui-theming` | Глобальная тема Naive UI: GlobalThemeOverrides (common + Button/Card/Form/Input/Tag/Tabs…… | `naive-ui`, `vue`, `theming`, `design-tokens`, `dark-mode`, `tailwind`, `frontend`, `components`, `ui` |
| `nuxt` | Use when working on Nuxt 4+ projects - provides server routes, file-based routing, middle… |  |
| `nuxt-modules` | Use when creating Nuxt modules: (1) Published npm modules (@nuxtjs/, nuxt-), (2) Local pr… |  |
| `nuxt-seo` | Nuxt SEO meta-module with robots, sitemap, og-image, schema-org. Use when configuring SEO… |  |
| `pinia` | Pinia official Vue state management library, type-safe and extensible. Use when defining … |  |
| `pinia-stores` | Pinia (Vue 3) — глобальное состояние: setup-сторы (defineStore с функцией), ref=state/com… | `pinia`, `vue`, `frontend`, `state-management`, `store`, `architecture` |
| `reka-ui-cva` | Библиотека UI-компонентов на headless-примитивах Reka UI + варианты class-variance-author… | `reka-ui`, `cva`, `vue`, `tailwind`, `headless`, `components`, `variants`, `design-system`, `ui`, `frontend` |
| `tailwind-conventions` | Конвенции Tailwind CSS v4 для Laravel/Vue: CSS-first конфиг (@import tailwindcss, @theme-… | `tailwind`, `tailwindcss-v4`, `css`, `vue`, `laravel`, `dark-mode`, `design-tokens`, `prettier` |
| `ts-library` | Use when authoring TypeScript libraries or npm packages - covers project setup, package.j… |  |
| `vite` | Vite build tool configuration, plugin API, SSR, and Vite 8 Rolldown migration. Use when w… |  |
| `vite-module-loader` | Vite как основной сборщик Frontend-проектов: базовая конфигурация, алиасы, build-практики | `vite`, `frontend`, `build`, `laravel`, `vue` |
| `vite-multi-build` | Две независимые Vite-сборки в одном Laravel-проекте: основное приложение и Filament-админ… | `vite`, `laravel`, `filament`, `tailwind`, `build`, `multi-config`, `frontend` |
| `vitepress` | VitePress static site generator powered by Vite and Vue. Use when building documentation … |  |
| `vitest` | Vitest для Vue/Inertia-проекта на Laravel: jsdom, globals, тесты в resources/js/tests зер… | `vitest`, `testing`, `vue`, `coverage`, `jsdom`, `laravel`, `frontend` |
| `vitest-vue` | Vitest fast unit testing framework powered by Vite with Jest-compatible API. Use when wri… |  |
| `vue` | Vue 3 Composition API, script setup macros, reactivity system, and built-in components. U… |  |
| `vue-best-practices` | MUST be used for Vue.js tasks. Strongly recommends Composition API with `<script setup>` … |  |
| `vue-composition-api` | Проектные конвенции Composition API: ref-first и паттерн composables. НЕ справочник API (… | `vue`, `frontend`, `composable`, `patterns` |
| `vue-dynamic-icons` | Vue: один компонент-иконка, выбирающий SVG по строковому имени из набора (lucide-vue-next… | `vue`, `icons`, `dynamic-component`, `lucide`, `typescript`, `frontend` |
| `vue-router-best-practices` | Vue Router 4 patterns, navigation guards, route params, and route-component lifecycle int… |  |
| `vue-testing-best-practices` | Use for Vue.js testing. Covers Vitest, Vue Test Utils, component testing, mocking, testin… |  |
| `vueuse-functions` | Apply VueUse composables where appropriate to build concise, maintainable Vue.js / Nuxt f… |  |
| `wayfinder` | Laravel Wayfinder: типобезопасные роуты и controller actions для фронтенда. Генерация, им… | `wayfinder`, `laravel`, `typescript`, `routes`, `inertia`, `eslint`, `frontend` |
| `web-design-guidelines` | Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI",… |  |

### general — General agent workflow conventions: git commits, task briefs, project maps, cross-layer checklists (17)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `ai-context-workflow` | Редактирование AI-контекста проекта: .ai/guidelines, .ai/skills, boost.json; запрет правк… | `ai`, `workflow`, `conventions`, `ai-context`, `skills`, `laravel` |
| `anti-drift` | Дисциплина против «закапывания» агента: думай до кода, простота прежде всего, хирургическ… | `workflow`, `discipline`, `orchestration`, `context` |
| `compact-responses` | Activate to switch Claude into ultra-compact response mode: minimal prose, code-only answ… | `conventions`, `style`, `tokens`, `context`, `workflow` |
| `complex-task-orchestrator` | Оркестрация сложных задач: декомпозиция, контекст-роутинг, управление рисками, Definition… | `workflow`, `orchestration`, `checklist`, `agents` |
| `context-economy` | Экономия контекста Claude Code в проекте: CLAUDE.md ≤200 строк, path-scoped правила .clau… | `tokens`, `context`, `claude-code`, `workflow`, `conventions` |
| `cross-layer-change-checklist` | Универсальный checklist для изменений, затрагивающих несколько слоев: код, доступы, UI, д… | `checklist`, `workflow`, `validation` |
| `git-commit-rules` | Правила работы с Git в проекте: подготовка коммита, husky/commitlint, формат сообщений и … | `git`, `conventions`, `conventional-commits`, `gitops` |
| `naming-conventions` | Дисциплина именования сущностей (язык-агностично): имя раскрывает намерение, а не реализа… | `naming`, `conventions`, `readability`, `code-style`, `discipline`, `clean-code` |
| `packages-stack` | Реестр используемых внешних NPM и Composer пакетов. Опирайся на официальную документацию … | `dependencies`, `conventions`, `laravel`, `vue`, `navigation` |
| `project-map` | Быстрая карта структуры проекта и зон ответственности по директориям для безопасного роут… | `conventions`, `navigation`, `laravel`, `architecture`, `structure` |
| `session-handoff` | Передача контекста между сессиями и агентами: сжатие сессии в структурированный handoff-д… | `workflow`, `context`, `tokens`, `handoff` |
| `skills-ssot` | Единый источник истины скиллов для нескольких AI-агентов: .ai/skills + симлинки, gitignor… | `ai-context`, `skills`, `ssot`, `workflow`, `conventions`, `ai` |
| `spec-interview` | Интервью перед кодом: агент задаёт вопросы по одному, сам читает кодовую базу где может, … | `workflow`, `requirements`, `discovery` |
| `task-brief-template` | Шаблон постановки сложных задач для агента: цель, границы, инварианты, явные предположени… | `workflow`, `template`, `requirements`, `context` |
| `ticket-workflow` | Use for ticket domain logic: Actions, Services, Repositories, Observers, Policies, Notifi… | `workflow`, `domain`, `laravel`, `authorization`, `repository`, `architecture` |
| `user-roles` | Use when working with UserRole enum, user permissions, role priority resolution, or any c… | `roles`, `authorization`, `laravel`, `php`, `enum`, `permissions`, `reflection` |
| `writing-style` | Тон и язык кодовых артефактов: русский по умолчанию для комментариев, тел коммитов, описа… | `writing`, `language`, `russian`, `comments`, `commits`, `tests`, `docs`, `style` |

### imported — External super-skills tracked via upstream.json (marketing, sales, legal, research and more) (12)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `agent-security-super-skill` | Comprehensive AI agent security skill covering prompt injection defense, skill/plugin val… |  |
| `ai-agent-super-skill` | Comprehensive AI agent building skill merging Perplexity Computer's skill creation, webse… |  |
| `content-creative-super-skill` | Comprehensive creative studio skill merging Perplexity Computer's video production, speec… |  |
| `dev-engineering-super-skill` | Comprehensive full-stack development and engineering skill merging Perplexity Computer's … |  |
| `finance-super-skill` | Comprehensive finance and accounting skill merging Perplexity Computer's 7 finance skills… |  |
| `legal-super-skill` | Comprehensive legal operations skill merging Perplexity Computer's 6 legal skills with Cl… |  |
| `marketing-super-skill` | Comprehensive end-to-end marketing skill merging Perplexity Computer's 6 built-in marketi… |  |
| `operations-cx-super-skill` | Comprehensive operations and customer experience skill merging Perplexity Computer's 5 CX… |  |
| `pm-super-skill` | Comprehensive product management skill merging Perplexity Computer's 6 PM skills with Cla… |  |
| `research-knowledge-super-skill` | Comprehensive research and knowledge management skill merging Perplexity Computer's resea… |  |
| `sales-super-skill` | Comprehensive end-to-end sales skill merging Perplexity Computer's 6 built-in sales skill… |  |
| `token-efficient` | Reduces Perplexity Computer output verbosity and token waste. Eliminates sycophantic open… |  |

### mobile — Mobile development: Flutter — design-to-code, theming, layout mapping from Figma (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `figma-to-flutter` | Маппинг дизайна из Figma Dev Mode MCP в Flutter: Auto-layout → Row/Column/Expanded/Paddin… | `figma`, `flutter`, `dart`, `mobile`, `design-tokens`, `theming`, `auto-layout` |

### operator — Incident response, runbooks, postmortems, on-call and capacity planning (5)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `capacity-planning` | Планирование capacity — load forecasting, headroom, autoscaling policy, cost budget, что … | `ops`, `observability`, `monitoring`, `sla` |
| `incident-response` | Процесс реагирования на инциденты в проде — severity-уровни, роли (IC/Comms/SME), коммуни… | `incident`, `ops`, `workflow`, `sla` |
| `oncall-rotation` | Дизайн on-call ротации — расписание, primary/secondary, handoff, compensation, defusing b… | `ops`, `incident`, `sla`, `handoff` |
| `postmortem` | Blameless postmortem после SEV-1/2 инцидента — таймлайн, root cause (5 Whys), contributin… | `incident`, `ops`, `workflow`, `reflection` |
| `runbook` | Шаблон operational runbook на каждый P1/P2-алерт — symptoms, диагностика, mitigation step… | `ops`, `incident`, `template`, `monitoring` |

### oss-dev — Open-source development: releases, governance, DX, dependency audits + language references (7)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `dependency-audit` | Аудит зависимостей: lockfile sanity, vuln scan, лицензионная совместимость, supply-chain … | `oss`, `compliance`, `security`, `dependencies`, `php` |
| `dx-design` | Developer Experience: README, quick-start (≤ 60 сек), API ergonomics, error messages, тип… | `oss`, `documentation`, `api`, `cli` |
| `gh-review` | Ревью и хендофф изменений через GitHub CLI (gh) с экономией контекста: gh pr diff/view/co… | `github`, `gh`, `review`, `handoff`, `tokens`, `context` |
| `github-flow` | Цепочка Issue → Branch → PR → Merge → Tag → Release на GitHub: naming, labels, SemVer-ора… | `oss`, `github`, `git`, `semver`, `release` |
| `oss-development` | OSS-проект: repo structure, README, Architecture, ADR, SemVer, CI/CD. PHP-специфика в ../… | `oss`, `architecture`, `documentation`, `ci` |
| `oss-governance` | LICENSE, CoC, CONTRIBUTING, MAINTAINERS, RFC-процесс, security policy для OSS-проекта | `oss`, `compliance`, `license`, `security`, `documentation` |
| `release-engineering` | SemVer-стратегия, CHANGELOG, релизный pipeline (CI/CD), pre-releases, deprecation policy … | `oss`, `semver`, `release`, `changelog`, `ci` |

### php — PHP and Laravel: applications, packages, Filament, permissions, testing, patterns (42)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `attribute-authorization` | Декларативная авторизация на уровне методов контроллера через атрибут #[CheckPermission] … | `php`, `laravel`, `authorization`, `attribute`, `reflection`, `middleware`, `gate`, `enum`, `permissions`, `rbac` |
| `azguard` | Роли и контроль доступа на базе пакета azguard: code-first RBAC, панели, scoped roles, di… | `php`, `laravel`, `permissions`, `azguard`, `rbac`, `authorization`, `gate`, `enum` |
| `botkit` | Bot framework patterns: BotDefinition contract, package service provider, webhook handling | `php`, `laravel`, `bots`, `botkit` |
| `code-style-spatie` | Стиль кода Laravel/PHP по гайдлайнам Spatie: Laravel-конвенции прежде PSR-12, типизация в… | `php`, `laravel`, `code-style`, `spatie` |
| `database` | Database migrations, models, and table naming. Activate when writing migrations, creating… | `php`, `laravel`, `database`, `migrations` |
| `dependency-injection` | Взаимодействие слоёв через constructor injection: final readonly + promotion, матрица инъ… | `php`, `laravel`, `di`, `architecture` |
| `enum-attributes` | Активируй при работе с метаданными enum: когда match-простыни label()/color()/description… | `php`, `enum`, `attributes`, `reflection`, `laravel`, `patterns`, `typescript` |
| `enum-state-machine` | Активируй, когда статус домена (Order/Document/Subscription) растёт в граф переходов: еди… | `php`, `enum`, `state-machine`, `workflow`, `laravel`, `transitions`, `domain`, `actions` |
| `filament` | Filament v5 — Panels, Resources, Schemas, Tables, Widgets, Actions: структура файлов, CLI… | `php`, `laravel`, `filament`, `ui`, `admin-panel`, `crud`, `livewire` |
| `health-checks` | spatie/laravel-health в Laravel: кастомные Check-классы (диск, очередь, heartbeat шедулер… | `laravel`, `health`, `monitoring`, `spatie`, `liveness`, `readiness`, `observability` |
| `laravel` | Laravel architecture patterns: actions, repositories, resources | `php`, `laravel`, `architecture`, `patterns` |
| `laravel-best-practices` | Лучшие практики Laravel: 20 категорий правил (Eloquent, валидация, кеш, очереди, безопасн… | `php`, `laravel`, `best-practices` |
| `laravel-broadcasting` | Laravel Echo + Reverb/Pusher/Ably: broadcast-события, авторизация каналов, presence/whisp… | `php`, `laravel`, `broadcasting`, `echo`, `reverb`, `websockets`, `realtime` |
| `laravel-data` | DTO на spatie/laravel-data: типизированные Data-классы, вложенные DataCollection, casts/t… | `php`, `laravel`, `spatie`, `laravel-data`, `dto`, `data-transfer-object`, `casts`, `validation`, `inertia`, `api` |
| `laravel-dusk` | Laravel Dusk: браузерные E2E-тесты, изолированная тестовая БД, запуск из Docker через hos… | `php`, `laravel`, `dusk`, `e2e`, `browser-testing`, `chromedriver`, `docker` |
| `laravel-package-compatibility` | Use this skill when reviewing Laravel package compatibility across composer constraints, … | `php`, `laravel`, `package-dev` |
| `laravel-package-docs` | Use this skill when writing or revising package documentation after creating a package fr… | `php`, `laravel`, `package-dev` |
| `laravel-package-expressive` | Upstream-скилл для работы НАД самим пакетом WendellAdriel/laravel-expressive (starter kit… | `php`, `laravel`, `package-dev` |
| `laravel-package-generate-skill` | Use this skill when creating or updating the bundled Laravel Boost skill under resources/… | `php`, `laravel`, `package-dev` |
| `laravel-package-release` | Use this skill when preparing Laravel package releases: generated release notes, GitHub r… | `php`, `laravel`, `package-dev` |
| `laravel-package-scaffold` | Use this skill when adding Laravel package capabilities or package shape changes after cr… | `php`, `laravel`, `package-dev` |
| `laravel-package-service-provider` | Use this skill when changing a Laravel package service provider: config merges, routes, v… | `php`, `laravel`, `package-dev` |
| `laravel-package-testing` | Use this skill when writing, editing, fixing, or reviewing package tests with Pest 4 and … | `php`, `laravel`, `package-dev` |
| `laravel-packages` | Создание Laravel-пакетов: scaffold, тесты, публикация скиллов пакета потребителям через v… | `php`, `laravel`, `package-dev`, `skills` |
| `laravel-permissions` | Ручной/нативный Laravel RBAC: policies, gates, entity-scoped permissions без спец-пакета.… | `php`, `laravel`, `permissions`, `azguard`, `rbac`, `authorization` |
| `laravel-security-audit` | Аудит Laravel-кода на «острые грани»: raw-запросы Eloquent, mass assignment, XSS в Blade,… | `php`, `laravel`, `security` |
| `laravel-structure` | Канон структуры Laravel-проекта для greenfield-проектов и добавления доменов: доменная та… | `php`, `laravel`, `architecture`, `structure` |
| `laravel-subagents` | Оркестрация субагентов на крупных Laravel-задачах: порог срабатывания, делегирование иссл… | `workflow`, `orchestration`, `agents`, `laravel` |
| `laravel-testing` | Feature/unit/pest testing patterns: изоляция тестовой БД, детект Docker/локального окруже… | `php`, `laravel`, `testing` |
| `livewire-blade-attributes` | Дельта-гочизы Livewire 3 по атрибутам Blade-компонентов. Активировать при написании/ревью… | `livewire`, `blade`, `laravel`, `frontend`, `advisory`, `gotchas` |
| `medialibrary` | spatie/laravel-medialibrary: привязка файлов к Eloquent-моделям, коллекции, конверсии, по… | `php`, `laravel`, `media`, `spatie`, `uploads`, `images` |
| `modular-architecture` | Масштабирование Laravel-кода при росте: организация по бизнес-доменам, Модульный Монолит … | `php`, `laravel`, `architecture`, `nwidart`, `laravel-modules`, `filament` |
| `named-arguments` | Правило обязательных именованных аргументов в PHP: вызовы методов/функций, исключения, ак… | `php`, `code-style`, `readability`, `conventions` |
| `naming-conventions` | Именование сущностей Laravel/PHP: методы репозиториев по намерению (а не findByCodeOrFail… | `php`, `laravel`, `naming`, `conventions`, `code-style`, `readability` |
| `pao` | Laravel PAO — агентно-оптимизированный вывод PHP-инструментов: PHPUnit/Pest/Paratest/PHPS… | `php`, `laravel`, `testing`, `tokens`, `agent-output` |
| `pennant-development` | Laravel Pennant — feature-флаги: define/active/for-scope, директива @feature, активация/д… | `php`, `laravel`, `pennant`, `feature-flags` |
| `php-patterns` | PHP domain patterns: VO, DTO, pipeline, specification | `php`, `laravel`, `patterns`, `dto`, `architecture` |
| `php-upgrade-checklist` | Чеклист апгрейда версии PHP в приложении (минор/мажор): обновить образ/CI, composer updat… | `php`, `upgrade`, `version`, `rector`, `phpstan`, `composer` |
| `repositories` | Система репозиториев Laravel: read/store split, model scopes, delta-DTO, фасад, Visibilit… | `php`, `laravel`, `repository`, `architecture` |
| `spatie-settings` | spatie/laravel-settings: типизированные классы настроек (extends Settings, public-свойств… | `php`, `laravel`, `spatie`, `settings`, `filament`, `configuration` |
| `static-analysis` | Статический анализ и линтинг PHP/Laravel: Laravel Pint, PHPStan и Rector локально и в CI,… | `php`, `laravel`, `quality` |
| `test-isolation-guard` | Защита тестов Laravel от запуска по боевой/dev БД и медиа-диску: bootstrap.php выставляет… | `php`, `laravel`, `testing`, `isolation`, `safety`, `database`, `ci`, `refreshdatabase` |

### pm — Product management: BRD, PRD, roadmap, monetization, unit economics (9)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `brd` | Business Requirements Document: функциональные требования, user stories, acceptance crite… | `requirements`, `template` |
| `business-process` | Бизнес-процессы, workflow, FSM, sequence/state-диаграммы, обработка ошибок | `requirements`, `workflow` |
| `go-to-market` | GTM-стратегия, ICP, messaging framework, каналы привлечения, launch plan | `gtm`, `market`, `monetization` |
| `monetization-design` | Выбор бизнес-модели (SaaS / marketplace / ads / freemium / hybrid) с trade-off матрицей и… | `monetization`, `market` |
| `pmf-diagnostics` | Диагностика product-market fit — measurement framework до launch, Sean Ellis test (>40%),… | `validation`, `market` |
| `prd-from-brd` | Product Requirements Document — разворачивает BRD в детальные user stories с acceptance c… | `requirements`, `template` |
| `product-roadmap` | MVP definition, Impact/Effort приоритизация, фазы MVP → v1 → v2 → Backlog, метрики перехо… | `requirements`, `gtm`, `market` |
| `requirement-critic` | Аудит BRD: полнота, конфликты, допущения, gap-анализ, MoSCoW. Только в чат, файл не созда… | `requirements`, `validation` |
| `unit-economics` | Unit economics: LTV, CAC, payback, churn, break-even, 3 сценария | `monetization` |

### python — Python: ML project structure, virtualenv and dependency management (2)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `ml-project-structure` | Стандартизированная структура ML/Data Science проектов по подходу Cookiecutter Data Scien… | `python`, `ml`, `structure`, `architecture`, `data`, `conventions` |
| `venv-dependencies` | Управление зависимостями и виртуальными окружениями Python для воспроизводимости проектов | `python`, `venv`, `dependencies`, `tooling`, `quality`, `conventions` |

### quality — Code review, refactoring plans, tech debt audits, test strategy (8)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `code-review` | Процесс и чек-лист code review: что обязательно проверять, severity градация комментариев… | `quality`, `validation`, `review`, `github`, `workflow` |
| `code-simplifier` | Упрощение свеженаписанного кода без изменения поведения: мёртвый код, лишние абстракции, … | `quality`, `refactoring`, `refactor`, `ci`, `validation` |
| `mutation-testing` | Мутационное тестирование PHP через Infection: infection.json5 (source/excludes, мутаторы,… | `quality`, `testing`, `mutation`, `infection`, `php`, `ci`, `coverage` |
| `playwright-e2e` | Браузерный E2E на Playwright для веб-приложения (агностично к Vue/Inertia/Livewire): play… | `playwright`, `e2e`, `browser`, `testing`, `storage-state`, `ci`, `quality`, `frontend`, `typescript` |
| `refactoring-plan` | План безопасного рефакторинга: scope, Mikado / strangler pattern, atomic шаги, критерии г… | `quality`, `refactor`, `refactoring`, `validation`, `workflow` |
| `tech-debt-audit` | Инвентаризация техдолга, классификация (architectural/code/dependency/test/process), прио… | `quality`, `validation`, `refactor`, `dependencies`, `workflow` |
| `test-strategy` | Стратегия тестирования: пирамида (unit/integration/e2e), coverage policy, mock vs real, к… | `quality`, `testing`, `coverage`, `validation`, `ci`, `architecture`, `pest` |
| `testing-safety-report` | Отчёт безопасности после рискованного изменения (миграции, рефакторинг схемы/слоёв, апгре… | `testing`, `safety`, `migrations`, `reporting`, `verification`, `quality`, `refactor` |

### roles — Personas: tech lead, startup CTO, solo founder, open-source maintainer (4)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `open-source-maintainer` | OSS Maintainer — triage, review, releases | `role`, `persona`, `oss`, `github`, `review`, `release`, `triage` |
| `solo-founder` | Solo Founder — weekly review, decision log | `role`, `persona`, `discovery`, `market`, `validation` |
| `startup-cto` | Startup CTO persona — tech radar, hiring, architecture decisions | `role`, `persona`, `architecture`, `stack-choice`, `discipline` |
| `tech-lead` | Tech Lead persona — sprint kickoff, 1:1s, team coordination | `role`, `persona`, `orchestration`, `review`, `workflow` |

### system — Local environment topology: the three hub nodes (Brain vault, swissknifeman, projects base) and how agents navigate between projects and their docs (3)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `cross-project-coordinator` | Оркестрация межпроектного анализа кода: обойти связанные проекты (через топологию), найти… | `cross-project`, `coordination`, `refactoring`, `duplication`, `topology`, `orchestration`, `agents`, `tokens` |
| `local-topology` | Корневая карта локальной среды разработки — три узла-хаба (Brain-волт, swissknifeman, баз… | `topology`, `architecture`, `navigation`, `meta`, `cross-project` |
| `shared-memory` | Единый «мозг» (общая память) для выбранных проектов констелляции через хук ~/.claude/hook… | `memory`, `cross-project`, `topology`, `recall`, `context`, `coordination` |

## Tag matrix

Поиск скиллов по тегу (грузи точечно, не весь бакет).

| Тег | Скиллы |
|:--|:--|
| `3d` | `build-loop`, `mcp-blender`, `model-rules`, `parametric-config`, `threading`, `version-gotchas` |
| `actions` | `enum-state-machine` |
| `admin-panel` | `filament` |
| `adr` | `architecture`, `tech-stack-selection` |
| `advisory` | `livewire-blade-attributes`, `version-gotchas` |
| `agent-output` | `pao` |
| `agentic` | `agent-design`, `eval-design` |
| `agents` | `complex-task-orchestrator`, `cross-project-coordinator`, `laravel-subagents` |
| `ai` | `ai-context-workflow`, `skills-ssot` |
| `ai-act` | `legal-compliance` |
| `ai-context` | `ai-context-workflow`, `skills-ssot` |
| `alerting` | `observability-design` |
| `anti-bloat` | `package-contribution-protocol` |
| `api` | `api-design`, `dx-design`, `laravel-data`, `version-gotchas` |
| `architecture` | `agent-design`, `api-design`, `architecture`, `data-schema`, `dependency-injection`, `inertia-vue`, `laravel`, `laravel-structure`, `local-topology`, `ml-project-structure`, `modular-architecture`, `oss-development`, `php-patterns`, `pinia-stores`, `project-map`, `repositories`, `startup-cto`, `tech-stack-selection`, `test-strategy`, `ticket-workflow` |
| `attribute` | `attribute-authorization` |
| `attributes` | `enum-attributes` |
| `auth` | `security-design` |
| `authorization` | `attribute-authorization`, `azguard`, `laravel-permissions`, `ticket-workflow`, `user-roles` |
| `auto-layout` | `figma-to-flutter`, `figma-to-vue` |
| `azguard` | `azguard`, `laravel-permissions` |
| `best-practices` | `laravel-best-practices` |
| `blade` | `livewire-blade-attributes` |
| `blender` | `build-loop`, `config-conventions`, `mcp-blender`, `model-rules`, `parametric-config`, `scene-conventions`, `threading`, `version-gotchas` |
| `botkit` | `botkit` |
| `bots` | `botkit` |
| `boundary` | `package-contribution-protocol` |
| `bpy` | `build-loop`, `config-conventions`, `mcp-blender`, `parametric-config`, `scene-conventions`, `threading`, `version-gotchas` |
| `broadcasting` | `laravel-broadcasting`, `laravel-echo-client` |
| `browser` | `playwright-e2e` |
| `browser-testing` | `laravel-dusk` |
| `build` | `vite-module-loader`, `vite-multi-build` |
| `c4` | `architecture` |
| `cad` | `build-loop`, `config-conventions`, `model-rules`, `parametric-config`, `scene-conventions` |
| `camera` | `mcp-blender` |
| `casts` | `laravel-data` |
| `changelog` | `release-engineering` |
| `checklist` | `complex-task-orchestrator`, `cross-layer-change-checklist` |
| `chromedriver` | `laravel-dusk` |
| `ci` | `backend-type-sync`, `ci-cd`, `code-simplifier`, `db-test-preflight`, `mutation-testing`, `node-pnpm-preflight`, `oss-development`, `playwright-e2e`, `release-engineering`, `test-isolation-guard`, `test-strategy` |
| `claude-code` | `context-economy` |
| `clean-code` | `naming-conventions` |
| `cli` | `dx-design` |
| `code-connect` | `figma-mcp-core` |
| `code-style` | `code-style-spatie`, `eslint-flat-config`, `js-code-style`, `named-arguments`, `naming-conventions` |
| `comments` | `writing-style` |
| `commits` | `writing-style` |
| `compliance` | `dependency-audit`, `legal-compliance`, `oss-governance`, `risk-assessment`, `security-design` |
| `components` | `naive-ui-theming`, `reka-ui-cva` |
| `composable` | `dark-mode`, `vue-composition-api` |
| `compose` | `docker-dev-prod`, `docker-services` |
| `composer` | `php-upgrade-checklist` |
| `config` | `config-conventions` |
| `configuration` | `spatie-settings` |
| `context` | `anti-drift`, `compact-responses`, `context-economy`, `gh-review`, `session-handoff`, `shared-memory`, `task-brief-template` |
| `contracts` | `api-design` |
| `contribution` | `package-contribution-protocol` |
| `conventional-commits` | `git-commit-rules` |
| `conventions` | `ai-context-workflow`, `compact-responses`, `config-conventions`, `context-economy`, `git-commit-rules`, `ml-project-structure`, `model-rules`, `named-arguments`, `naming-conventions`, `packages-stack`, `project-map`, `skills-ssot`, `venv-dependencies` |
| `coordination` | `cross-project-coordinator`, `shared-memory` |
| `coverage` | `ci-cd`, `mutation-testing`, `test-strategy`, `vitest` |
| `cross-config` | `config-conventions` |
| `cross-project` | `cross-project-coordinator`, `local-topology`, `shared-memory` |
| `crud` | `filament` |
| `css` | `tailwind-conventions` |
| `cva` | `figma-to-vue`, `reka-ui-cva` |
| `dark-mode` | `dark-mode`, `figma-to-vue`, `naive-ui-theming`, `tailwind-conventions` |
| `dart` | `figma-to-flutter` |
| `data` | `data-schema`, `ml-project-structure` |
| `data-transfer-object` | `laravel-data` |
| `database` | `database`, `test-isolation-guard` |
| `dataclass` | `config-conventions`, `parametric-config` |
| `dependencies` | `dependency-audit`, `packages-stack`, `tech-debt-audit`, `venv-dependencies` |
| `deployment` | `architecture` |
| `design-system` | `figma-mcp-core`, `reka-ui-cva` |
| `design-tokens` | `figma-mcp-core`, `figma-to-flutter`, `figma-to-vue`, `naive-ui-theming`, `tailwind-conventions` |
| `dev-mode` | `figma-mcp-core` |
| `devops` | `ci-cd`, `db-test-preflight`, `docker`, `docker-dev-prod`, `docker-php`, `docker-postgres`, `docker-services`, `docker-vite`, `makefile`, `node-pnpm-preflight` |
| `di` | `dependency-injection` |
| `discipline` | `anti-drift`, `naming-conventions`, `startup-cto` |
| `discovery` | `competitive-analysis`, `customer-discovery`, `idea-discovery`, `new-project`, `solo-founder`, `spec-interview` |
| `docker` | `db-test-preflight`, `docker`, `docker-dev-prod`, `docker-php`, `docker-postgres`, `docker-services`, `docker-vite`, `laravel-dusk`, `makefile` |
| `docs` | `writing-style` |
| `documentation` | `dx-design`, `oss-development`, `oss-governance` |
| `domain` | `enum-state-machine`, `ticket-workflow` |
| `dto` | `backend-type-sync`, `laravel-data`, `php-patterns` |
| `duplication` | `cross-project-coordinator` |
| `dusk` | `laravel-dusk` |
| `dynamic-component` | `vue-dynamic-icons` |
| `e2e` | `laravel-dusk`, `playwright-e2e` |
| `echo` | `laravel-broadcasting` |
| `entities` | `data-schema` |
| `enum` | `attribute-authorization`, `azguard`, `backend-type-sync`, `enum-attributes`, `enum-state-machine`, `user-roles` |
| `erd` | `data-schema` |
| `eslint` | `eslint-flat-config`, `wayfinder` |
| `fdm` | `build-loop`, `config-conventions`, `parametric-config`, `threading` |
| `feature-flags` | `pennant-development` |
| `figma` | `figma-mcp-core`, `figma-to-flutter`, `figma-to-vue` |
| `filament` | `filament`, `modular-architecture`, `spatie-settings`, `vite-multi-build` |
| `file-upload` | `filepond-upload` |
| `filepond` | `filepond-upload` |
| `flat-config` | `eslint-flat-config` |
| `flutter` | `figma-to-flutter` |
| `forms` | `filepond-upload` |
| `frontend` | `backend-type-sync`, `docker-vite`, `eslint-flat-config`, `filepond-upload`, `inertia-vue`, `laravel-echo-client`, `livewire-blade-attributes`, `naive-ui-theming`, `pinia-stores`, `playwright-e2e`, `reka-ui-cva`, `vite-module-loader`, `vite-multi-build`, `vitest`, `vue-composition-api`, `vue-dynamic-icons`, `wayfinder` |
| `gate` | `attribute-authorization`, `azguard` |
| `gdpr` | `legal-compliance`, `security-design` |
| `geometry` | `parametric-config`, `threading` |
| `gh` | `gh-review` |
| `git` | `git-commit-rules`, `github-flow`, `gitops` |
| `github` | `code-review`, `gh-review`, `github-flow`, `gitops`, `open-source-maintainer` |
| `github-actions` | `ci-cd` |
| `gitlab-ci` | `ci-cd` |
| `gitops` | `git-commit-rules`, `gitops` |
| `gotchas` | `livewire-blade-attributes`, `version-gotchas` |
| `governance` | `package-contribution-protocol` |
| `gtm` | `competitive-analysis`, `go-to-market`, `new-project`, `pitch-deck`, `product-roadmap` |
| `handoff` | `gh-review`, `oncall-rotation`, `session-handoff` |
| `headless` | `reka-ui-cva` |
| `health` | `health-checks` |
| `icons` | `vue-dynamic-icons` |
| `image-preview` | `filepond-upload` |
| `images` | `medialibrary` |
| `incident` | `incident-response`, `oncall-rotation`, `postmortem`, `runbook` |
| `inertia` | `filepond-upload`, `inertia-vue`, `laravel-data`, `wayfinder` |
| `infection` | `mutation-testing` |
| `isolation` | `db-test-preflight`, `test-isolation-guard` |
| `javascript` | `js-code-style` |
| `jsdom` | `vitest` |
| `language` | `writing-style` |
| `laravel` | `ai-context-workflow`, `attribute-authorization`, `azguard`, `backend-type-sync`, `botkit`, `ci-cd`, `code-style-spatie`, `database`, `dependency-injection`, `docker-dev-prod`, `docker-php`, `docker-services`, `docker-vite`, `enum-attributes`, `enum-state-machine`, `filament`, `filepond-upload`, `health-checks`, `inertia-vue`, `laravel`, `laravel-best-practices`, `laravel-broadcasting`, `laravel-data`, `laravel-dusk`, `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages`, `laravel-permissions`, `laravel-security-audit`, `laravel-structure`, `laravel-subagents`, `laravel-testing`, `livewire-blade-attributes`, `medialibrary`, `modular-architecture`, `naming-conventions`, `packages-stack`, `pao`, `pennant-development`, `php-patterns`, `project-map`, `repositories`, `spatie-settings`, `static-analysis`, `tailwind-conventions`, `test-isolation-guard`, `ticket-workflow`, `user-roles`, `vite-module-loader`, `vite-multi-build`, `vitest`, `wayfinder` |
| `laravel-data` | `laravel-data` |
| `laravel-echo` | `laravel-echo-client` |
| `laravel-modules` | `modular-architecture` |
| `license` | `oss-governance` |
| `liveness` | `health-checks` |
| `livewire` | `filament`, `livewire-blade-attributes` |
| `llm` | `eval-design` |
| `localstorage` | `dark-mode` |
| `logging` | `observability-design` |
| `lucide` | `vue-dynamic-icons` |
| `make` | `makefile` |
| `market` | `adversarial-check`, `competitive-analysis`, `customer-discovery`, `defensibility`, `go-to-market`, `idea-discovery`, `monetization-design`, `new-project`, `pitch-deck`, `pmf-diagnostics`, `product-roadmap`, `solo-founder`, `startup-lifecycle` |
| `matchmedia` | `dark-mode` |
| `materials` | `scene-conventions` |
| `mcp` | `build-loop`, `figma-mcp-core`, `mcp-blender` |
| `media` | `medialibrary` |
| `memory` | `shared-memory` |
| `meta` | `local-topology` |
| `metrics` | `eval-design`, `observability-design` |
| `middleware` | `attribute-authorization` |
| `migrations` | `database`, `testing-safety-report` |
| `ml` | `ml-project-structure` |
| `mobile` | `figma-to-flutter` |
| `monetization` | `go-to-market`, `monetization-design`, `pitch-deck`, `unit-economics` |
| `monitoring` | `capacity-planning`, `health-checks`, `runbook` |
| `monorepo` | `package-contribution-protocol` |
| `multi-config` | `vite-multi-build` |
| `mutation` | `mutation-testing` |
| `naive-ui` | `naive-ui-theming` |
| `naming` | `naming-conventions`, `scene-conventions` |
| `navigation` | `local-topology`, `packages-stack`, `project-map` |
| `node` | `node-pnpm-preflight` |
| `nwidart` | `modular-architecture` |
| `observability` | `capacity-planning`, `health-checks`, `observability-design` |
| `ops` | `capacity-planning`, `incident-response`, `oncall-rotation`, `postmortem`, `runbook` |
| `orchestration` | `anti-drift`, `complex-task-orchestrator`, `cross-project-coordinator`, `laravel-subagents`, `mcp-blender`, `tech-lead` |
| `oss` | `dependency-audit`, `dx-design`, `github-flow`, `open-source-maintainer`, `oss-development`, `oss-governance`, `release-engineering` |
| `owasp` | `security-design` |
| `package` | `package-contribution-protocol` |
| `package-dev` | `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages` |
| `parametric` | `build-loop`, `config-conventions`, `parametric-config`, `scene-conventions` |
| `parenting` | `scene-conventions` |
| `patterns` | `enum-attributes`, `laravel`, `php-patterns`, `vue-composition-api` |
| `pennant` | `pennant-development` |
| `permissions` | `attribute-authorization`, `azguard`, `laravel-permissions`, `user-roles` |
| `persona` | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| `pest` | `test-strategy` |
| `php` | `attribute-authorization`, `azguard`, `botkit`, `code-style-spatie`, `database`, `dependency-audit`, `dependency-injection`, `docker-php`, `enum-attributes`, `enum-state-machine`, `filament`, `laravel`, `laravel-best-practices`, `laravel-broadcasting`, `laravel-data`, `laravel-dusk`, `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages`, `laravel-permissions`, `laravel-security-audit`, `laravel-structure`, `laravel-testing`, `medialibrary`, `modular-architecture`, `mutation-testing`, `named-arguments`, `naming-conventions`, `pao`, `pennant-development`, `php-patterns`, `php-upgrade-checklist`, `repositories`, `spatie-settings`, `static-analysis`, `test-isolation-guard`, `user-roles` |
| `phpstan` | `php-upgrade-checklist` |
| `pinia` | `pinia-stores` |
| `playwright` | `playwright-e2e` |
| `pnpm` | `node-pnpm-preflight` |
| `postgres` | `db-test-preflight`, `docker-postgres` |
| `preflight` | `db-test-preflight`, `node-pnpm-preflight` |
| `prettier` | `eslint-flat-config`, `js-code-style`, `tailwind-conventions` |
| `privacy` | `legal-compliance`, `security-design` |
| `pusher` | `laravel-echo-client` |
| `python` | `mcp-blender`, `ml-project-structure`, `parametric-config`, `venv-dependencies`, `version-gotchas` |
| `quality` | `code-review`, `code-simplifier`, `mutation-testing`, `playwright-e2e`, `refactoring-plan`, `static-analysis`, `tech-debt-audit`, `test-strategy`, `testing-safety-report`, `venv-dependencies` |
| `queue` | `docker-services` |
| `rbac` | `attribute-authorization`, `azguard`, `laravel-permissions`, `security-design` |
| `readability` | `named-arguments`, `naming-conventions` |
| `readiness` | `health-checks` |
| `realtime` | `laravel-broadcasting`, `laravel-echo-client` |
| `recall` | `shared-memory` |
| `rector` | `php-upgrade-checklist` |
| `refactor` | `code-simplifier`, `refactoring-plan`, `tech-debt-audit`, `testing-safety-report` |
| `refactoring` | `code-simplifier`, `cross-project-coordinator`, `refactoring-plan` |
| `reflection` | `attribute-authorization`, `enum-attributes`, `postmortem`, `user-roles` |
| `refreshdatabase` | `test-isolation-guard` |
| `regulatory` | `legal-compliance` |
| `reka-ui` | `reka-ui-cva` |
| `release` | `ci-cd`, `github-flow`, `open-source-maintainer`, `release-engineering` |
| `reporting` | `testing-safety-report` |
| `repository` | `repositories`, `ticket-workflow` |
| `requirements` | `brd`, `business-process`, `idea-discovery`, `new-project`, `prd-from-brd`, `product-roadmap`, `requirement-critic`, `spec-interview`, `startup-lifecycle`, `task-brief-template` |
| `rest` | `api-design` |
| `reverb` | `laravel-broadcasting`, `laravel-echo-client` |
| `review` | `code-review`, `gh-review`, `open-source-maintainer`, `tech-lead` |
| `role` | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| `roles` | `user-roles` |
| `routes` | `wayfinder` |
| `rules` | `model-rules` |
| `runbook` | `observability-design` |
| `russian` | `writing-style` |
| `safety` | `test-isolation-guard`, `testing-safety-report` |
| `scalability` | `architecture` |
| `scene` | `scene-conventions` |
| `schema` | `data-schema` |
| `screenshot` | `mcp-blender` |
| `security` | `agent-design`, `ci-cd`, `dependency-audit`, `laravel-security-audit`, `oss-governance`, `risk-assessment`, `security-design` |
| `semver` | `github-flow`, `package-contribution-protocol`, `release-engineering` |
| `settings` | `spatie-settings` |
| `skills` | `ai-context-workflow`, `laravel-packages`, `skills-ssot` |
| `sla` | `build-loop`, `capacity-planning`, `config-conventions`, `incident-response`, `oncall-rotation`, `parametric-config`, `threading` |
| `slo` | `observability-design` |
| `spatie` | `backend-type-sync`, `code-style-spatie`, `health-checks`, `js-code-style`, `laravel-data`, `medialibrary`, `spatie-settings` |
| `ssot` | `skills-ssot` |
| `ssr` | `dark-mode` |
| `stack-choice` | `startup-cto`, `tech-stack-selection` |
| `state-machine` | `enum-state-machine` |
| `state-management` | `pinia-stores` |
| `storage-state` | `playwright-e2e` |
| `store` | `pinia-stores` |
| `stride` | `security-design` |
| `structure` | `inertia-vue`, `laravel-structure`, `ml-project-structure`, `project-map` |
| `style` | `compact-responses`, `writing-style` |
| `stylistic` | `eslint-flat-config` |
| `tailwind` | `dark-mode`, `figma-to-vue`, `naive-ui-theming`, `reka-ui-cva`, `tailwind-conventions`, `vite-multi-build` |
| `tailwindcss-v4` | `figma-to-vue`, `tailwind-conventions` |
| `template` | `brd`, `model-rules`, `prd-from-brd`, `runbook`, `task-brief-template` |
| `testing` | `db-test-preflight`, `docker-postgres`, `eval-design`, `laravel-testing`, `mutation-testing`, `pao`, `playwright-e2e`, `test-isolation-guard`, `test-strategy`, `testing-safety-report`, `vitest` |
| `tests` | `writing-style` |
| `theme` | `dark-mode` |
| `theming` | `figma-to-flutter`, `naive-ui-theming` |
| `threading` | `threading` |
| `threat-modeling` | `security-design` |
| `tokens` | `compact-responses`, `context-economy`, `cross-project-coordinator`, `gh-review`, `pao`, `session-handoff` |
| `tooling` | `eslint-flat-config`, `venv-dependencies` |
| `topology` | `cross-project-coordinator`, `local-topology`, `shared-memory` |
| `tracing` | `observability-design` |
| `trade-off` | `tech-stack-selection` |
| `transitions` | `enum-state-machine` |
| `triage` | `open-source-maintainer` |
| `type-sync` | `backend-type-sync` |
| `types` | `backend-type-sync` |
| `typescript` | `backend-type-sync`, `enum-attributes`, `eslint-flat-config`, `js-code-style`, `playwright-e2e`, `vue-dynamic-icons`, `wayfinder` |
| `ui` | `figma-mcp-core`, `filament`, `naive-ui-theming`, `reka-ui-cva` |
| `units` | `parametric-config` |
| `upgrade` | `php-upgrade-checklist` |
| `uploads` | `filepond-upload`, `medialibrary` |
| `validation` | `adversarial-check`, `agent-design`, `code-review`, `code-simplifier`, `cross-layer-change-checklist`, `customer-discovery`, `defensibility`, `eval-design`, `laravel-data`, `pmf-diagnostics`, `refactoring-plan`, `requirement-critic`, `risk-assessment`, `solo-founder`, `startup-lifecycle`, `tech-debt-audit`, `test-strategy` |
| `variants` | `reka-ui-cva` |
| `venv` | `venv-dependencies` |
| `verification` | `testing-safety-report` |
| `version` | `php-upgrade-checklist`, `version-gotchas` |
| `viewport` | `mcp-blender` |
| `vite` | `docker-vite`, `vite-module-loader`, `vite-multi-build` |
| `vitest` | `vitest` |
| `vue` | `dark-mode`, `eslint-flat-config`, `figma-to-vue`, `filepond-upload`, `inertia-vue`, `js-code-style`, `laravel-echo-client`, `naive-ui-theming`, `packages-stack`, `pinia-stores`, `reka-ui-cva`, `tailwind-conventions`, `vite-module-loader`, `vitest`, `vue-composition-api`, `vue-dynamic-icons` |
| `wayfinder` | `wayfinder` |
| `websocket` | `docker-services` |
| `websockets` | `laravel-broadcasting`, `laravel-echo-client` |
| `workflow` | `ai-context-workflow`, `anti-drift`, `build-loop`, `business-process`, `code-review`, `compact-responses`, `complex-task-orchestrator`, `context-economy`, `cross-layer-change-checklist`, `enum-state-machine`, `incident-response`, `laravel-subagents`, `postmortem`, `refactoring-plan`, `session-handoff`, `skills-ssot`, `spec-interview`, `task-brief-template`, `tech-debt-audit`, `tech-lead`, `ticket-workflow` |
| `writing` | `writing-style` |
