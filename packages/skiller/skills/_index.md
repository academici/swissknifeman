# Реестр скиллов swissknifeman

<!-- GENERATED `skiller registry` — не редактировать вручную -->

Источник истины портируемых скиллов (машинный реестр — `skills.json`). Раздача в проекты: `skiller connect` (плагины-бакеты) / `vendor` (физ. перенос). CORE-набор токен-скиллов (`general`/`oss-dev`) раздаётся по умолчанию — см. `connect`/`vendor`.

Всего: 195 скиллов в 45 бакетах.

## Скиллы по бакетам

### ai — AI agent building: design, tools, evaluation (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `ai-agents` | Навигатор по справочнику построения AI-агентов (vendored super-skill get-zeked): паттерны… | `ai`, `agents`, `mcp`, `rag`, `orchestration`, `prompt-engineering`, `subagents` |

### architect — Architecture, API and data design, security, observability, tech stack selection (14)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `agent-design` | Agent design, agentic loop, tool contracts, harness, permission gates | `agentic`, `architecture`, `security`, `validation` |
| `api-design` | Designing REST/GraphQL APIs, endpoints, contracts, versioning, authentication | `api`, `architecture`, `rest`, `contracts` |
| `architecture` | System architecture, stack choice, ADR, C4 diagrams, deployment, scalability | `architecture`, `adr`, `c4`, `scalability`, `deployment` |
| `codebase-design` | Общий словарь и дисциплина проектирования ГЛУБОКИХ модулей (Ousterhout/Feathers): Module/… | `design`, `deep-modules`, `ousterhout`, `seam`, `testability` |
| `data-schema` | Data schema, entities, attributes, relations. DB-agnostic — markdown tables only | `data`, `architecture`, `schema`, `entities`, `erd` |
| `dev-engineering-super-skill` | Comprehensive full-stack development and engineering skill merging Perplexity Computer's … |  |
| `domain-modeling` | Активная дисциплина доменной модели: бросать вызов терминам, стресс-тестировать сценариям… | `domain`, `ddd`, `glossary`, `adr`, `ubiquitous-language` |
| `eval-design` | Evaluate LLM/AI output quality — eval-set, metrics, regression harness, automated + human… | `agentic`, `validation`, `llm`, `metrics`, `testing` |
| `figma-mcp-core` | Discipline for the official Figma Dev Mode MCP: real tools (get_metadata, get_variable_de… | `figma`, `mcp`, `design-system`, `design-tokens`, `dev-mode`, `code-connect`, `ui` |
| `legal-compliance` | GDPR, CCPA, AI Act, DMCA, COPPA, DSA — pre-launch regulatory checklist | `compliance`, `gdpr`, `privacy`, `ai-act`, `regulatory` |
| `observability-design` | Logging, metrics, tracing, alerting. SLO/SLI, error budget, runbooks for prod-readiness | `observability`, `logging`, `metrics`, `tracing`, `alerting`, `slo`, `runbook` |
| `package-contribution-protocol` | Gate against bloating a depended-on package from a consumer project: Rule of Three, propo… | `governance`, `package`, `monorepo`, `contribution`, `semver`, `anti-bloat`, `boundary` |
| `security-design` | Data classification, auth strategy, RBAC/ABAC, OWASP Top 10, GDPR, STRIDE threat modeling… | `security`, `compliance`, `auth`, `owasp`, `threat-modeling`, `rbac`, `gdpr`, `privacy`, `stride` |
| `tech-stack-selection` | Tech stack selection with trade-off matrix before architecture design. ADR-first step | `stack-choice`, `architecture`, `adr`, `trade-off` |

### azguard — azguard package usage: code-first RBAC, panels, scoped roles, abilities (academici package — skill will relocate into the package repo) (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `azguard` | Roles & access control via azguard package: code-first RBAC, panels, scoped roles, direct… | `php`, `laravel`, `permissions`, `azguard`, `rbac`, `authorization`, `gate`, `enum` |

### blender — Universal Blender bpy+MCP tooling: MCP workflow primitives, viewport modes, camera helper, version gotchas (2)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `mcp-blender` | MCP Blender: tools (execute_blender_code, get_object_info, get_viewport_screenshot, get_s… | `blender`, `mcp`, `python`, `3d`, `bpy`, `viewport`, `camera`, `screenshot`, `orchestration` |
| `version-gotchas` | Known breaking changes and pitfalls of the Blender 5.0 API | `blender`, `api`, `bpy`, `3d`, `python`, `gotchas`, `advisory`, `version` |

### blender-modeling — Parametric CAD modeling in Blender for FDM/SLA: config-driven dataclasses, profile/revolve geometry, threading clearances, config & scene conventions, model-rules template, generic build loop (6)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `build-loop` | Parametric-modeling build loop via MCP Blender: analyze task → check flexibility/cross-co… | `blender`, `cad`, `parametric`, `workflow`, `bpy`, `mcp`, `3d`, `fdm`, `sla` |
| `config-conventions` | Parametric CAD config conventions: one entity = one dataclass; variable naming (r_outer/z… | `blender`, `cad`, `parametric`, `dataclass`, `config`, `cross-config`, `conventions`, `bpy`, `fdm`, `sla` |
| `model-rules` | Template models/{name}/ai/rules.md — model-specific rules read by the agent before any ta… | `blender`, `template`, `rules`, `3d`, `cad`, `conventions` |
| `parametric-config` | Data-config-driven parametric 3D modeling in Blender (bpy): dataclass part params (dims/t… | `blender`, `bpy`, `parametric`, `dataclass`, `cad`, `fdm`, `sla`, `geometry`, `units`, `python`, `3d` |
| `scene-conventions` | Parametric-model scene conventions: object prefixes (MESH_/CRV_/LGT_/MTL_), parenting hie… | `blender`, `cad`, `parametric`, `naming`, `scene`, `materials`, `parenting`, `bpy` |
| `threading` | Threads on FDM/SLA parts: material, print physics, radial clearance by fit type | `blender`, `3d`, `fdm`, `sla`, `threading`, `geometry`, `bpy` |

### botkit — botkit package usage: bot framework patterns — BotDefinition, service provider, webhooks (academici package — skill will relocate into the package repo) (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `botkit` | Bot framework patterns: BotDefinition contract, package service provider, webhook handling | `php`, `laravel`, `bots`, `botkit` |

### creative — Creative studio: video, design, content production (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `content-creative-super-skill` | Comprehensive creative studio skill merging Perplexity Computer's video production, speec… |  |

### devops — Docker environments, CI/CD pipelines, GitOps (11)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `ci-cd` | GitHub Actions / GitLab CI pipelines for Laravel: lint, tests, build, release + security … | `ci`, `github-actions`, `gitlab-ci`, `laravel`, `devops`, `release`, `security`, `coverage` |
| `db-test-preflight` | Pre-flight check of test DB (Postgres in Docker) BEFORE running tests: container up (dock… | `postgres`, `docker`, `testing`, `preflight`, `devops`, `ci`, `isolation` |
| `docker` | Advanced Docker containerization expertise: container optimization, security hardening, m… | `docker`, `devops` |
| `docker-dev-prod` | Split docker-compose into dev (build + bind-mount) and prod (prebuilt image + named volum… | `docker`, `devops`, `compose`, `laravel` |
| `docker-php` | Production PHP Docker image: alpine-fpm or all-in-one serversideup/php (FPM+Nginx), entry… | `docker`, `php`, `devops`, `laravel` |
| `docker-postgres` | PostgreSQL in Docker: pg_isready healthcheck, named volume for data, init script creating… | `docker`, `devops`, `postgres`, `testing` |
| `docker-services` | Full Laravel service stack from one image: app (fpm-nginx), queue, scheduler, reverb, opt… | `docker`, `devops`, `compose`, `laravel`, `queue`, `websocket` |
| `docker-vite` | Vite dev server as separate compose service for Laravel: named volume for node_modules, H… | `docker`, `devops`, `vite`, `frontend`, `laravel` |
| `gitops` | Team Git strategy: branch model (main/develop/feature/hotfix), PR workflow, branch protec… | `git`, `gitops`, `github` |
| `makefile` | Makefile as single entrypoint: help, .PHONY, Docker command aliases; delegating root Make… | `make`, `devops`, `docker` |
| `node-pnpm-preflight` | Check Node/pnpm availability on host before commands and git hooks that use pnpm (commitl… | `node`, `pnpm`, `devops`, `preflight`, `ci` |

### finance — Finance and accounting: bookkeeping, reporting, FP&A (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `finance-super-skill` | Comprehensive finance and accounting skill merging Perplexity Computer's 7 finance skills… |  |

### founder — Idea discovery, competitive analysis, risk assessment, pitch decks (9)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `adversarial-check` | Structured devil's advocate — 3 strongest counterarguments, failed competitors, negative … | `validation`, `market` |
| `competitive-analysis` | Market, competitors, JTBD, open niche, attack vector. Uses Perplexity search_deep | `discovery`, `market`, `gtm` |
| `customer-discovery` | Systematic discovery — target profile, interview framework (past not future), post-interv… | `discovery`, `validation`, `market` |
| `defensibility` | Moat analysis for Scale stage — accumulated depth, data flywheel, workflow lock-in, domai… | `market`, `validation` |
| `idea-discovery` | Structured interview of a raw idea — JTBD, problem statement, hypothesis, before competit… | `discovery`, `requirements`, `market` |
| `new-project` | Launch a new startup project: concept, competitors, risks, full folder structure | `discovery`, `requirements`, `market`, `gtm` |
| `pitch-deck` | 10-slide investor deck per YC/Sequoia canon from existing project artifacts | `gtm`, `market`, `monetization` |
| `risk-assessment` | 5 risk categories, Risk Matrix, RAID log, pre-mortem for critical risks | `validation`, `compliance`, `security` |
| `startup-lifecycle` | 4 AI-native startup stages (Idea→MVP→Launch→Scale) with exit-criteria, failure modes, ant… | `validation`, `requirements`, `market` |

### frontend — Frontend core: общие фронт-скиллы (web design guidelines, document writer, file upload) (3)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `document-writer` | Use when writing blog posts or documentation markdown files - provides writing style guid… |  |
| `filepond-upload` | File upload via FilePond in Vue + Laravel: register vue-filepond + plugins (validate-type… | `filepond`, `vue`, `laravel`, `file-upload`, `frontend`, `forms`, `image-preview`, `inertia`, `uploads` |
| `web-design-guidelines` | Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI",… |  |

### frontend-animations — Animations with Motion Vue (motion-v) (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `motion` | Use when adding animations with Motion Vue (motion-v) - provides motion component API, ge… |  |

### frontend-backend — Backend integration layer: Inertia+Vue, Laravel Echo realtime client, backend→frontend type sync (3)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `backend-type-sync` | Backend→frontend type sync via spatie/laravel-typescript-transformer: #[TypeScript] on en… | `typescript`, `laravel`, `spatie`, `types`, `enum`, `dto`, `frontend`, `type-sync`, `ci` |
| `inertia-vue` | Inertia + Vue in Laravel: pages, forms, navigation and layered resources/js organization … | `inertia`, `vue`, `laravel`, `frontend`, `architecture`, `structure` |
| `laravel-echo-client` | Frontend realtime client Laravel Echo (Reverb/Pusher) in Vue 3: configure Echo from runti… | `laravel-echo`, `reverb`, `pusher`, `websockets`, `realtime`, `vue`, `broadcasting`, `frontend` |

### frontend-figma — Figma Dev Mode MCP → Vue mapping (uses architect/figma-mcp-core) (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `figma-to-vue` | Map Figma Dev Mode MCP design to Vue + Tailwind v4: Auto-layout → flexbox/grid, tokens.js… | `figma`, `vue`, `tailwind`, `tailwindcss-v4`, `cva`, `design-tokens`, `dark-mode`, `auto-layout` |

### frontend-linting — JS/TS tooling and style: antfu config, ESLint flat config, Spatie JS style, TS library authoring (4)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `antfu` | Anthony Fu's opinionated tooling and conventions for JavaScript/TypeScript projects. Use … |  |
| `eslint-flat-config` | ESLint flat config (eslint.config.js) for Vue 3 + TypeScript: defineConfigWithVueTs/types… | `eslint`, `prettier`, `flat-config`, `vue`, `typescript`, `stylistic`, `tooling`, `code-style`, `frontend` |
| `js-code-style` | Стиль JS/TS по Spatie: 4 пробела, ширина 120, одинарные кавычки, const-first, строгое ===… | `javascript`, `typescript`, `code-style`, `spatie`, `prettier`, `vue` |
| `ts-library` | Use when authoring TypeScript libraries or npm packages - covers project setup, package.j… |  |

### frontend-naive-ui — Naive UI component library theming (GlobalThemeOverrides) (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `naive-ui-theming` | Naive UI global theme: GlobalThemeOverrides (common + Button/Card/Form/Input/Tag/Tabs…), … | `naive-ui`, `vue`, `theming`, `design-tokens`, `dark-mode`, `tailwind`, `frontend`, `components`, `ui` |

### frontend-nuxt — Nuxt 4+: server routes, modules, SEO meta-module (3)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `nuxt` | Use when working on Nuxt 4+ projects - provides server routes, file-based routing, middle… |  |
| `nuxt-modules` | Use when creating Nuxt modules: (1) Published npm modules (@nuxtjs/, nuxt-), (2) Local pr… |  |
| `nuxt-seo` | Nuxt SEO meta-module with robots, sitemap, og-image, schema-org. Use when configuring SEO… |  |

### frontend-reka — Reka UI headless primitives + CVA variants (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `reka-ui-cva` | UI component library on Reka UI headless primitives + class-variance-authority (cva) vari… | `reka-ui`, `cva`, `vue`, `tailwind`, `headless`, `components`, `variants`, `design-system`, `ui`, `frontend` |

### frontend-tailwind — Tailwind CSS v4 conventions and dark-mode theming (2)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `dark-mode` | Dark theme light\|dark\|system on Vue 3: useDarkMode composable (matchMedia prefers-color… | `dark-mode`, `theme`, `vue`, `composable`, `ssr`, `tailwind`, `matchmedia`, `localstorage` |
| `tailwind-conventions` | Tailwind CSS v4 conventions for Laravel/Vue: CSS-first config (@import tailwindcss, @them… | `tailwind`, `tailwindcss-v4`, `css`, `vue`, `laravel`, `dark-mode`, `design-tokens`, `prettier` |

### frontend-vite — Vite build tooling: config/plugins/SSR, project module loader, multi-build, VitePress (4)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `vite` | Vite build tool configuration, plugin API, SSR, and Vite 8 Rolldown migration. Use when w… |  |
| `vite-module-loader` | Vite as primary frontend bundler: base config, aliases, build practices | `vite`, `frontend`, `build`, `laravel`, `vue` |
| `vite-multi-build` | Two independent Vite builds in one Laravel project: main app + Filament admin, with separ… | `vite`, `laravel`, `filament`, `tailwind`, `build`, `multi-config`, `frontend` |
| `vitepress` | VitePress static site generator powered by Vite and Vue. Use when building documentation … |  |

### frontend-vue — Vue 3 ecosystem: Composition API, best practices, router, VueUse, Pinia state, Vitest testing (11)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `pinia` | Pinia official Vue state management library, type-safe and extensible. Use when defining … |  |
| `pinia-stores` | Pinia (Vue 3) global state: setup stores (defineStore with function), ref=state/computed=… | `pinia`, `vue`, `frontend`, `state-management`, `store`, `architecture` |
| `vitest` | Vitest for Vue/Inertia-on-Laravel: jsdom, globals, tests in resources/js/tests mirror sou… | `vitest`, `testing`, `vue`, `coverage`, `jsdom`, `laravel`, `frontend` |
| `vitest-vue` | Vitest fast unit testing framework powered by Vite with Jest-compatible API. Use when wri… |  |
| `vue` | Vue 3 Composition API, script setup macros, reactivity system, and built-in components. U… |  |
| `vue-best-practices` | MUST be used for Vue.js tasks. Strongly recommends Composition API with `<script setup>` … |  |
| `vue-composition-api` | Project Composition API conventions: ref-first and composables pattern. NOT an API refere… | `vue`, `frontend`, `composable`, `patterns` |
| `vue-dynamic-icons` | Vue: one icon component rendering SVG by string name from a set (lucide-vue-next etc.) vi… | `vue`, `icons`, `dynamic-component`, `lucide`, `typescript`, `frontend` |
| `vue-router-best-practices` | Vue Router 4 — маршрутизация и навигация: typed/именованные routes, lazy-loading view-ком… | `vue`, `vue-router`, `frontend`, `routing`, `navigation-guards`, `lazy-loading`, `typescript` |
| `vue-testing-best-practices` | Практики тестирования Vue 3-компонентов через Vitest + Vue Test Utils 2: mount vs shallow… | `vue`, `testing`, `vitest`, `vue-test-utils`, `pinia`, `composables`, `frontend` |
| `vueuse-functions` | Apply VueUse composables where appropriate to build concise, maintainable Vue.js / Nuxt f… |  |

### frontend-wayfinder — Laravel Wayfinder: type-safe routes/controller actions in the frontend (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `wayfinder` | Laravel Wayfinder: typesafe routes and controller actions for the frontend. Generation, n… | `wayfinder`, `laravel`, `typescript`, `routes`, `inertia`, `eslint`, `frontend` |

### general — General agent workflow conventions: git commits, task briefs, project maps, cross-layer checklists (20)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `anti-drift` | Discipline against agent rabbit-holing: think before coding, simplicity first, surgical e… | `workflow`, `discipline`, `orchestration`, `context` |
| `compact-responses` | Activate ultra-compact response mode: minimal prose, code-only, no explanations unless as… | `conventions`, `style`, `tokens`, `context`, `workflow` |
| `complex-task-orchestrator` | Complex-task orchestration: decomposition, context routing, risk management, Definition o… | `workflow`, `orchestration`, `checklist`, `agents` |
| `context-economy` | Claude Code context economy in a project: CLAUDE.md ≤200 lines, path-scoped .claude/rules… | `tokens`, `context`, `claude-code`, `workflow`, `conventions` |
| `cross-layer-change-checklist` | Universal checklist for changes spanning multiple layers: code, authorization, UI, docs, … | `checklist`, `workflow`, `validation` |
| `git-commit-rules` | Git workflow: commit prep, husky/commitlint, message format, safe action order. | `git`, `conventions`, `conventional-commits`, `gitops` |
| `git-safety` | Защита от деструктивных git-команд через PreToolUse-хук Claude Code: блокирует push/reset… | `git`, `safety`, `hooks`, `guardrails`, `init` |
| `grill-with-docs` | Безжалостная грилинг-сессия, которая ОДНОВРЕМЕННО строит доменную модель: уточняет план/д… | `grilling`, `requirements`, `domain`, `adr`, `docs` |
| `implement` | Реализация куска работы по ТЗ/PRD/issue минимальной цепочкой: tdd-discipline на согласова… | `workflow`, `implementation`, `tdd`, `review` |
| `mcp-advisor` | Pick MCP servers for a project at onboarding/sync: which to connect (context7/playwright/… | `mcp`, `onboarding`, `tooling`, `context`, `claude-code` |
| `naming-conventions` | Naming discipline (language-agnostic): name reveals intent, not implementation; fight noi… | `naming`, `conventions`, `readability`, `code-style`, `discipline`, `clean-code` |
| `packages-stack` | Project external-dependency registry methodology: which packages are used and for what, a… | `dependencies`, `conventions`, `navigation`, `stack`, `init` |
| `project-map` | Project structure map methodology: zone directories by responsibility for safe change rou… | `conventions`, `navigation`, `architecture`, `structure`, `routing` |
| `session-handoff` | Cross-session/agent context handoff: compress a session into a structured doc — state, de… | `workflow`, `context`, `tokens`, `handoff` |
| `skills-ssot` | Single source of truth for skills across multiple AI agents: .ai/skills + symlinks, gitig… | `ai-context`, `skills`, `ssot`, `workflow`, `conventions`, `ai` |
| `spec-interview` | Pre-code interview: agent asks one question at a time, reads the codebase itself where it… | `workflow`, `requirements`, `discovery` |
| `task-brief-template` | Brief template for complex agent tasks: goal, scope, invariants, explicit assumptions, ou… | `workflow`, `template`, `requirements`, `context` |
| `token-efficient` | Reduces Perplexity Computer output verbosity and token waste. Eliminates sycophantic open… |  |
| `verify-claims` | Before a decision/verdict that rests on an EXTERNAL fact (library version/API, 'still cur… | `verification`, `rag`, `research`, `planning`, `context`, `claude-code` |
| `writing-style` | Tone & language of code artifacts: Russian by default for comments, commit bodies, test d… | `writing`, `language`, `russian`, `comments`, `commits`, `tests`, `docs`, `style` |

### laravel-architecture — Scaling architecture: modular monolith/DDD, enum state machines, enum attributes, subagent orchestration (4)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `enum-attributes` | Use for enum metadata: replace label()/color()/description() match-ladders with PHP attri… | `php`, `enum`, `attributes`, `reflection`, `laravel`, `patterns`, `typescript` |
| `enum-state-machine` | Activate when a domain status (Order/Document/Subscription) grows into a transition graph… | `php`, `enum`, `state-machine`, `workflow`, `laravel`, `transitions`, `domain`, `actions` |
| `laravel-subagents` | Subagent orchestration on large Laravel tasks: activation threshold, delegating research … | `workflow`, `orchestration`, `agents`, `laravel` |
| `modular-architecture` | Scale Laravel code as it grows: organize by business domain, Modular Monolith and DDD pat… | `php`, `laravel`, `architecture`, `nwidart`, `laravel-modules`, `filament` |

### laravel-auth — Authorization & security: permissions/RBAC, attribute-based gates, security audit (3)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `attribute-authorization` | Declarative method-level authorization via #[CheckPermission] attribute (enum permission … | `php`, `laravel`, `authorization`, `attribute`, `reflection`, `middleware`, `gate`, `enum`, `permissions`, `rbac` |
| `laravel-permissions` | Manual/native Laravel RBAC: policies, gates, entity-scoped permissions without a dedicate… | `php`, `laravel`, `permissions`, `azguard`, `rbac`, `authorization` |
| `laravel-security-audit` | Audit Laravel code for sharp edges: raw Eloquent queries, mass assignment, Blade XSS, CSR… | `php`, `laravel`, `security` |

### laravel-data-layer — Typed data + realtime: spatie/laravel-data DTOs (TS export), Echo/Reverb broadcasting (2)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `laravel-broadcasting` | Laravel Echo + Reverb/Pusher/Ably: broadcast-события, авторизация каналов, presence/whisp… | `php`, `laravel`, `broadcasting`, `echo`, `reverb`, `websockets`, `realtime` |
| `laravel-data` | DTOs with spatie/laravel-data: typed Data classes, nested DataCollection, casts/transform… | `php`, `laravel`, `spatie`, `laravel-data`, `dto`, `data-transfer-object`, `casts`, `validation`, `inertia`, `api` |

### laravel-extras — Optional Laravel runtime packages: media library, typed settings, Pennant feature flags (3)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `medialibrary` | spatie/laravel-medialibrary: attach files to Eloquent models, collections, conversions, g… | `php`, `laravel`, `media`, `spatie`, `uploads`, `images` |
| `pennant-development` | Laravel Pennant — feature-флаги: define/active/for-scope, директива @feature, активация/д… | `php`, `laravel`, `pennant`, `feature-flags` |
| `spatie-settings` | spatie/laravel-settings: typed settings classes (extends Settings, public properties, gro… | `php`, `laravel`, `spatie`, `settings`, `filament`, `configuration` |

### laravel-filament — Filament admin panels: resources, schemas, tables, widgets, actions, tenancy (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `filament` | Filament v5 — Panels, Resources, Schemas, Tables, Widgets, Actions: структура файлов, CLI… | `php`, `laravel`, `filament`, `ui`, `admin-panel`, `crud`, `livewire` |

### laravel-livewire — Livewire 3 UI: dynamic Blade attributes (ComponentAttributeBag) (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `livewire-blade-attributes` | Livewire 3 delta gotchas for Blade-component attributes. Activate when writing/reviewing … | `livewire`, `blade`, `laravel`, `frontend`, `advisory`, `gotchas` |

### laravel-testing — Laravel testing: Pest feature/unit, DB isolation guard, Dusk browser tests, health checks (4)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `health-checks` | spatie/laravel-health in Laravel: custom Check classes (disk, queue, scheduler heartbeat,… | `laravel`, `health`, `monitoring`, `spatie`, `liveness`, `readiness`, `observability` |
| `laravel-dusk` | Laravel Dusk: browser E2E tests, isolated test DB, run from Docker via host ChromeDriver,… | `php`, `laravel`, `dusk`, `e2e`, `browser-testing`, `chromedriver`, `docker` |
| `laravel-testing` | Feature/unit/pest testing patterns: test DB isolation, Docker/local env detection, covera… | `php`, `laravel`, `testing` |
| `test-isolation-guard` | Guard Laravel tests against running on prod/dev DB and prod media disk: bootstrap.php set… | `php`, `laravel`, `testing`, `isolation`, `safety`, `database`, `ci`, `refreshdatabase` |

### legal — Legal operations: contracts, compliance, risk (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `legal-super-skill` | Comprehensive legal operations skill merging Perplexity Computer's 6 legal skills with Cl… |  |

### marketing — Marketing: strategy, campaigns, content, growth (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `marketing-super-skill` | Comprehensive end-to-end marketing skill merging Perplexity Computer's 6 built-in marketi… |  |

### mobile — Mobile development: Flutter — design-to-code, theming, layout mapping from Figma (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `figma-to-flutter` | Map Figma Dev Mode MCP design to Flutter: Auto-layout → Row/Column/Expanded/Padding, toke… | `figma`, `flutter`, `dart`, `mobile`, `design-tokens`, `theming`, `auto-layout` |

### operator — Incident response, runbooks, postmortems, on-call and capacity planning (6)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `capacity-planning` | Capacity planning — load forecasting, headroom, autoscaling policy, cost budget, what to … | `ops`, `observability`, `monitoring`, `sla` |
| `incident-response` | Prod incident response process — severity levels, roles (IC/Comms/SME), communication, ac… | `incident`, `ops`, `workflow`, `sla` |
| `oncall-rotation` | On-call rotation design — schedule, primary/secondary, handoff, compensation, burnout def… | `ops`, `incident`, `sla`, `handoff` |
| `operations-cx-super-skill` | Comprehensive operations and customer experience skill merging Perplexity Computer's 5 CX… |  |
| `postmortem` | Blameless postmortem after SEV-1/2 incident — timeline, root cause (5 Whys), contributing… | `incident`, `ops`, `workflow`, `reflection` |
| `runbook` | Operational runbook template per P1/P2 alert — symptoms, diagnostics, mitigation steps, e… | `ops`, `incident`, `template`, `monitoring` |

### oss-dev — Open-source development: releases, governance, DX, dependency audits + language references (10)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `dependency-audit` | Dependency audit — lockfile sanity, vuln scan, license compatibility, supply-chain risk, … | `oss`, `compliance`, `security`, `dependencies`, `php` |
| `dx-design` | Developer Experience: README, quick-start (≤60s), API ergonomics, error messages, types, … | `oss`, `documentation`, `api`, `cli` |
| `gh-review` | Review and handoff changes via GitHub CLI (gh) with context economy: gh pr diff/view/comm… | `github`, `gh`, `review`, `handoff`, `tokens`, `context` |
| `github-flow` | Chain Issue → Branch → PR → Merge → Tag → Release on GitHub: naming, labels, SemVer oracl… | `oss`, `github`, `git`, `semver`, `release` |
| `issue-triage` | Стейт-машина обработки issue и внешних PR: категория (bug/enhancement) + статус (needs-tr… | `triage`, `issues`, `github`, `state-machine`, `governance` |
| `oss-development` | OSS project: repo structure, README, Architecture, ADR, SemVer, CI/CD. PHP specifics in .… | `oss`, `architecture`, `documentation`, `ci` |
| `oss-governance` | LICENSE, CoC, CONTRIBUTING, MAINTAINERS, RFC process, security policy for an OSS project | `oss`, `compliance`, `license`, `security`, `documentation` |
| `release-engineering` | SemVer strategy, CHANGELOG, release pipeline (CI/CD), pre-releases, deprecation policy fo… | `oss`, `semver`, `release`, `changelog`, `ci` |
| `resolving-merge-conflicts` | Дисциплина разрешения активного git merge/rebase-конфликта: понять состояние и первичные … | `git`, `merge`, `rebase`, `conflicts` |
| `to-issues` | Разбить план/спеку/PRD на независимо-«хватаемые» GitHub-issue ВЕРТИКАЛЬНЫМИ срезами (trac… | `issues`, `github`, `vertical-slices`, `decomposition`, `planning` |

### php — PHP and Laravel core: architecture, structure, conventions, DI, database, repositories, patterns, static analysis (13)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `code-style-spatie` | Стиль кода Laravel/PHP по гайдлайнам Spatie: Laravel-конвенции прежде PSR-12, типизация в… | `php`, `laravel`, `code-style`, `spatie` |
| `database` | Database migrations, models, and table naming. Activate when writing migrations, creating… | `php`, `laravel`, `database`, `migrations` |
| `dependency-injection` | Layer interaction via constructor injection: final readonly + promotion, injection matrix… | `php`, `laravel`, `di`, `architecture` |
| `laravel` | Laravel architecture patterns: actions, repositories, resources | `php`, `laravel`, `architecture`, `patterns` |
| `laravel-best-practices` | Лучшие практики Laravel: 20 категорий правил (Eloquent, валидация, кеш, очереди, безопасн… | `php`, `laravel`, `best-practices` |
| `laravel-structure` | Laravel project structure canon for greenfield and adding domains: domain taxonomy, layer… | `php`, `laravel`, `architecture`, `structure` |
| `named-arguments` | PHP rule: method/function calls use named arguments; exceptions; activate when writing/re… | `php`, `code-style`, `readability`, `conventions` |
| `naming-conventions` | Naming Laravel/PHP entities: repository methods by intent (not findByCodeOrFail-explosion… | `php`, `laravel`, `naming`, `conventions`, `code-style`, `readability` |
| `pao` | Laravel PAO — agent-optimized PHP tool output: PHPUnit/Pest/Paratest/PHPStan/Rector/Artis… | `php`, `laravel`, `testing`, `tokens`, `agent-output` |
| `php-patterns` | PHP domain patterns: VO, DTO, pipeline, specification — selection guide | `php`, `laravel`, `patterns`, `dto`, `architecture` |
| `php-upgrade-checklist` | PHP version upgrade checklist (minor/major): sync image/CI, composer update + clear depre… | `php`, `upgrade`, `version`, `rector`, `phpstan`, `composer` |
| `repositories` | Laravel repositories: read/store split, model scopes, delta-DTO, facade, VisibilityService | `php`, `laravel`, `repository`, `architecture` |
| `static-analysis` | PHP/Laravel static analysis & linting: Laravel Pint, PHPStan, Rector locally + CI, refere… | `php`, `laravel`, `quality` |

### php-packages — Laravel package development: scaffold, service provider, testing, compatibility, docs, releases (9)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `laravel-package-compatibility` | Use this skill when reviewing Laravel package compatibility across composer constraints, … | `php`, `laravel`, `package-dev` |
| `laravel-package-docs` | Use this skill when writing or revising package documentation after creating a package fr… | `php`, `laravel`, `package-dev` |
| `laravel-package-expressive` | Upstream-скилл для работы НАД самим пакетом WendellAdriel/laravel-expressive (starter kit… | `php`, `laravel`, `package-dev` |
| `laravel-package-generate-skill` | Use this skill when creating or updating the bundled Laravel Boost skill under resources/… | `php`, `laravel`, `package-dev` |
| `laravel-package-release` | Use this skill when preparing Laravel package releases: generated release notes, GitHub r… | `php`, `laravel`, `package-dev` |
| `laravel-package-scaffold` | Use this skill when adding Laravel package capabilities or package shape changes after cr… | `php`, `laravel`, `package-dev` |
| `laravel-package-service-provider` | Use this skill when changing a Laravel package service provider: config merges, routes, v… | `php`, `laravel`, `package-dev` |
| `laravel-package-testing` | Use this skill when writing, editing, fixing, or reviewing package tests with Pest 4 and … | `php`, `laravel`, `package-dev` |
| `laravel-packages` | Build Laravel packages: scaffold, tests, publish package skills to consumers via vendor:p… | `php`, `laravel`, `package-dev`, `skills` |

### pm — Product management: BRD, PRD, roadmap, monetization, unit economics (10)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `brd` | Business Requirements Document: functional requirements, user stories, acceptance criteria | `requirements`, `template` |
| `business-process` | Business processes, workflow, FSM, sequence/state diagrams, error handling | `requirements`, `workflow` |
| `go-to-market` | GTM strategy, ICP, messaging framework, acquisition channels, launch plan | `gtm`, `market`, `monetization` |
| `monetization-design` | Pick business model (SaaS / marketplace / ads / freemium / hybrid) with trade-off matrix … | `monetization`, `market` |
| `pm-super-skill` | Comprehensive product management skill merging Perplexity Computer's 6 PM skills with Cla… |  |
| `pmf-diagnostics` | Product-market fit diagnostics — pre-launch measurement framework, Sean Ellis test (>40%)… | `validation`, `market` |
| `prd-from-brd` | Product Requirements Document — expands BRD into detailed user stories with acceptance cr… | `requirements`, `template` |
| `product-roadmap` | MVP definition, Impact/Effort prioritization, MVP → v1 → v2 → Backlog phases, phase-trans… | `requirements`, `gtm`, `market` |
| `requirement-critic` | BRD audit: completeness, conflicts, assumptions, gap analysis, MoSCoW. Chat-only, no file | `requirements`, `validation` |
| `unit-economics` | Unit economics: LTV, CAC, payback, churn, break-even, 3 scenarios | `monetization` |

### python — Python: ML project structure, virtualenv and dependency management (2)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `ml-project-structure` | Standardized ML/Data Science project structure (Cookiecutter Data Science) | `python`, `ml`, `structure`, `architecture`, `data`, `conventions` |
| `venv-dependencies` | Python dependency management and virtual environments for project reproducibility | `python`, `venv`, `dependencies`, `tooling`, `quality`, `conventions` |

### quality — Code review, refactoring plans, tech debt audits, test strategy (10)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `code-review` | Code review process & checklist: mandatory checks, comment severity grades, async vs sync… | `quality`, `validation`, `review`, `github`, `workflow` |
| `code-simplifier` | Simplify freshly written code without changing behavior: dead code, needless abstractions… | `quality`, `refactoring`, `refactor`, `ci`, `validation` |
| `diagnosing-bugs` | Дисциплина диагностики трудных багов и регрессий производительности: СНАЧАЛА строим тугой… | `debugging`, `diagnostics`, `feedback-loop`, `performance`, `testing` |
| `mutation-testing` | PHP mutation testing via Infection: infection.json5 (source/excludes, mutators, logs, min… | `quality`, `testing`, `mutation`, `infection`, `php`, `ci`, `coverage` |
| `playwright-e2e` | Browser E2E with Playwright for a web app (frontend-agnostic: Vue/Inertia/Livewire): play… | `playwright`, `e2e`, `browser`, `testing`, `storage-state`, `ci`, `quality`, `frontend`, `typescript` |
| `refactoring-plan` | Safe refactoring plan: scope, Mikado / strangler pattern, atomic steps, done criteria, ro… | `quality`, `refactor`, `refactoring`, `validation`, `workflow` |
| `tdd-discipline` | Дисциплина TDD по циклу red-green-refactor ВЕРТИКАЛЬНЫМИ срезами (tracer bullets), а НЕ г… | `tdd`, `testing`, `red-green-refactor`, `vertical-slices` |
| `tech-debt-audit` | Tech-debt inventory, classification (architectural/code/dependency/test/process), priorit… | `quality`, `validation`, `refactor`, `dependencies`, `workflow` |
| `test-strategy` | Test strategy: pyramid (unit/integration/e2e), coverage policy, mock vs real, which featu… | `quality`, `testing`, `coverage`, `validation`, `ci`, `architecture`, `pest` |
| `testing-safety-report` | Safety report after a risky change (migrations, schema/layer refactor, dependency upgrade… | `testing`, `safety`, `migrations`, `reporting`, `verification`, `quality`, `refactor` |

### research — Research and knowledge management (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `research-knowledge-super-skill` | Comprehensive research and knowledge management skill merging Perplexity Computer's resea… |  |

### roles — Personas: tech lead, startup CTO, solo founder, open-source maintainer (4)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `open-source-maintainer` | OSS Maintainer — triage, review, releases | `role`, `persona`, `oss`, `github`, `review`, `release`, `triage` |
| `solo-founder` | Solo Founder — weekly review, decision log | `role`, `persona`, `discovery`, `market`, `validation` |
| `startup-cto` | Startup CTO persona — tech radar, hiring, architecture decisions | `role`, `persona`, `architecture`, `stack-choice`, `discipline` |
| `tech-lead` | Tech Lead persona — sprint kickoff, 1:1s, team coordination | `role`, `persona`, `orchestration`, `review`, `workflow` |

### sales — Sales: pipeline, outreach, CRM, negotiation (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `sales-super-skill` | Comprehensive end-to-end sales skill merging Perplexity Computer's 6 built-in sales skill… |  |

### security — AI agent security: prompt injection defense, hardening (1)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `agent-security-super-skill` | Comprehensive AI agent security skill covering prompt injection defense, skill/plugin val… |  |

### system — Local environment topology: the three hub nodes (Brain vault, swissknifeman, projects base) and how agents navigate between projects and their docs (5)

| Скилл | Описание | Теги |
|:--|:--|:--|
| `agent-packs` | Install and VERSIONED upgrade of agent-packs (Claude Code agents/workflows/hooks) from ha… | `agent-packs`, `templates`, `versioning`, `upgrade`, `install`, `claude-code`, `harness`, `lock` |
| `cross-project-coordinator` | Orchestrate cross-project code analysis: walk linked projects (via topology), find dups/d… | `cross-project`, `coordination`, `refactoring`, `duplication`, `topology`, `orchestration`, `agents`, `tokens` |
| `local-topology` | Root map of the local dev environment — three hub nodes (Brain vault, swissknifeman, proj… | `topology`, `architecture`, `navigation`, `meta`, `cross-project` |
| `session-observer` | EXPERIMENTAL (enable per-project). Post-hoc Claude Code session analysis from JSONL logs … | `observer`, `session-analysis`, `learning`, `jsonl`, `drift`, `self-improvement`, `post-mortem` |
| `shared-memory` | Constellation shared brain via hook ~/.claude/hooks/memory/ + mAInd daemon. Recall before… | `memory`, `cross-project`, `topology`, `recall`, `context`, `coordination` |

## Tag matrix

Поиск скиллов по тегу (грузи точечно, не весь бакет).

| Тег | Скиллы |
|:--|:--|
| `3d` | `build-loop`, `mcp-blender`, `model-rules`, `parametric-config`, `threading`, `version-gotchas` |
| `actions` | `enum-state-machine` |
| `admin-panel` | `filament` |
| `adr` | `architecture`, `domain-modeling`, `grill-with-docs`, `tech-stack-selection` |
| `advisory` | `livewire-blade-attributes`, `version-gotchas` |
| `agent-output` | `pao` |
| `agent-packs` | `agent-packs` |
| `agentic` | `agent-design`, `eval-design` |
| `agents` | `ai-agents`, `complex-task-orchestrator`, `cross-project-coordinator`, `laravel-subagents` |
| `ai` | `ai-agents`, `skills-ssot` |
| `ai-act` | `legal-compliance` |
| `ai-context` | `skills-ssot` |
| `alerting` | `observability-design` |
| `anti-bloat` | `package-contribution-protocol` |
| `api` | `api-design`, `dx-design`, `laravel-data`, `version-gotchas` |
| `architecture` | `agent-design`, `api-design`, `architecture`, `data-schema`, `dependency-injection`, `inertia-vue`, `laravel`, `laravel-structure`, `local-topology`, `ml-project-structure`, `modular-architecture`, `oss-development`, `php-patterns`, `pinia-stores`, `project-map`, `repositories`, `startup-cto`, `tech-stack-selection`, `test-strategy` |
| `attribute` | `attribute-authorization` |
| `attributes` | `enum-attributes` |
| `auth` | `security-design` |
| `authorization` | `attribute-authorization`, `azguard`, `laravel-permissions` |
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
| `claude-code` | `agent-packs`, `context-economy`, `mcp-advisor`, `verify-claims` |
| `clean-code` | `naming-conventions` |
| `cli` | `dx-design` |
| `code-connect` | `figma-mcp-core` |
| `code-style` | `code-style-spatie`, `eslint-flat-config`, `js-code-style`, `named-arguments`, `naming-conventions` |
| `comments` | `writing-style` |
| `commits` | `writing-style` |
| `compliance` | `dependency-audit`, `legal-compliance`, `oss-governance`, `risk-assessment`, `security-design` |
| `components` | `naive-ui-theming`, `reka-ui-cva` |
| `composable` | `dark-mode`, `vue-composition-api` |
| `composables` | `vue-testing-best-practices` |
| `compose` | `docker-dev-prod`, `docker-services` |
| `composer` | `php-upgrade-checklist` |
| `config` | `config-conventions` |
| `configuration` | `spatie-settings` |
| `conflicts` | `resolving-merge-conflicts` |
| `context` | `anti-drift`, `compact-responses`, `context-economy`, `gh-review`, `mcp-advisor`, `session-handoff`, `shared-memory`, `task-brief-template`, `verify-claims` |
| `contracts` | `api-design` |
| `contribution` | `package-contribution-protocol` |
| `conventional-commits` | `git-commit-rules` |
| `conventions` | `compact-responses`, `config-conventions`, `context-economy`, `git-commit-rules`, `ml-project-structure`, `model-rules`, `named-arguments`, `naming-conventions`, `packages-stack`, `project-map`, `skills-ssot`, `venv-dependencies` |
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
| `ddd` | `domain-modeling` |
| `debugging` | `diagnosing-bugs` |
| `decomposition` | `to-issues` |
| `deep-modules` | `codebase-design` |
| `dependencies` | `dependency-audit`, `packages-stack`, `tech-debt-audit`, `venv-dependencies` |
| `deployment` | `architecture` |
| `design` | `codebase-design` |
| `design-system` | `figma-mcp-core`, `reka-ui-cva` |
| `design-tokens` | `figma-mcp-core`, `figma-to-flutter`, `figma-to-vue`, `naive-ui-theming`, `tailwind-conventions` |
| `dev-mode` | `figma-mcp-core` |
| `devops` | `ci-cd`, `db-test-preflight`, `docker`, `docker-dev-prod`, `docker-php`, `docker-postgres`, `docker-services`, `docker-vite`, `makefile`, `node-pnpm-preflight` |
| `di` | `dependency-injection` |
| `diagnostics` | `diagnosing-bugs` |
| `discipline` | `anti-drift`, `naming-conventions`, `startup-cto` |
| `discovery` | `competitive-analysis`, `customer-discovery`, `idea-discovery`, `new-project`, `solo-founder`, `spec-interview` |
| `docker` | `db-test-preflight`, `docker`, `docker-dev-prod`, `docker-php`, `docker-postgres`, `docker-services`, `docker-vite`, `laravel-dusk`, `makefile` |
| `docs` | `grill-with-docs`, `writing-style` |
| `documentation` | `dx-design`, `oss-development`, `oss-governance` |
| `domain` | `domain-modeling`, `enum-state-machine`, `grill-with-docs` |
| `drift` | `session-observer` |
| `dto` | `backend-type-sync`, `laravel-data`, `php-patterns` |
| `duplication` | `cross-project-coordinator` |
| `dusk` | `laravel-dusk` |
| `dynamic-component` | `vue-dynamic-icons` |
| `e2e` | `laravel-dusk`, `playwright-e2e` |
| `echo` | `laravel-broadcasting` |
| `entities` | `data-schema` |
| `enum` | `attribute-authorization`, `azguard`, `backend-type-sync`, `enum-attributes`, `enum-state-machine` |
| `erd` | `data-schema` |
| `eslint` | `eslint-flat-config`, `wayfinder` |
| `fdm` | `build-loop`, `config-conventions`, `parametric-config`, `threading` |
| `feature-flags` | `pennant-development` |
| `feedback-loop` | `diagnosing-bugs` |
| `figma` | `figma-mcp-core`, `figma-to-flutter`, `figma-to-vue` |
| `filament` | `filament`, `modular-architecture`, `spatie-settings`, `vite-multi-build` |
| `file-upload` | `filepond-upload` |
| `filepond` | `filepond-upload` |
| `flat-config` | `eslint-flat-config` |
| `flutter` | `figma-to-flutter` |
| `forms` | `filepond-upload` |
| `frontend` | `backend-type-sync`, `docker-vite`, `eslint-flat-config`, `filepond-upload`, `inertia-vue`, `laravel-echo-client`, `livewire-blade-attributes`, `naive-ui-theming`, `pinia-stores`, `playwright-e2e`, `reka-ui-cva`, `vite-module-loader`, `vite-multi-build`, `vitest`, `vue-composition-api`, `vue-dynamic-icons`, `vue-router-best-practices`, `vue-testing-best-practices`, `wayfinder` |
| `gate` | `attribute-authorization`, `azguard` |
| `gdpr` | `legal-compliance`, `security-design` |
| `geometry` | `parametric-config`, `threading` |
| `gh` | `gh-review` |
| `git` | `git-commit-rules`, `git-safety`, `github-flow`, `gitops`, `resolving-merge-conflicts` |
| `github` | `code-review`, `gh-review`, `github-flow`, `gitops`, `issue-triage`, `open-source-maintainer`, `to-issues` |
| `github-actions` | `ci-cd` |
| `gitlab-ci` | `ci-cd` |
| `gitops` | `git-commit-rules`, `gitops` |
| `glossary` | `domain-modeling` |
| `gotchas` | `livewire-blade-attributes`, `version-gotchas` |
| `governance` | `issue-triage`, `package-contribution-protocol` |
| `grilling` | `grill-with-docs` |
| `gtm` | `competitive-analysis`, `go-to-market`, `new-project`, `pitch-deck`, `product-roadmap` |
| `guardrails` | `git-safety` |
| `handoff` | `gh-review`, `oncall-rotation`, `session-handoff` |
| `harness` | `agent-packs` |
| `headless` | `reka-ui-cva` |
| `health` | `health-checks` |
| `hooks` | `git-safety` |
| `icons` | `vue-dynamic-icons` |
| `image-preview` | `filepond-upload` |
| `images` | `medialibrary` |
| `implementation` | `implement` |
| `incident` | `incident-response`, `oncall-rotation`, `postmortem`, `runbook` |
| `inertia` | `filepond-upload`, `inertia-vue`, `laravel-data`, `wayfinder` |
| `infection` | `mutation-testing` |
| `init` | `git-safety`, `packages-stack` |
| `install` | `agent-packs` |
| `isolation` | `db-test-preflight`, `test-isolation-guard` |
| `issues` | `issue-triage`, `to-issues` |
| `javascript` | `js-code-style` |
| `jsdom` | `vitest` |
| `jsonl` | `session-observer` |
| `language` | `writing-style` |
| `laravel` | `attribute-authorization`, `azguard`, `backend-type-sync`, `botkit`, `ci-cd`, `code-style-spatie`, `database`, `dependency-injection`, `docker-dev-prod`, `docker-php`, `docker-services`, `docker-vite`, `enum-attributes`, `enum-state-machine`, `filament`, `filepond-upload`, `health-checks`, `inertia-vue`, `laravel`, `laravel-best-practices`, `laravel-broadcasting`, `laravel-data`, `laravel-dusk`, `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages`, `laravel-permissions`, `laravel-security-audit`, `laravel-structure`, `laravel-subagents`, `laravel-testing`, `livewire-blade-attributes`, `medialibrary`, `modular-architecture`, `naming-conventions`, `pao`, `pennant-development`, `php-patterns`, `repositories`, `spatie-settings`, `static-analysis`, `tailwind-conventions`, `test-isolation-guard`, `vite-module-loader`, `vite-multi-build`, `vitest`, `wayfinder` |
| `laravel-data` | `laravel-data` |
| `laravel-echo` | `laravel-echo-client` |
| `laravel-modules` | `modular-architecture` |
| `lazy-loading` | `vue-router-best-practices` |
| `learning` | `session-observer` |
| `license` | `oss-governance` |
| `liveness` | `health-checks` |
| `livewire` | `filament`, `livewire-blade-attributes` |
| `llm` | `eval-design` |
| `localstorage` | `dark-mode` |
| `lock` | `agent-packs` |
| `logging` | `observability-design` |
| `lucide` | `vue-dynamic-icons` |
| `make` | `makefile` |
| `market` | `adversarial-check`, `competitive-analysis`, `customer-discovery`, `defensibility`, `go-to-market`, `idea-discovery`, `monetization-design`, `new-project`, `pitch-deck`, `pmf-diagnostics`, `product-roadmap`, `solo-founder`, `startup-lifecycle` |
| `matchmedia` | `dark-mode` |
| `materials` | `scene-conventions` |
| `mcp` | `ai-agents`, `build-loop`, `figma-mcp-core`, `mcp-advisor`, `mcp-blender` |
| `media` | `medialibrary` |
| `memory` | `shared-memory` |
| `merge` | `resolving-merge-conflicts` |
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
| `navigation-guards` | `vue-router-best-practices` |
| `node` | `node-pnpm-preflight` |
| `nwidart` | `modular-architecture` |
| `observability` | `capacity-planning`, `health-checks`, `observability-design` |
| `observer` | `session-observer` |
| `onboarding` | `mcp-advisor` |
| `ops` | `capacity-planning`, `incident-response`, `oncall-rotation`, `postmortem`, `runbook` |
| `orchestration` | `ai-agents`, `anti-drift`, `complex-task-orchestrator`, `cross-project-coordinator`, `laravel-subagents`, `mcp-blender`, `tech-lead` |
| `oss` | `dependency-audit`, `dx-design`, `github-flow`, `open-source-maintainer`, `oss-development`, `oss-governance`, `release-engineering` |
| `ousterhout` | `codebase-design` |
| `owasp` | `security-design` |
| `package` | `package-contribution-protocol` |
| `package-dev` | `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages` |
| `parametric` | `build-loop`, `config-conventions`, `parametric-config`, `scene-conventions` |
| `parenting` | `scene-conventions` |
| `patterns` | `enum-attributes`, `laravel`, `php-patterns`, `vue-composition-api` |
| `pennant` | `pennant-development` |
| `performance` | `diagnosing-bugs` |
| `permissions` | `attribute-authorization`, `azguard`, `laravel-permissions` |
| `persona` | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| `pest` | `test-strategy` |
| `php` | `attribute-authorization`, `azguard`, `botkit`, `code-style-spatie`, `database`, `dependency-audit`, `dependency-injection`, `docker-php`, `enum-attributes`, `enum-state-machine`, `filament`, `laravel`, `laravel-best-practices`, `laravel-broadcasting`, `laravel-data`, `laravel-dusk`, `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages`, `laravel-permissions`, `laravel-security-audit`, `laravel-structure`, `laravel-testing`, `medialibrary`, `modular-architecture`, `mutation-testing`, `named-arguments`, `naming-conventions`, `pao`, `pennant-development`, `php-patterns`, `php-upgrade-checklist`, `repositories`, `spatie-settings`, `static-analysis`, `test-isolation-guard` |
| `phpstan` | `php-upgrade-checklist` |
| `pinia` | `pinia-stores`, `vue-testing-best-practices` |
| `planning` | `to-issues`, `verify-claims` |
| `playwright` | `playwright-e2e` |
| `pnpm` | `node-pnpm-preflight` |
| `post-mortem` | `session-observer` |
| `postgres` | `db-test-preflight`, `docker-postgres` |
| `preflight` | `db-test-preflight`, `node-pnpm-preflight` |
| `prettier` | `eslint-flat-config`, `js-code-style`, `tailwind-conventions` |
| `privacy` | `legal-compliance`, `security-design` |
| `prompt-engineering` | `ai-agents` |
| `pusher` | `laravel-echo-client` |
| `python` | `mcp-blender`, `ml-project-structure`, `parametric-config`, `venv-dependencies`, `version-gotchas` |
| `quality` | `code-review`, `code-simplifier`, `mutation-testing`, `playwright-e2e`, `refactoring-plan`, `static-analysis`, `tech-debt-audit`, `test-strategy`, `testing-safety-report`, `venv-dependencies` |
| `queue` | `docker-services` |
| `rag` | `ai-agents`, `verify-claims` |
| `rbac` | `attribute-authorization`, `azguard`, `laravel-permissions`, `security-design` |
| `readability` | `named-arguments`, `naming-conventions` |
| `readiness` | `health-checks` |
| `realtime` | `laravel-broadcasting`, `laravel-echo-client` |
| `rebase` | `resolving-merge-conflicts` |
| `recall` | `shared-memory` |
| `rector` | `php-upgrade-checklist` |
| `red-green-refactor` | `tdd-discipline` |
| `refactor` | `code-simplifier`, `refactoring-plan`, `tech-debt-audit`, `testing-safety-report` |
| `refactoring` | `code-simplifier`, `cross-project-coordinator`, `refactoring-plan` |
| `reflection` | `attribute-authorization`, `enum-attributes`, `postmortem` |
| `refreshdatabase` | `test-isolation-guard` |
| `regulatory` | `legal-compliance` |
| `reka-ui` | `reka-ui-cva` |
| `release` | `ci-cd`, `github-flow`, `open-source-maintainer`, `release-engineering` |
| `reporting` | `testing-safety-report` |
| `repository` | `repositories` |
| `requirements` | `brd`, `business-process`, `grill-with-docs`, `idea-discovery`, `new-project`, `prd-from-brd`, `product-roadmap`, `requirement-critic`, `spec-interview`, `startup-lifecycle`, `task-brief-template` |
| `research` | `verify-claims` |
| `rest` | `api-design` |
| `reverb` | `laravel-broadcasting`, `laravel-echo-client` |
| `review` | `code-review`, `gh-review`, `implement`, `open-source-maintainer`, `tech-lead` |
| `role` | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| `routes` | `wayfinder` |
| `routing` | `project-map`, `vue-router-best-practices` |
| `rules` | `model-rules` |
| `runbook` | `observability-design` |
| `russian` | `writing-style` |
| `safety` | `git-safety`, `test-isolation-guard`, `testing-safety-report` |
| `scalability` | `architecture` |
| `scene` | `scene-conventions` |
| `schema` | `data-schema` |
| `screenshot` | `mcp-blender` |
| `seam` | `codebase-design` |
| `security` | `agent-design`, `ci-cd`, `dependency-audit`, `laravel-security-audit`, `oss-governance`, `risk-assessment`, `security-design` |
| `self-improvement` | `session-observer` |
| `semver` | `github-flow`, `package-contribution-protocol`, `release-engineering` |
| `session-analysis` | `session-observer` |
| `settings` | `spatie-settings` |
| `skills` | `laravel-packages`, `skills-ssot` |
| `sla` | `build-loop`, `capacity-planning`, `config-conventions`, `incident-response`, `oncall-rotation`, `parametric-config`, `threading` |
| `slo` | `observability-design` |
| `spatie` | `backend-type-sync`, `code-style-spatie`, `health-checks`, `js-code-style`, `laravel-data`, `medialibrary`, `spatie-settings` |
| `ssot` | `skills-ssot` |
| `ssr` | `dark-mode` |
| `stack` | `packages-stack` |
| `stack-choice` | `startup-cto`, `tech-stack-selection` |
| `state-machine` | `enum-state-machine`, `issue-triage` |
| `state-management` | `pinia-stores` |
| `storage-state` | `playwright-e2e` |
| `store` | `pinia-stores` |
| `stride` | `security-design` |
| `structure` | `inertia-vue`, `laravel-structure`, `ml-project-structure`, `project-map` |
| `style` | `compact-responses`, `writing-style` |
| `stylistic` | `eslint-flat-config` |
| `subagents` | `ai-agents` |
| `tailwind` | `dark-mode`, `figma-to-vue`, `naive-ui-theming`, `reka-ui-cva`, `tailwind-conventions`, `vite-multi-build` |
| `tailwindcss-v4` | `figma-to-vue`, `tailwind-conventions` |
| `tdd` | `implement`, `tdd-discipline` |
| `template` | `brd`, `model-rules`, `prd-from-brd`, `runbook`, `task-brief-template` |
| `templates` | `agent-packs` |
| `testability` | `codebase-design` |
| `testing` | `db-test-preflight`, `diagnosing-bugs`, `docker-postgres`, `eval-design`, `laravel-testing`, `mutation-testing`, `pao`, `playwright-e2e`, `tdd-discipline`, `test-isolation-guard`, `test-strategy`, `testing-safety-report`, `vitest`, `vue-testing-best-practices` |
| `tests` | `writing-style` |
| `theme` | `dark-mode` |
| `theming` | `figma-to-flutter`, `naive-ui-theming` |
| `threading` | `threading` |
| `threat-modeling` | `security-design` |
| `tokens` | `compact-responses`, `context-economy`, `cross-project-coordinator`, `gh-review`, `pao`, `session-handoff` |
| `tooling` | `eslint-flat-config`, `mcp-advisor`, `venv-dependencies` |
| `topology` | `cross-project-coordinator`, `local-topology`, `shared-memory` |
| `tracing` | `observability-design` |
| `trade-off` | `tech-stack-selection` |
| `transitions` | `enum-state-machine` |
| `triage` | `issue-triage`, `open-source-maintainer` |
| `type-sync` | `backend-type-sync` |
| `types` | `backend-type-sync` |
| `typescript` | `backend-type-sync`, `enum-attributes`, `eslint-flat-config`, `js-code-style`, `playwright-e2e`, `vue-dynamic-icons`, `vue-router-best-practices`, `wayfinder` |
| `ubiquitous-language` | `domain-modeling` |
| `ui` | `figma-mcp-core`, `filament`, `naive-ui-theming`, `reka-ui-cva` |
| `units` | `parametric-config` |
| `upgrade` | `agent-packs`, `php-upgrade-checklist` |
| `uploads` | `filepond-upload`, `medialibrary` |
| `validation` | `adversarial-check`, `agent-design`, `code-review`, `code-simplifier`, `cross-layer-change-checklist`, `customer-discovery`, `defensibility`, `eval-design`, `laravel-data`, `pmf-diagnostics`, `refactoring-plan`, `requirement-critic`, `risk-assessment`, `solo-founder`, `startup-lifecycle`, `tech-debt-audit`, `test-strategy` |
| `variants` | `reka-ui-cva` |
| `venv` | `venv-dependencies` |
| `verification` | `testing-safety-report`, `verify-claims` |
| `version` | `php-upgrade-checklist`, `version-gotchas` |
| `versioning` | `agent-packs` |
| `vertical-slices` | `tdd-discipline`, `to-issues` |
| `viewport` | `mcp-blender` |
| `vite` | `docker-vite`, `vite-module-loader`, `vite-multi-build` |
| `vitest` | `vitest`, `vue-testing-best-practices` |
| `vue` | `dark-mode`, `eslint-flat-config`, `figma-to-vue`, `filepond-upload`, `inertia-vue`, `js-code-style`, `laravel-echo-client`, `naive-ui-theming`, `pinia-stores`, `reka-ui-cva`, `tailwind-conventions`, `vite-module-loader`, `vitest`, `vue-composition-api`, `vue-dynamic-icons`, `vue-router-best-practices`, `vue-testing-best-practices` |
| `vue-router` | `vue-router-best-practices` |
| `vue-test-utils` | `vue-testing-best-practices` |
| `wayfinder` | `wayfinder` |
| `websocket` | `docker-services` |
| `websockets` | `laravel-broadcasting`, `laravel-echo-client` |
| `workflow` | `anti-drift`, `build-loop`, `business-process`, `code-review`, `compact-responses`, `complex-task-orchestrator`, `context-economy`, `cross-layer-change-checklist`, `enum-state-machine`, `implement`, `incident-response`, `laravel-subagents`, `postmortem`, `refactoring-plan`, `session-handoff`, `skills-ssot`, `spec-interview`, `task-brief-template`, `tech-debt-audit`, `tech-lead` |
| `writing` | `writing-style` |
