# Skill Registry swissknifeman

<!-- GENERATED `skiller registry` — do not edit manually -->

Source of truth for ported skills (machine registry - `skills.json`). Distribution to projects: `skiller connect` (plugin buckets) / `vendor` (physical. transfer). CORE-set of token skills (`general`/`oss-dev`) is heard by default - see `connect`/`vendor`.

Total: 209 skills in 47 buckets.

## Skills for buckets

### ai — AI agent building: design, tools, evaluation (3)

| Skill | Description | Tags |
|:--|:--|:--|
| `ai-agents` | Navigator for the AI-agent building reference (vendored super-skill): agent patterns, MCP… | `ai`, `agents`, `mcp`, `rag`, `orchestration`, `prompt-engineering`, `subagents` |
| `mcp-builder` | Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to … |  |
| `token-efficient` | Reduces Perplexity Computer output verbosity and token waste. Eliminates sycophantic open… |  |

### architect — Architecture, API and data design, security, observability, tech stack selection (15)

| Skill | Description | Tags |
|:--|:--|:--|
| `agent-design` | Design or audit an agent loop, tool boundary, autonomy policy, or recovery behavior. | `agentic`, `architecture`, `security`, `validation` |
| `api-design` | Design or evolve an API contract: compatibility, auth, errors, pagination, and retry sema… | `api`, `architecture`, `rest`, `contracts` |
| `architecture` | Choose a consequential architecture or record a disputed design decision; scale artifacts… | `architecture`, `adr`, `c4`, `scalability`, `deployment` |
| `codebase-design` | Shared vocabulary and discipline for designing DEEP modules (Ousterhout/Feathers): Module… | `design`, `deep-modules`, `ousterhout`, `seam`, `testability` |
| `data-schema` | Use when designing a data schema: entities, attributes, relations. DB-agnostic — markdown… | `data`, `architecture`, `schema`, `entities`, `erd` |
| `dev-engineering-super-skill` | Broad engineering-bucket navigator (composite of external dev skills). For specific work … |  |
| `domain-modeling` | Active domain-model discipline: challenge terms, stress-test with scenarios, RECORD the g… | `domain`, `ddd`, `glossary`, `adr`, `ubiquitous-language` |
| `ecosystem-reuse-gate` | Gate against reinventing functionality when designing a new project/feature: before build… | `ecosystem`, `reuse`, `vendor-vs-build`, `gate`, `architecture` |
| `eval-design` | Use when evaluating LLM/AI output quality: eval-set, metrics, regression harness, automat… | `agentic`, `validation`, `llm`, `metrics`, `testing` |
| `figma-mcp-core` | Figma Dev Mode MCP discipline: real tools (get_metadata, get_variable_defs, get_code, get… | `figma`, `mcp`, `design-system`, `design-tokens`, `dev-mode`, `code-connect`, `ui` |
| `legal-compliance` | Use when checking regulatory compliance before launch: GDPR, CCPA, AI Act, DMCA, COPPA, D… | `compliance`, `gdpr`, `privacy`, `ai-act`, `regulatory` |
| `observability-design` | Use when designing observability for prod-readiness: logging, metrics, tracing, alerting,… | `observability`, `logging`, `metrics`, `tracing`, `alerting`, `slo`, `runbook` |
| `package-contribution-protocol` | Change a dependency at its owning source; distinguish authorized bugfixes from new public… | `governance`, `package`, `monorepo`, `contribution`, `semver`, `anti-bloat`, `boundary` |
| `security-design` | Design or review changed trust, auth, secrets, sensitive-data, or external exposure bound… | `security`, `compliance`, `auth`, `owasp`, `threat-modeling`, `rbac`, `gdpr`, `privacy`, `stride` |
| `tech-stack-selection` | Use when selecting a tech stack: trade-off matrix before architecture design, ADR-first s… | `stack-choice`, `architecture`, `adr`, `trade-off` |

### axioma — Axioma ecosystem doctrine & reuse: dev philosophy, tech-radar binding, vendor-vs-build discipline (project-scoped bucket) (4)

| Skill | Description | Tags |
|:--|:--|:--|
| `axioma-doctrine` | Axioma ecosystem development doctrine: five imperative pillars (horizontal core → vertica… | `axioma`, `doctrine`, `architecture`, `ecosystem` |
| `axioma-glossary` | Binds domain-modeling discipline to the live thin term-index of the Axioma ecosystem: can… | `axioma`, `ecosystem`, `glossary`, `term-index` |
| `axioma-stack` | Binds the universal reuse-gate to the live Ecosystem_Tech_Radar.md of the Axioma ecosyste… | `axioma`, `ecosystem`, `reuse`, `tech-radar` |
| `ecosystem-map` | Where docs, plans, findings and vault links live in a project and how repo↔Brain sync. A … | `axioma`, `ecosystem`, `plans`, `docs`, `navigation` |

### azguard — azguard package usage: code-first RBAC, panels, scoped roles, abilities (academici package — skill will relocate into the package repo) (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `azguard` | Roles & access control via azguard package: code-first RBAC, panels, scoped roles, direct… | `php`, `laravel`, `permissions`, `azguard`, `rbac`, `authorization`, `gate`, `enum` |

### blender — Universal Blender bpy+MCP tooling: MCP workflow primitives, viewport modes, camera helper, version gotchas (2)

| Skill | Description | Tags |
|:--|:--|:--|
| `mcp-blender` | Use when working through Blender MCP: execution, object inspection, viewport setup and sc… | `blender`, `mcp`, `python`, `3d`, `bpy`, `viewport`, `camera`, `screenshot`, `orchestration` |
| `version-gotchas` | Use when hitting Blender 5.0 API issues: known breaking changes and pitfalls. | `blender`, `api`, `bpy`, `3d`, `python`, `gotchas`, `advisory`, `version` |

### blender-modeling — Parametric CAD modeling in Blender for FDM/SLA: config-driven dataclasses, profile/revolve geometry, threading clearances, config & scene conventions, model-rules template, generic build loop (7)

| Skill | Description | Tags |
|:--|:--|:--|
| `build-loop` | Use for an incremental parametric part build or geometry fix: config preflight, scoped re… | `blender`, `cad`, `parametric`, `workflow`, `bpy`, `mcp`, `3d`, `fdm`, `sla` |
| `config-conventions` | Use for physical config fields, units and dependencies between parametric parts. Keeps pu… | `blender`, `cad`, `parametric`, `dataclass`, `config`, `cross-config`, `conventions`, `bpy`, `fdm`, `sla` |
| `model-rules` | Use for model work: read its existing models/{name}/ai/rules.md for construction, axes, i… | `blender`, `template`, `rules`, `3d`, `cad`, `conventions` |
| `model-verification` | Use for final digital acceptance, export or a requested whole-model audit of a declared a… | `blender`, `cad`, `verification`, `evidence`, `release`, `fdm`, `sla` |
| `parametric-config` | Use when editing parametric configs, derivations, profiles or builders. Covers pure versu… | `blender`, `bpy`, `parametric`, `dataclass`, `cad`, `fdm`, `sla`, `geometry`, `units`, `python`, `3d` |
| `scene-conventions` | Use when naming or parenting model objects, assigning materials, or defining scene owners… | `blender`, `cad`, `parametric`, `naming`, `scene`, `materials`, `parenting`, `bpy` |
| `threading` | Use when designing threads on FDM/SLA parts: material, print physics, radial clearance by… | `blender`, `3d`, `fdm`, `sla`, `threading`, `geometry`, `bpy` |

### botkit — botkit package usage: bot framework patterns — BotDefinition, service provider, webhooks (academici package — skill will relocate into the package repo) (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `botkit` | Use when building bot framework features: BotDefinition contract, package service provide… | `php`, `laravel`, `bots`, `botkit` |

### creative — Creative studio: video, design, content production (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `content-creative-super-skill` | Creative studio: video production, speech synthesis, image generation, website building, … |  |

### dart — Dart package and SDK development: public API, pubspec, null safety, testing and compatibility (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `dart-package-development` | Use when developing, maintaining, or releasing a Dart package/SDK: pubspec, public API, n… | `dart`, `pub`, `package`, `sdk`, `api`, `null-safety`, `testing`, `compatibility` |

### devops — Docker environments, CI/CD pipelines, GitOps (11)

| Skill | Description | Tags |
|:--|:--|:--|
| `ci-cd` | GitHub Actions / GitLab CI pipelines for Laravel: lint, tests, build, release + security … | `ci`, `github-actions`, `gitlab-ci`, `laravel`, `devops`, `release`, `security`, `coverage` |
| `db-test-preflight` | Pre-flight check of test DB (Postgres in Docker) BEFORE running tests: container up (dock… | `postgres`, `docker`, `testing`, `preflight`, `devops`, `ci`, `isolation` |
| `docker` | Router for Dockerizing a Laravel/PHP app: directs to the right sub-skill (PHP image, Post… | `docker`, `devops`, `router` |
| `docker-dev-prod` | Split docker-compose into dev (build + bind-mount) and prod (prebuilt image + named volum… | `docker`, `devops`, `compose`, `laravel` |
| `docker-php` | Production PHP Docker image: alpine-fpm or all-in-one serversideup/php (FPM+Nginx), entry… | `docker`, `php`, `devops`, `laravel` |
| `docker-postgres` | PostgreSQL in Docker: pg_isready healthcheck, named volume for data, init script creating… | `docker`, `devops`, `postgres`, `testing` |
| `docker-services` | Full Laravel service stack from one image: app (fpm-nginx), queue, scheduler, reverb, opt… | `docker`, `devops`, `compose`, `laravel`, `queue`, `websocket` |
| `docker-vite` | Vite dev server as separate compose service for Laravel: named volume for node_modules, H… | `docker`, `devops`, `vite`, `frontend`, `laravel` |
| `gitops` | Use when defining team Git strategy: branch model (main/develop/feature/hotfix), PR workf… | `git`, `gitops`, `github` |
| `makefile` | Makefile as single entrypoint: help, .PHONY, Docker command aliases; delegating root Make… | `make`, `devops`, `docker` |
| `node-pnpm-preflight` | Check Node/pnpm availability on host before commands and git hooks that use pnpm (commitl… | `node`, `pnpm`, `devops`, `preflight`, `ci` |

### finance — Finance and accounting: bookkeeping, reporting, FP&A (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `finance-super-skill` | Finance and accounting: financial statements, journal entries, reconciliation, close mana… |  |

### founder — Idea discovery, competitive analysis, risk assessment, pitch decks (10)

| Skill | Description | Tags |
|:--|:--|:--|
| `adversarial-check` | Structured devil's advocate — 3 strongest counterarguments, failed competitors, negative … | `validation`, `market` |
| `competitive-analysis` | Use when researching market, competitors, JTBD, open niche, attack vector. Uses Perplexit… | `discovery`, `market`, `gtm` |
| `customer-discovery` | Systematic discovery — target profile, interview framework (past not future), post-interv… | `discovery`, `validation`, `market` |
| `defensibility` | Moat analysis for Scale stage — accumulated depth, data flywheel, workflow lock-in, domai… | `market`, `validation` |
| `idea-audit` | Full destructive audit of an idea / concept / spec — first-principles → market skepticism… | `validation`, `market`, `architecture` |
| `idea-discovery` | Structured interview of a raw idea — JTBD, problem statement, hypothesis, before competit… | `discovery`, `requirements`, `market` |
| `new-project` | Use when launching a new startup project: concept, competitors, risks, full folder struct… | `discovery`, `requirements`, `market`, `gtm` |
| `pitch-deck` | Use when building a 10-slide investor deck per YC/Sequoia canon from existing project art… | `gtm`, `market`, `monetization` |
| `risk-assessment` | Use when assessing startup risk: 6 categories (incl. AI/Agentic), Risk Matrix, RAID log, … | `validation`, `compliance`, `security`, `agentic` |
| `startup-lifecycle` | 4 AI-native startup stages (Idea→MVP→Launch→Scale) with exit-criteria, failure modes, ant… | `validation`, `requirements`, `market` |

### frontend — Frontend core: general front skills (web design guidelines, document writer, file upload) (3)

| Skill | Description | Tags |
|:--|:--|:--|
| `document-writer` | Use when writing blog posts or documentation markdown files - provides writing style guid… |  |
| `filepond-upload` | File upload via FilePond in Vue + Laravel: register vue-filepond + plugins (validate-type… | `filepond`, `vue`, `laravel`, `file-upload`, `frontend`, `forms`, `image-preview`, `inertia`, `uploads` |
| `web-design-guidelines` | Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI",… |  |

### frontend-animations — Animations with Motion Vue (motion-v) (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `motion` | Use when adding animations with Motion Vue (motion-v) - provides motion component API, ge… |  |

### frontend-backend — Backend integration layer: Inertia+Vue, Laravel Echo realtime client, backend→frontend type sync (3)

| Skill | Description | Tags |
|:--|:--|:--|
| `backend-type-sync` | Use for Laravel enum/DTO to TypeScript generation; route typing belongs to Wayfinder. | `typescript`, `laravel`, `spatie`, `types`, `enum`, `dto`, `frontend`, `type-sync`, `ci` |
| `inertia-vue` | Use for Laravel/Inertia Vue pages, forms, navigation, and resources/js organization. | `inertia`, `vue`, `laravel`, `frontend`, `architecture`, `structure` |
| `laravel-echo-client` | Use for Vue Laravel Echo subscriptions, private/presence channels, cleanup, and socket ID… | `laravel-echo`, `reverb`, `pusher`, `websockets`, `realtime`, `vue`, `broadcasting`, `frontend` |

### frontend-figma — Figma Dev Mode MCP → Vue mapping (uses architect/figma-mcp-core) (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `figma-to-vue` | Map Figma Dev Mode MCP design to Vue + Tailwind v4: Auto-layout → flexbox/grid, tokens.js… | `figma`, `vue`, `tailwind`, `tailwindcss-v4`, `cva`, `design-tokens`, `dark-mode`, `auto-layout` |

### frontend-linting — JS/TS tooling and style: antfu config, ESLint flat config, Spatie JS style, TS library authoring (4)

| Skill | Description | Tags |
|:--|:--|:--|
| `antfu` | Anthony Fu's opinionated tooling and conventions for JavaScript/TypeScript projects. Use … |  |
| `eslint-flat-config` | ESLint flat config (eslint.config.js) for Vue 3 + TypeScript: defineConfigWithVueTs/types… | `eslint`, `prettier`, `flat-config`, `vue`, `typescript`, `stylistic`, `tooling`, `code-style`, `frontend` |
| `js-code-style` | JS/TS style per Spatie: 4 spaces, width 120, single quotes, const-first, strict ===, func… | `javascript`, `typescript`, `code-style`, `spatie`, `prettier`, `vue` |
| `ts-library` | Use when authoring TypeScript libraries or npm packages - covers project setup, package.j… |  |

### frontend-naive-ui — Naive UI component library theming (GlobalThemeOverrides) (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `naive-ui-theming` | Use for Naive UI theme tokens, GlobalThemeOverrides, NConfigProvider, and dark mode. | `naive-ui`, `vue`, `theming`, `design-tokens`, `dark-mode`, `tailwind`, `frontend`, `components`, `ui` |

### frontend-nuxt — Nuxt 4+: server routes, modules, SEO meta-module (3)

| Skill | Description | Tags |
|:--|:--|:--|
| `nuxt` | Use for Nuxt 4+ routes, middleware, composables, server handlers, and project configurati… |  |
| `nuxt-modules` | Use for Nuxt modules: Kit hooks, runtime/server extensions, module tests, and release set… |  |
| `nuxt-seo` | Use for Nuxt SEO modules: robots, sitemap, OG images, metadata, and structured data. |  |

### frontend-reka — Reka UI headless primitives + CVA variants (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `reka-ui-cva` | UI component library on Reka UI headless primitives + class-variance-authority (cva) vari… | `reka-ui`, `cva`, `vue`, `tailwind`, `headless`, `components`, `variants`, `design-system`, `ui`, `frontend` |

### frontend-tailwind — Tailwind CSS v4 conventions and dark-mode theming (2)

| Skill | Description | Tags |
|:--|:--|:--|
| `dark-mode` | Use for Vue light/dark/system switching, SSR theme restore, and preventing theme flash. | `dark-mode`, `theme`, `vue`, `composable`, `ssr`, `tailwind`, `matchmedia`, `localstorage` |
| `tailwind-conventions` | Use for Tailwind v4 in Laravel/Vue: CSS-first config, theme tokens, classes, and formatti… | `tailwind`, `tailwindcss-v4`, `css`, `vue`, `laravel`, `dark-mode`, `design-tokens`, `prettier` |

### frontend-vite — Vite build tooling: config/plugins/SSR, project module loader, multi-build, VitePress (4)

| Skill | Description | Tags |
|:--|:--|:--|
| `vite` | Vite build tool configuration, plugin API, SSR, and Vite 8 Rolldown migration. Use when w… |  |
| `vite-module-loader` | Use when configuring Vite as the primary frontend bundler: base config, aliases, build pr… | `vite`, `frontend`, `build`, `laravel`, `vue` |
| `vite-multi-build` | Two independent Vite builds in one Laravel project: main app + Filament admin, with separ… | `vite`, `laravel`, `filament`, `tailwind`, `build`, `multi-config`, `frontend` |
| `vitepress` | VitePress static site generator powered by Vite and Vue. Use when building documentation … |  |

### frontend-vue — Vue 3 ecosystem: Composition API, best practices, router, VueUse, Pinia state, Vitest testing (11)

| Skill | Description | Tags |
|:--|:--|:--|
| `pinia` | Use for Pinia APIs: defining stores, typed state/getters/actions, and store composition. |  |
| `pinia-stores` | Use for project Pinia setup-store conventions, shared state, hydration, and persistence. | `pinia`, `vue`, `frontend`, `state-management`, `store`, `architecture` |
| `vitest` | Use for Vue/Inertia-on-Laravel Vitest setup: jsdom, test layout, and generated-code exclu… | `vitest`, `testing`, `vue`, `coverage`, `jsdom`, `laravel`, `frontend` |
| `vitest-vue` | Use for Vitest APIs: tests, mocks, coverage, filtering, and fixtures in Vite projects. |  |
| `vue` | Use for Vue 3 APIs: SFC macros, reactivity, watchers, and built-in components. |  |
| `vue-best-practices` | Use for Vue workflow and component design; follow the project's Composition/Options choic… |  |
| `vue-composition-api` | Use for project ref-first/composable conventions; Vue API syntax belongs to the vue skill. | `vue`, `frontend`, `composable`, `patterns` |
| `vue-dynamic-icons` | Use for Vue SVG icons selected by string name: component :is, typed names, and icon props. | `vue`, `icons`, `dynamic-component`, `lucide`, `typescript`, `frontend` |
| `vue-router-best-practices` | Use for Vue Router 4 routes, navigation guards, redirects, lazy views, and scroll restora… | `vue`, `vue-router`, `frontend`, `routing`, `navigation-guards`, `lazy-loading`, `typescript` |
| `vue-testing-best-practices` | Use for Vue Test Utils 2 component/composable tests, Pinia fakes, async DOM, and emits. | `vue`, `testing`, `vitest`, `vue-test-utils`, `pinia`, `composables`, `frontend` |
| `vueuse-functions` | Select a VueUse composable for an applicable Vue/Nuxt task when VueUse is available. | `vue`, `nuxt`, `vueuse`, `composables` |

### frontend-wayfinder — Laravel Wayfinder: type-safe routes/controller actions in the frontend (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `wayfinder` | Use for Laravel Wayfinder route/action generation, typed imports, forms, and import bound… | `wayfinder`, `laravel`, `typescript`, `routes`, `inertia`, `eslint`, `frontend` |

### general — General agent workflow conventions: git commits, task briefs, project maps, cross-layer checklists (20)

| Skill | Description | Tags |
|:--|:--|:--|
| `anti-drift` | Recover from repeated failed approaches or growing scope; preserve authorized progress. | `workflow`, `discipline`, `orchestration`, `context` |
| `compact-responses` | Use when the user explicitly requests terse output; preserve necessary explanations, prog… | `conventions`, `style`, `tokens`, `context`, `workflow` |
| `complex-task-orchestrator` | Complex-task orchestration: decomposition, context routing, risk, Definition of Done. | `workflow`, `orchestration`, `checklist`, `agents` |
| `context-economy` | Reduce measured context overhead with targeted reads, on-demand instructions, continuity … | `tokens`, `context`, `claude-code`, `workflow`, `conventions` |
| `cross-layer-change-checklist` | Use when a change spans multiple layers: code, authorization, UI, docs, tests. | `checklist`, `workflow`, `validation` |
| `git-commit-rules` | Use when preparing a Git commit: husky/commitlint, message format, safe action order. | `git`, `conventions`, `conventional-commits`, `gitops` |
| `git-safety` | Guard against destructive git commands via a Claude Code PreToolUse hook: blocks push/res… | `git`, `safety`, `hooks`, `guardrails`, `init` |
| `grill-with-docs` | Ruthless grilling session that SIMULTANEOUSLY builds a domain model: refines a plan/desig… | `grilling`, `requirements`, `domain`, `adr`, `docs` |
| `implement` | Implement a chunk of work from a spec/PRD/issue via a minimal chain: tdd-discipline on ag… | `workflow`, `implementation`, `tdd`, `review` |
| `mcp-advisor` | Pick MCP servers for a project at onboarding/sync: which to connect (context7/playwright/… | `mcp`, `onboarding`, `tooling`, `context`, `claude-code` |
| `naming-conventions` | Naming discipline (language-agnostic): name reveals intent, not implementation; fight noi… | `naming`, `conventions`, `readability`, `code-style`, `discipline`, `clean-code` |
| `packages-stack` | Project external-dependency registry methodology: which packages are used and for what, a… | `dependencies`, `conventions`, `navigation`, `stack`, `init` |
| `project-map` | Project structure map methodology: zone directories by responsibility for safe change rou… | `conventions`, `navigation`, `architecture`, `structure`, `routing` |
| `session-handoff` | Cross-session/agent handoff: compress a session into state, decisions, open items. | `workflow`, `context`, `tokens`, `handoff` |
| `shell` | Growing cookbook of shell constructs compatible with this environment's hooks (currently … | `workflow`, `bash`, `shell`, `safety`, `hooks` |
| `skills-ssot` | Resolve duplicate or drifting skill delivery by inspecting each source, generator, and pr… | `ai-context`, `skills`, `ssot`, `workflow`, `conventions`, `ai` |
| `spec-interview` | Pre-code interview: one question at a time, reads the codebase itself, proposes a recomme… | `workflow`, `requirements`, `discovery` |
| `task-brief-template` | Brief template for complex tasks: goal, scope, invariants, assumptions, out of scope, acc… | `workflow`, `template`, `requirements`, `context` |
| `verify-claims` | Use when a decision relies on changing external premises; verify in primary sources. Repo… | `verification`, `rag`, `research`, `planning`, `context`, `claude-code` |
| `writing-style` | Tone & language of code artifacts: Russian by default for comments, commit bodies, test d… | `writing`, `language`, `russian`, `comments`, `commits`, `tests`, `docs`, `style` |

### laravel-architecture — Scaling architecture: modular monolith/DDD, enum state machines, enum attributes, subagent orchestration (6)

| Skill | Description | Tags |
|:--|:--|:--|
| `config-driven-abstraction` | Config-driven cache-safe Registry+Builder for multi-panel/multi-tenant Laravel: immutable… | `php`, `laravel`, `architecture`, `config`, `registry`, `multi-tenant` |
| `eloquent-accessors` | Activate when writing/refactoring Eloquent accessors and mutators: when you see legacy ge… | `php`, `laravel`, `eloquent`, `attributes`, `accessors`, `mutators`, `patterns` |
| `enum-attributes` | Use for enum metadata: replace label()/color()/description() match-ladders with PHP attri… | `php`, `enum`, `attributes`, `reflection`, `laravel`, `patterns`, `typescript` |
| `enum-state-machine` | Activate when a domain status (Order/Document/Subscription) needs transition rules: edge … | `php`, `enum`, `state-machine`, `workflow`, `laravel`, `transitions`, `domain`, `actions` |
| `laravel-subagents` | Subagent orchestration on large Laravel tasks: activation threshold, delegating research … | `workflow`, `orchestration`, `agents`, `laravel` |
| `modular-architecture` | Scale Laravel code as it grows: organize by business domain, Modular Monolith and DDD pat… | `php`, `laravel`, `architecture`, `nwidart`, `laravel-modules`, `filament` |

### laravel-auth — Authorization & security: permissions/RBAC, attribute-based gates, security audit (3)

| Skill | Description | Tags |
|:--|:--|:--|
| `attribute-authorization` | Use for #[CheckPermission] action attributes and reflection middleware over Laravel Gate. | `php`, `laravel`, `authorization`, `attribute`, `reflection`, `middleware`, `gate`, `enum`, `permissions`, `rbac` |
| `laravel-permissions` | Use for native Laravel policies/gates and entity RBAC; azguard has its own skill. | `php`, `laravel`, `permissions`, `azguard`, `rbac`, `authorization` |
| `laravel-security-audit` | Use to audit Laravel auth, raw queries, mass assignment, XSS, CSRF, and unsafe input. | `php`, `laravel`, `security` |

### laravel-data-layer — Typed data + realtime: spatie/laravel-data DTOs (TS export), Echo/Reverb broadcasting (2)

| Skill | Description | Tags |
|:--|:--|:--|
| `laravel-broadcasting` | Use for Laravel broadcast events, channel auth, Echo/Reverb/Pusher/Ably integration. | `php`, `laravel`, `broadcasting`, `echo`, `reverb`, `websockets`, `realtime` |
| `laravel-data` | Use for spatie/laravel-data DTOs: validation, casts, nested data, and typed API output. | `php`, `laravel`, `spatie`, `laravel-data`, `dto`, `data-transfer-object`, `casts`, `validation`, `inertia`, `api` |

### laravel-extras — Optional Laravel runtime packages: media library, typed settings, Pennant feature flags (3)

| Skill | Description | Tags |
|:--|:--|:--|
| `medialibrary` | Use when attaching files to Eloquent models: spatie/laravel-medialibrary collections, con… | `php`, `laravel`, `media`, `spatie`, `uploads`, `images` |
| `pennant-development` | Laravel Pennant feature flags: define/active/for-scope, the @feature directive, activatio… | `php`, `laravel`, `pennant`, `feature-flags` |
| `spatie-settings` | spatie/laravel-settings: typed settings classes (extends Settings, group()), migrations a… | `php`, `laravel`, `spatie`, `settings`, `filament`, `configuration` |

### laravel-filament — Filament admin panels: resources, schemas, tables, widgets, actions, tenancy (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `filament` | Use for Filament v5 panels, resources, schemas, tables, actions, auth, and Artisan scaffo… | `php`, `laravel`, `filament`, `ui`, `admin-panel`, `crud`, `livewire` |

### laravel-livewire — Livewire 3 UI: dynamic Blade attributes (ComponentAttributeBag) (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `livewire-blade-attributes` | Livewire 3 Blade-component attribute delta gotchas. Activate when a tag attribute must be… | `livewire`, `blade`, `laravel`, `frontend`, `advisory`, `gotchas` |

### laravel-testing — Laravel testing: Pest feature/unit, DB isolation guard, Dusk browser tests, health checks (4)

| Skill | Description | Tags |
|:--|:--|:--|
| `health-checks` | Use for spatie/laravel-health checks, readiness endpoints, heartbeat, and failure alerts. | `laravel`, `health`, `monitoring`, `spatie`, `liveness`, `readiness`, `observability` |
| `laravel-dusk` | Use for Laravel Dusk browser tests: isolated DB, Docker/ChromeDriver, and Page Objects. | `php`, `laravel`, `dusk`, `e2e`, `browser-testing`, `chromedriver`, `docker` |
| `laravel-testing` | Use for Laravel/Pest tests: isolated DB, environment preflight, fixtures, and test compos… | `php`, `laravel`, `testing` |
| `test-isolation-guard` | Use before Laravel tests that can mutate DB/files: prove isolated serial or parallel targ… | `php`, `laravel`, `testing`, `isolation`, `safety`, `database`, `ci`, `refreshdatabase` |

### legal — Legal operations: contracts, compliance, risk (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `legal-super-skill` | Legal operations: contract review, NDA triage, compliance (GDPR/CCPA), risk assessment, m… |  |

### marketing — Marketing: strategy, campaigns, content, growth (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `marketing-super-skill` | Marketing: campaign planning, brand voice, competitive analysis, SEO, content creation, p… |  |

### mobile — Mobile development: Flutter — design-to-code, theming, layout mapping from Figma (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `figma-to-flutter` | Map Figma Dev Mode MCP design to Flutter: Auto-layout → Row/Column/Expanded/Padding, toke… | `figma`, `flutter`, `dart`, `mobile`, `design-tokens`, `theming`, `auto-layout` |

### operator — Incident response, runbooks, postmortems, on-call and capacity planning (6)

| Skill | Description | Tags |
|:--|:--|:--|
| `capacity-planning` | Capacity planning — load forecasting, headroom, autoscaling policy, cost budget, what to … | `ops`, `observability`, `monitoring`, `sla` |
| `incident-response` | Prod incident response process — severity levels, roles (IC/Comms/SME), communication, ac… | `incident`, `ops`, `workflow`, `sla` |
| `oncall-rotation` | On-call rotation design — schedule, primary/secondary, handoff, compensation, burnout def… | `ops`, `incident`, `sla`, `handoff` |
| `operations-cx-super-skill` | Broad operations/CX-bucket navigator (composite of external CX skills). For specific work… |  |
| `postmortem` | Blameless postmortem after SEV-1/2 incident — timeline, root cause (5 Whys), contributing… | `incident`, `ops`, `workflow`, `reflection` |
| `runbook` | Operational runbook template per P1/P2 alert — symptoms, diagnostics, mitigation steps, e… | `ops`, `incident`, `template`, `monitoring` |

### oss-dev — Open-source development: releases, governance, DX, dependency audits + language references (10)

| Skill | Description | Tags |
|:--|:--|:--|
| `dependency-audit` | Use when auditing lockfiles, vulnerabilities, licenses, supply-chain risk, or SBOMs. | `oss`, `compliance`, `security`, `dependencies`, `php` |
| `dx-design` | Use when designing developer UX: quick-start, README, API errors, types, and CLI behavior. | `oss`, `documentation`, `api`, `cli` |
| `gh-review` | Use for GitHub PR review or handoff via gh: targeted diffs, file reads, and review comman… | `github`, `gh`, `review`, `handoff`, `tokens`, `context` |
| `github-flow` | Use for GitHub Issue→Branch→PR→Merge→Tag→Release workflow, templates, and version routing. | `oss`, `github`, `git`, `semver`, `release` |
| `issue-triage` | Explicit issue/PR triage only: classify, verify, and prepare tracker updates via gh. | `triage`, `issues`, `github`, `state-machine`, `governance` |
| `oss-development` | Use for OSS repository structure, package docs, architecture decisions, versioning, and C… | `oss`, `architecture`, `documentation`, `ci` |
| `oss-governance` | Use when defining OSS license, conduct, contribution, maintainer, RFC, or security polici… | `oss`, `compliance`, `license`, `security`, `documentation` |
| `release-engineering` | Use for package release policy: SemVer, changelog, CI releases, prereleases, and deprecat… | `oss`, `semver`, `release`, `changelog`, `ci` |
| `resolving-merge-conflicts` | Use during an active merge/rebase conflict: preserve both intents and verify resolution. | `git`, `merge`, `rebase`, `conflicts` |
| `to-issues` | Explicit publishing request only: turn a plan/spec into vertical GitHub issues with depen… | `issues`, `github`, `vertical-slices`, `decomposition`, `planning` |

### php — PHP and Laravel core: architecture, structure, conventions, DI, database, repositories, patterns, static analysis (17)

| Skill | Description | Tags |
|:--|:--|:--|
| `code-style-spatie` | Use when applying adopted Spatie PHP style: types, early returns, Laravel conventions. | `php`, `laravel`, `code-style`, `spatie` |
| `cursor-pagination-design` | Use for keyset pagination or duplicate/skipped feed rows under concurrent inserts. | `php`, `laravel`, `pagination`, `cursor`, `database` |
| `database` | Use when changing migrations, models, table names, foreign keys, or database schema. | `php`, `laravel`, `database`, `migrations` |
| `dependency-injection` | Wire dependencies in an adopted Laravel layer model; inspect the relevant DI example. | `php`, `laravel`, `di`, `architecture` |
| `laravel` | Navigate an adopted Laravel layered architecture; choose only the relevant class pattern. | `php`, `laravel`, `architecture`, `patterns` |
| `laravel-best-practices` | Laravel fallback guidance when equivalent versioned project or Boost skills are unavailab… | `php`, `laravel`, `best-practices` |
| `laravel-structure` | Place new Laravel domain classes within the project's chosen structure. | `php`, `laravel`, `architecture`, `structure` |
| `named-arguments` | Use when writing PHP calls under the project's named-argument rule and exceptions. | `php`, `code-style`, `readability`, `conventions` |
| `namespace-refactor-safety` | Use for PHP namespace/class moves: FQN-safe edits, aliases, and caller compatibility. | `php`, `refactor`, `namespace`, `safety` |
| `pao` | Use when installing or verifying PAO compact output for PHP tests, analysis, or Artisan. | `php`, `laravel`, `testing`, `tokens`, `agent-output` |
| `php-naming-conventions` | Use when naming PHP classes, repository methods, DTOs, events, tables, or routes. | `php`, `laravel`, `naming`, `conventions`, `code-style`, `readability` |
| `php-patterns` | Use when choosing a PHP domain pattern: VO, DTO, pipeline, specification — selection guid… | `php`, `laravel`, `patterns`, `dto`, `architecture` |
| `php-upgrade-checklist` | Use before upgrading PHP: runtime/CI alignment, dependencies, deprecations, compatibility. | `php`, `upgrade`, `version`, `rector`, `phpstan`, `composer` |
| `production-readiness-checklist` | Use for risky Laravel changes: atomicity, idempotency, queues, cursors, and state transit… | `php`, `laravel`, `review`, `production`, `reliability`, `quality` |
| `repositories` | Implement repositories when justified; Read/Store and visibility patterns apply if adopte… | `php`, `laravel`, `repository`, `architecture` |
| `static-analysis` | Use when configuring or running Laravel Pint, PHPStan, or Rector locally and in CI. | `php`, `laravel`, `quality` |
| `transactional-outbox-relay` | Use for durable async delivery: transactional outbox, relay retries, idempotent consumers. | `php`, `laravel`, `queue`, `outbox`, `reliability`, `async` |

### php-packages — Laravel package development: scaffold, service provider, testing, compatibility, docs, releases (9)

| Skill | Description | Tags |
|:--|:--|:--|
| `laravel-package-compatibility` | Use for Laravel package PHP/Laravel/Testbench constraints and CI compatibility matrices. | `php`, `laravel`, `package-dev` |
| `laravel-package-docs` | Use for configured Laravel package README, VitePress, install/usage, and upgrade docs. | `php`, `laravel`, `package-dev` |
| `laravel-package-expressive` | Use only on WendellAdriel/laravel-expressive starter itself, not configured package featu… | `php`, `laravel`, `package-dev` |
| `laravel-package-generate-skill` | Use to update a package's resources/boost/skills after its public API or docs change. | `php`, `laravel`, `package-dev` |
| `laravel-package-release` | Use to prepare Laravel package releases, notes, tags, and checks; publishing needs author… | `php`, `laravel`, `package-dev` |
| `laravel-package-scaffold` | Use to add commands, routes, migrations, config, or publishable assets to a configured pa… | `php`, `laravel`, `package-dev` |
| `laravel-package-service-provider` | Use for Laravel package providers: boot/register, config, routes, views, assets, and comm… | `php`, `laravel`, `package-dev` |
| `laravel-package-testing` | Use for Laravel package Pest 4/Testbench tests: HTTP, commands, config, migrations, and f… | `php`, `laravel`, `package-dev` |
| `laravel-packages` | Use when building a Laravel package: scaffold, tests, and publishing skills to consumers. | `php`, `laravel`, `package-dev`, `skills` |

### pm — Product management: BRD, PRD, roadmap, monetization, unit economics (10)

| Skill | Description | Tags |
|:--|:--|:--|
| `brd` | Use when writing a Business Requirements Document: functional requirements, user stories,… | `requirements`, `template` |
| `business-process` | Use when modeling business processes: workflow, FSM, sequence/state diagrams, error handl… | `requirements`, `workflow` |
| `go-to-market` | Use when building a GTM strategy: ICP, messaging framework, acquisition channels, launch … | `gtm`, `market`, `monetization` |
| `monetization-design` | Pick business model (SaaS / marketplace / ads / freemium / hybrid) with trade-off matrix … | `monetization`, `market` |
| `pm-super-skill` | Broad PM-bucket navigator (composite of external PM skills). For specific work prefer the… |  |
| `pmf-diagnostics` | Product-market fit diagnostics — pre-launch measurement framework, Sean Ellis test (>40%)… | `validation`, `market` |
| `prd-from-brd` | Product Requirements Document — expands BRD into detailed user stories with acceptance cr… | `requirements`, `template` |
| `product-roadmap` | MVP definition, Impact/Effort prioritization, MVP → v1 → v2 → Backlog phases, phase-trans… | `requirements`, `gtm`, `market` |
| `requirement-critic` | Audit of a written spec/BRD: completeness, conflicts, assumptions, gap analysis, MoSCoW +… | `requirements`, `validation` |
| `unit-economics` | Use when modeling unit economics: LTV, CAC, payback, churn, break-even, 3 scenarios. | `monetization` |

### python — Python: ML project structure, virtualenv and dependency management (2)

| Skill | Description | Tags |
|:--|:--|:--|
| `ml-project-structure` | Use when structuring an ML/Data Science project per Cookiecutter Data Science. | `python`, `ml`, `structure`, `architecture`, `data`, `conventions` |
| `venv-dependencies` | Use when managing Python dependencies and virtual environments for project reproducibilit… | `python`, `venv`, `dependencies`, `tooling`, `quality`, `conventions` |

### quality — Code review, refactoring plans, tech debt audits, test strategy (11)

| Skill | Description | Tags |
|:--|:--|:--|
| `artifact-review` | Review plans, specifications, docs, or mixed artifacts against their adopted contracts. | `quality`, `review`, `taxonomy`, `plan`, `docs`, `code`, `severity`, `conventional-comments` |
| `code-review` | Review a code diff or define team review policy; severity follows demonstrated impact. | `quality`, `validation`, `review`, `github`, `workflow` |
| `code-simplifier` | Use to simplify a fresh diff: remove duplication and needless layers while preserving beh… | `quality`, `refactoring`, `refactor`, `ci`, `validation` |
| `diagnosing-bugs` | Diagnose hard, flaky, or performance bugs after ordinary inspection cannot establish the … | `debugging`, `diagnostics`, `feedback-loop`, `performance`, `testing` |
| `mutation-testing` | Use for PHP Infection setup, mutation CI checks, MSI reports, or surviving mutants. | `quality`, `testing`, `mutation`, `infection`, `php`, `ci`, `coverage` |
| `playwright-e2e` | Use for Playwright browser scenarios, auth state, config, or isolated test data. | `playwright`, `e2e`, `browser`, `testing`, `storage-state`, `ci`, `quality`, `frontend`, `typescript` |
| `refactoring-plan` | Use when planning a safe refactor: scope, incremental steps, validation, and rollback. | `quality`, `refactor`, `refactoring`, `validation`, `workflow` |
| `tdd-discipline` | Test-first work explicitly requested or adopted by the project: one behavior per red-gree… | `tdd`, `testing`, `red-green-refactor`, `vertical-slices` |
| `tech-debt-audit` | Use when auditing technical debt: classify findings and prioritize by impact and effort. | `quality`, `validation`, `refactor`, `dependencies`, `workflow` |
| `test-strategy` | Design or revise a test suite strategy; choose checks by behavior and risk, not fixed per… | `quality`, `testing`, `coverage`, `validation`, `ci`, `architecture`, `pest` |
| `testing-safety-report` | Use after a risky schema, layer, or dependency change to report checks and remaining risk… | `testing`, `safety`, `migrations`, `reporting`, `verification`, `quality`, `refactor` |

### research — Research and knowledge management (2)

| Skill | Description | Tags |
|:--|:--|:--|
| `query-craft` | Use when a search query needs precision: concrete question, version, environment and sour… | `research`, `perplexity`, `search`, `query`, `rag`, `context7`, `claude-code` |
| `research-knowledge-super-skill` | Research and knowledge management: deep research, knowledge graphs, data exploration, sta… |  |

### roles — Personas: tech lead, startup CTO, solo founder, open-source maintainer (4)

| Skill | Description | Tags |
|:--|:--|:--|
| `open-source-maintainer` | Use when acting as OSS Maintainer: triage, review, releases. | `role`, `persona`, `oss`, `github`, `review`, `release`, `triage` |
| `solo-founder` | Use when acting as Solo Founder: weekly review, decision log. | `role`, `persona`, `discovery`, `market`, `validation` |
| `startup-cto` | Use when acting as Startup CTO: tech radar, hiring, architecture decisions. | `role`, `persona`, `architecture`, `stack-choice`, `discipline` |
| `tech-lead` | Use when acting as Tech Lead: sprint kickoff, 1:1s, team coordination. | `role`, `persona`, `orchestration`, `review`, `workflow` |

### sales — Sales: pipeline, outreach, CRM, negotiation (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `sales-super-skill` | End-to-end sales: account research, call prep, competitive intelligence, outreach draftin… |  |

### security — AI agent security: prompt injection defense, hardening (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `agent-security-super-skill` | AI agent security: prompt injection defense, skill/plugin validation, memory poisoning pr… |  |

### system — provided by host modules: maind, harness, analyst, brain

### voice-ai — Realtime voice AI agents: WebRTC+WebSocket transport, VAD + semantic turn detection, sub-500ms barge-in, sub-800ms latency budget, STT→LLM→TTS orchestration, session state-machine, RU stack (Yandex SpeechKit / SaluteSpeech / GigaChat) + offline fallback (1)

| Skill | Description | Tags |
|:--|:--|:--|
| `voice-ai` | Designing realtime voice AI agents: transport (WebRTC media + WebSocket control), turn de… | `voice`, `realtime`, `webrtc`, `stt`, `tts`, `vad`, `barge-in`, `latency`, `russian-stack` |

## Tag matrix

Search for skills by tag (load pointwise, not the whole bucket).

| Tag | Skills |
|:--|:--|
| `3d` | `build-loop`, `mcp-blender`, `model-rules`, `parametric-config`, `threading`, `version-gotchas` |
| `accessors` | `eloquent-accessors` |
| `actions` | `enum-state-machine` |
| `admin-panel` | `filament` |
| `adr` | `architecture`, `domain-modeling`, `grill-with-docs`, `tech-stack-selection` |
| `advisory` | `livewire-blade-attributes`, `version-gotchas` |
| `agent-output` | `pao` |
| `agentic` | `agent-design`, `eval-design`, `risk-assessment` |
| `agents` | `ai-agents`, `complex-task-orchestrator`, `laravel-subagents` |
| `ai` | `ai-agents`, `skills-ssot` |
| `ai-act` | `legal-compliance` |
| `ai-context` | `skills-ssot` |
| `alerting` | `observability-design` |
| `anti-bloat` | `package-contribution-protocol` |
| `api` | `api-design`, `dart-package-development`, `dx-design`, `laravel-data`, `version-gotchas` |
| `architecture` | `agent-design`, `api-design`, `architecture`, `axioma-doctrine`, `config-driven-abstraction`, `data-schema`, `dependency-injection`, `ecosystem-reuse-gate`, `idea-audit`, `inertia-vue`, `laravel`, `laravel-structure`, `ml-project-structure`, `modular-architecture`, `oss-development`, `php-patterns`, `pinia-stores`, `project-map`, `repositories`, `startup-cto`, `tech-stack-selection`, `test-strategy` |
| `async` | `transactional-outbox-relay` |
| `attribute` | `attribute-authorization` |
| `attributes` | `eloquent-accessors`, `enum-attributes` |
| `auth` | `security-design` |
| `authorization` | `attribute-authorization`, `azguard`, `laravel-permissions` |
| `auto-layout` | `figma-to-flutter`, `figma-to-vue` |
| `axioma` | `axioma-doctrine`, `axioma-glossary`, `axioma-stack`, `ecosystem-map` |
| `azguard` | `azguard`, `laravel-permissions` |
| `barge-in` | `voice-ai` |
| `bash` | `shell` |
| `best-practices` | `laravel-best-practices` |
| `blade` | `livewire-blade-attributes` |
| `blender` | `build-loop`, `config-conventions`, `mcp-blender`, `model-rules`, `model-verification`, `parametric-config`, `scene-conventions`, `threading`, `version-gotchas` |
| `botkit` | `botkit` |
| `bots` | `botkit` |
| `boundary` | `package-contribution-protocol` |
| `bpy` | `build-loop`, `config-conventions`, `mcp-blender`, `parametric-config`, `scene-conventions`, `threading`, `version-gotchas` |
| `broadcasting` | `laravel-broadcasting`, `laravel-echo-client` |
| `browser` | `playwright-e2e` |
| `browser-testing` | `laravel-dusk` |
| `build` | `vite-module-loader`, `vite-multi-build` |
| `c4` | `architecture` |
| `cad` | `build-loop`, `config-conventions`, `model-rules`, `model-verification`, `parametric-config`, `scene-conventions` |
| `camera` | `mcp-blender` |
| `casts` | `laravel-data` |
| `changelog` | `release-engineering` |
| `checklist` | `complex-task-orchestrator`, `cross-layer-change-checklist` |
| `chromedriver` | `laravel-dusk` |
| `ci` | `backend-type-sync`, `ci-cd`, `code-simplifier`, `db-test-preflight`, `mutation-testing`, `node-pnpm-preflight`, `oss-development`, `playwright-e2e`, `release-engineering`, `test-isolation-guard`, `test-strategy` |
| `claude-code` | `context-economy`, `mcp-advisor`, `query-craft`, `verify-claims` |
| `clean-code` | `naming-conventions` |
| `cli` | `dx-design` |
| `code` | `artifact-review` |
| `code-connect` | `figma-mcp-core` |
| `code-style` | `code-style-spatie`, `eslint-flat-config`, `js-code-style`, `named-arguments`, `naming-conventions`, `php-naming-conventions` |
| `comments` | `writing-style` |
| `commits` | `writing-style` |
| `compatibility` | `dart-package-development` |
| `compliance` | `dependency-audit`, `legal-compliance`, `oss-governance`, `risk-assessment`, `security-design` |
| `components` | `naive-ui-theming`, `reka-ui-cva` |
| `composable` | `dark-mode`, `vue-composition-api` |
| `composables` | `vue-testing-best-practices`, `vueuse-functions` |
| `compose` | `docker-dev-prod`, `docker-services` |
| `composer` | `php-upgrade-checklist` |
| `config` | `config-conventions`, `config-driven-abstraction` |
| `configuration` | `spatie-settings` |
| `conflicts` | `resolving-merge-conflicts` |
| `context` | `anti-drift`, `compact-responses`, `context-economy`, `gh-review`, `mcp-advisor`, `session-handoff`, `task-brief-template`, `verify-claims` |
| `context7` | `query-craft` |
| `contracts` | `api-design` |
| `contribution` | `package-contribution-protocol` |
| `conventional-comments` | `artifact-review` |
| `conventional-commits` | `git-commit-rules` |
| `conventions` | `compact-responses`, `config-conventions`, `context-economy`, `git-commit-rules`, `ml-project-structure`, `model-rules`, `named-arguments`, `naming-conventions`, `packages-stack`, `php-naming-conventions`, `project-map`, `skills-ssot`, `venv-dependencies` |
| `coverage` | `ci-cd`, `mutation-testing`, `test-strategy`, `vitest` |
| `cross-config` | `config-conventions` |
| `crud` | `filament` |
| `css` | `tailwind-conventions` |
| `cursor` | `cursor-pagination-design` |
| `cva` | `figma-to-vue`, `reka-ui-cva` |
| `dark-mode` | `dark-mode`, `figma-to-vue`, `naive-ui-theming`, `tailwind-conventions` |
| `dart` | `dart-package-development`, `figma-to-flutter` |
| `data` | `data-schema`, `ml-project-structure` |
| `data-transfer-object` | `laravel-data` |
| `database` | `cursor-pagination-design`, `database`, `test-isolation-guard` |
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
| `docs` | `artifact-review`, `ecosystem-map`, `grill-with-docs`, `writing-style` |
| `doctrine` | `axioma-doctrine` |
| `documentation` | `dx-design`, `oss-development`, `oss-governance` |
| `domain` | `domain-modeling`, `enum-state-machine`, `grill-with-docs` |
| `dto` | `backend-type-sync`, `laravel-data`, `php-patterns` |
| `dusk` | `laravel-dusk` |
| `dynamic-component` | `vue-dynamic-icons` |
| `e2e` | `laravel-dusk`, `playwright-e2e` |
| `echo` | `laravel-broadcasting` |
| `ecosystem` | `axioma-doctrine`, `axioma-glossary`, `axioma-stack`, `ecosystem-map`, `ecosystem-reuse-gate` |
| `eloquent` | `eloquent-accessors` |
| `entities` | `data-schema` |
| `enum` | `attribute-authorization`, `azguard`, `backend-type-sync`, `enum-attributes`, `enum-state-machine` |
| `erd` | `data-schema` |
| `eslint` | `eslint-flat-config`, `wayfinder` |
| `evidence` | `model-verification` |
| `fdm` | `build-loop`, `config-conventions`, `model-verification`, `parametric-config`, `threading` |
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
| `gate` | `attribute-authorization`, `azguard`, `ecosystem-reuse-gate` |
| `gdpr` | `legal-compliance`, `security-design` |
| `geometry` | `parametric-config`, `threading` |
| `gh` | `gh-review` |
| `git` | `git-commit-rules`, `git-safety`, `github-flow`, `gitops`, `resolving-merge-conflicts` |
| `github` | `code-review`, `gh-review`, `github-flow`, `gitops`, `issue-triage`, `open-source-maintainer`, `to-issues` |
| `github-actions` | `ci-cd` |
| `gitlab-ci` | `ci-cd` |
| `gitops` | `git-commit-rules`, `gitops` |
| `glossary` | `axioma-glossary`, `domain-modeling` |
| `gotchas` | `livewire-blade-attributes`, `version-gotchas` |
| `governance` | `issue-triage`, `package-contribution-protocol` |
| `grilling` | `grill-with-docs` |
| `gtm` | `competitive-analysis`, `go-to-market`, `new-project`, `pitch-deck`, `product-roadmap` |
| `guardrails` | `git-safety` |
| `handoff` | `gh-review`, `oncall-rotation`, `session-handoff` |
| `headless` | `reka-ui-cva` |
| `health` | `health-checks` |
| `hooks` | `git-safety`, `shell` |
| `icons` | `vue-dynamic-icons` |
| `image-preview` | `filepond-upload` |
| `images` | `medialibrary` |
| `implementation` | `implement` |
| `incident` | `incident-response`, `oncall-rotation`, `postmortem`, `runbook` |
| `inertia` | `filepond-upload`, `inertia-vue`, `laravel-data`, `wayfinder` |
| `infection` | `mutation-testing` |
| `init` | `git-safety`, `packages-stack` |
| `isolation` | `db-test-preflight`, `test-isolation-guard` |
| `issues` | `issue-triage`, `to-issues` |
| `javascript` | `js-code-style` |
| `jsdom` | `vitest` |
| `language` | `writing-style` |
| `laravel` | `attribute-authorization`, `azguard`, `backend-type-sync`, `botkit`, `ci-cd`, `code-style-spatie`, `config-driven-abstraction`, `cursor-pagination-design`, `database`, `dependency-injection`, `docker-dev-prod`, `docker-php`, `docker-services`, `docker-vite`, `eloquent-accessors`, `enum-attributes`, `enum-state-machine`, `filament`, `filepond-upload`, `health-checks`, `inertia-vue`, `laravel`, `laravel-best-practices`, `laravel-broadcasting`, `laravel-data`, `laravel-dusk`, `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages`, `laravel-permissions`, `laravel-security-audit`, `laravel-structure`, `laravel-subagents`, `laravel-testing`, `livewire-blade-attributes`, `medialibrary`, `modular-architecture`, `pao`, `pennant-development`, `php-naming-conventions`, `php-patterns`, `production-readiness-checklist`, `repositories`, `spatie-settings`, `static-analysis`, `tailwind-conventions`, `test-isolation-guard`, `transactional-outbox-relay`, `vite-module-loader`, `vite-multi-build`, `vitest`, `wayfinder` |
| `laravel-data` | `laravel-data` |
| `laravel-echo` | `laravel-echo-client` |
| `laravel-modules` | `modular-architecture` |
| `latency` | `voice-ai` |
| `lazy-loading` | `vue-router-best-practices` |
| `license` | `oss-governance` |
| `liveness` | `health-checks` |
| `livewire` | `filament`, `livewire-blade-attributes` |
| `llm` | `eval-design` |
| `localstorage` | `dark-mode` |
| `logging` | `observability-design` |
| `lucide` | `vue-dynamic-icons` |
| `make` | `makefile` |
| `market` | `adversarial-check`, `competitive-analysis`, `customer-discovery`, `defensibility`, `go-to-market`, `idea-audit`, `idea-discovery`, `monetization-design`, `new-project`, `pitch-deck`, `pmf-diagnostics`, `product-roadmap`, `solo-founder`, `startup-lifecycle` |
| `matchmedia` | `dark-mode` |
| `materials` | `scene-conventions` |
| `mcp` | `ai-agents`, `build-loop`, `figma-mcp-core`, `mcp-advisor`, `mcp-blender` |
| `media` | `medialibrary` |
| `merge` | `resolving-merge-conflicts` |
| `metrics` | `eval-design`, `observability-design` |
| `middleware` | `attribute-authorization` |
| `migrations` | `database`, `testing-safety-report` |
| `ml` | `ml-project-structure` |
| `mobile` | `figma-to-flutter` |
| `monetization` | `go-to-market`, `monetization-design`, `pitch-deck`, `unit-economics` |
| `monitoring` | `capacity-planning`, `health-checks`, `runbook` |
| `monorepo` | `package-contribution-protocol` |
| `multi-config` | `vite-multi-build` |
| `multi-tenant` | `config-driven-abstraction` |
| `mutation` | `mutation-testing` |
| `mutators` | `eloquent-accessors` |
| `naive-ui` | `naive-ui-theming` |
| `namespace` | `namespace-refactor-safety` |
| `naming` | `naming-conventions`, `php-naming-conventions`, `scene-conventions` |
| `navigation` | `ecosystem-map`, `packages-stack`, `project-map` |
| `navigation-guards` | `vue-router-best-practices` |
| `node` | `node-pnpm-preflight` |
| `null-safety` | `dart-package-development` |
| `nuxt` | `vueuse-functions` |
| `nwidart` | `modular-architecture` |
| `observability` | `capacity-planning`, `health-checks`, `observability-design` |
| `onboarding` | `mcp-advisor` |
| `ops` | `capacity-planning`, `incident-response`, `oncall-rotation`, `postmortem`, `runbook` |
| `orchestration` | `ai-agents`, `anti-drift`, `complex-task-orchestrator`, `laravel-subagents`, `mcp-blender`, `tech-lead` |
| `oss` | `dependency-audit`, `dx-design`, `github-flow`, `open-source-maintainer`, `oss-development`, `oss-governance`, `release-engineering` |
| `ousterhout` | `codebase-design` |
| `outbox` | `transactional-outbox-relay` |
| `owasp` | `security-design` |
| `package` | `dart-package-development`, `package-contribution-protocol` |
| `package-dev` | `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages` |
| `pagination` | `cursor-pagination-design` |
| `parametric` | `build-loop`, `config-conventions`, `parametric-config`, `scene-conventions` |
| `parenting` | `scene-conventions` |
| `patterns` | `eloquent-accessors`, `enum-attributes`, `laravel`, `php-patterns`, `vue-composition-api` |
| `pennant` | `pennant-development` |
| `performance` | `diagnosing-bugs` |
| `permissions` | `attribute-authorization`, `azguard`, `laravel-permissions` |
| `perplexity` | `query-craft` |
| `persona` | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| `pest` | `test-strategy` |
| `php` | `attribute-authorization`, `azguard`, `botkit`, `code-style-spatie`, `config-driven-abstraction`, `cursor-pagination-design`, `database`, `dependency-audit`, `dependency-injection`, `docker-php`, `eloquent-accessors`, `enum-attributes`, `enum-state-machine`, `filament`, `laravel`, `laravel-best-practices`, `laravel-broadcasting`, `laravel-data`, `laravel-dusk`, `laravel-package-compatibility`, `laravel-package-docs`, `laravel-package-expressive`, `laravel-package-generate-skill`, `laravel-package-release`, `laravel-package-scaffold`, `laravel-package-service-provider`, `laravel-package-testing`, `laravel-packages`, `laravel-permissions`, `laravel-security-audit`, `laravel-structure`, `laravel-testing`, `medialibrary`, `modular-architecture`, `mutation-testing`, `named-arguments`, `namespace-refactor-safety`, `pao`, `pennant-development`, `php-naming-conventions`, `php-patterns`, `php-upgrade-checklist`, `production-readiness-checklist`, `repositories`, `spatie-settings`, `static-analysis`, `test-isolation-guard`, `transactional-outbox-relay` |
| `phpstan` | `php-upgrade-checklist` |
| `pinia` | `pinia-stores`, `vue-testing-best-practices` |
| `plan` | `artifact-review` |
| `planning` | `to-issues`, `verify-claims` |
| `plans` | `ecosystem-map` |
| `playwright` | `playwright-e2e` |
| `pnpm` | `node-pnpm-preflight` |
| `postgres` | `db-test-preflight`, `docker-postgres` |
| `preflight` | `db-test-preflight`, `node-pnpm-preflight` |
| `prettier` | `eslint-flat-config`, `js-code-style`, `tailwind-conventions` |
| `privacy` | `legal-compliance`, `security-design` |
| `production` | `production-readiness-checklist` |
| `prompt-engineering` | `ai-agents` |
| `pub` | `dart-package-development` |
| `pusher` | `laravel-echo-client` |
| `python` | `mcp-blender`, `ml-project-structure`, `parametric-config`, `venv-dependencies`, `version-gotchas` |
| `quality` | `artifact-review`, `code-review`, `code-simplifier`, `mutation-testing`, `playwright-e2e`, `production-readiness-checklist`, `refactoring-plan`, `static-analysis`, `tech-debt-audit`, `test-strategy`, `testing-safety-report`, `venv-dependencies` |
| `query` | `query-craft` |
| `queue` | `docker-services`, `transactional-outbox-relay` |
| `rag` | `ai-agents`, `query-craft`, `verify-claims` |
| `rbac` | `attribute-authorization`, `azguard`, `laravel-permissions`, `security-design` |
| `readability` | `named-arguments`, `naming-conventions`, `php-naming-conventions` |
| `readiness` | `health-checks` |
| `realtime` | `laravel-broadcasting`, `laravel-echo-client`, `voice-ai` |
| `rebase` | `resolving-merge-conflicts` |
| `rector` | `php-upgrade-checklist` |
| `red-green-refactor` | `tdd-discipline` |
| `refactor` | `code-simplifier`, `namespace-refactor-safety`, `refactoring-plan`, `tech-debt-audit`, `testing-safety-report` |
| `refactoring` | `code-simplifier`, `refactoring-plan` |
| `reflection` | `attribute-authorization`, `enum-attributes`, `postmortem` |
| `refreshdatabase` | `test-isolation-guard` |
| `registry` | `config-driven-abstraction` |
| `regulatory` | `legal-compliance` |
| `reka-ui` | `reka-ui-cva` |
| `release` | `ci-cd`, `github-flow`, `model-verification`, `open-source-maintainer`, `release-engineering` |
| `reliability` | `production-readiness-checklist`, `transactional-outbox-relay` |
| `reporting` | `testing-safety-report` |
| `repository` | `repositories` |
| `requirements` | `brd`, `business-process`, `grill-with-docs`, `idea-discovery`, `new-project`, `prd-from-brd`, `product-roadmap`, `requirement-critic`, `spec-interview`, `startup-lifecycle`, `task-brief-template` |
| `research` | `query-craft`, `verify-claims` |
| `rest` | `api-design` |
| `reuse` | `axioma-stack`, `ecosystem-reuse-gate` |
| `reverb` | `laravel-broadcasting`, `laravel-echo-client` |
| `review` | `artifact-review`, `code-review`, `gh-review`, `implement`, `open-source-maintainer`, `production-readiness-checklist`, `tech-lead` |
| `role` | `open-source-maintainer`, `solo-founder`, `startup-cto`, `tech-lead` |
| `router` | `docker` |
| `routes` | `wayfinder` |
| `routing` | `project-map`, `vue-router-best-practices` |
| `rules` | `model-rules` |
| `runbook` | `observability-design` |
| `russian` | `writing-style` |
| `russian-stack` | `voice-ai` |
| `safety` | `git-safety`, `namespace-refactor-safety`, `shell`, `test-isolation-guard`, `testing-safety-report` |
| `scalability` | `architecture` |
| `scene` | `scene-conventions` |
| `schema` | `data-schema` |
| `screenshot` | `mcp-blender` |
| `sdk` | `dart-package-development` |
| `seam` | `codebase-design` |
| `search` | `query-craft` |
| `security` | `agent-design`, `ci-cd`, `dependency-audit`, `laravel-security-audit`, `oss-governance`, `risk-assessment`, `security-design` |
| `semver` | `github-flow`, `package-contribution-protocol`, `release-engineering` |
| `settings` | `spatie-settings` |
| `severity` | `artifact-review` |
| `shell` | `shell` |
| `skills` | `laravel-packages`, `skills-ssot` |
| `sla` | `build-loop`, `capacity-planning`, `config-conventions`, `incident-response`, `model-verification`, `oncall-rotation`, `parametric-config`, `threading` |
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
| `stt` | `voice-ai` |
| `style` | `compact-responses`, `writing-style` |
| `stylistic` | `eslint-flat-config` |
| `subagents` | `ai-agents` |
| `tailwind` | `dark-mode`, `figma-to-vue`, `naive-ui-theming`, `reka-ui-cva`, `tailwind-conventions`, `vite-multi-build` |
| `tailwindcss-v4` | `figma-to-vue`, `tailwind-conventions` |
| `taxonomy` | `artifact-review` |
| `tdd` | `implement`, `tdd-discipline` |
| `tech-radar` | `axioma-stack` |
| `template` | `brd`, `model-rules`, `prd-from-brd`, `runbook`, `task-brief-template` |
| `term-index` | `axioma-glossary` |
| `testability` | `codebase-design` |
| `testing` | `dart-package-development`, `db-test-preflight`, `diagnosing-bugs`, `docker-postgres`, `eval-design`, `laravel-testing`, `mutation-testing`, `pao`, `playwright-e2e`, `tdd-discipline`, `test-isolation-guard`, `test-strategy`, `testing-safety-report`, `vitest`, `vue-testing-best-practices` |
| `tests` | `writing-style` |
| `theme` | `dark-mode` |
| `theming` | `figma-to-flutter`, `naive-ui-theming` |
| `threading` | `threading` |
| `threat-modeling` | `security-design` |
| `tokens` | `compact-responses`, `context-economy`, `gh-review`, `pao`, `session-handoff` |
| `tooling` | `eslint-flat-config`, `mcp-advisor`, `venv-dependencies` |
| `tracing` | `observability-design` |
| `trade-off` | `tech-stack-selection` |
| `transitions` | `enum-state-machine` |
| `triage` | `issue-triage`, `open-source-maintainer` |
| `tts` | `voice-ai` |
| `type-sync` | `backend-type-sync` |
| `types` | `backend-type-sync` |
| `typescript` | `backend-type-sync`, `enum-attributes`, `eslint-flat-config`, `js-code-style`, `playwright-e2e`, `vue-dynamic-icons`, `vue-router-best-practices`, `wayfinder` |
| `ubiquitous-language` | `domain-modeling` |
| `ui` | `figma-mcp-core`, `filament`, `naive-ui-theming`, `reka-ui-cva` |
| `units` | `parametric-config` |
| `upgrade` | `php-upgrade-checklist` |
| `uploads` | `filepond-upload`, `medialibrary` |
| `vad` | `voice-ai` |
| `validation` | `adversarial-check`, `agent-design`, `code-review`, `code-simplifier`, `cross-layer-change-checklist`, `customer-discovery`, `defensibility`, `eval-design`, `idea-audit`, `laravel-data`, `pmf-diagnostics`, `refactoring-plan`, `requirement-critic`, `risk-assessment`, `solo-founder`, `startup-lifecycle`, `tech-debt-audit`, `test-strategy` |
| `variants` | `reka-ui-cva` |
| `vendor-vs-build` | `ecosystem-reuse-gate` |
| `venv` | `venv-dependencies` |
| `verification` | `model-verification`, `testing-safety-report`, `verify-claims` |
| `version` | `php-upgrade-checklist`, `version-gotchas` |
| `vertical-slices` | `tdd-discipline`, `to-issues` |
| `viewport` | `mcp-blender` |
| `vite` | `docker-vite`, `vite-module-loader`, `vite-multi-build` |
| `vitest` | `vitest`, `vue-testing-best-practices` |
| `voice` | `voice-ai` |
| `vue` | `dark-mode`, `eslint-flat-config`, `figma-to-vue`, `filepond-upload`, `inertia-vue`, `js-code-style`, `laravel-echo-client`, `naive-ui-theming`, `pinia-stores`, `reka-ui-cva`, `tailwind-conventions`, `vite-module-loader`, `vitest`, `vue-composition-api`, `vue-dynamic-icons`, `vue-router-best-practices`, `vue-testing-best-practices`, `vueuse-functions` |
| `vue-router` | `vue-router-best-practices` |
| `vue-test-utils` | `vue-testing-best-practices` |
| `vueuse` | `vueuse-functions` |
| `wayfinder` | `wayfinder` |
| `webrtc` | `voice-ai` |
| `websocket` | `docker-services` |
| `websockets` | `laravel-broadcasting`, `laravel-echo-client` |
| `workflow` | `anti-drift`, `build-loop`, `business-process`, `code-review`, `compact-responses`, `complex-task-orchestrator`, `context-economy`, `cross-layer-change-checklist`, `enum-state-machine`, `implement`, `incident-response`, `laravel-subagents`, `postmortem`, `refactoring-plan`, `session-handoff`, `shell`, `skills-ssot`, `spec-interview`, `task-brief-template`, `tech-debt-audit`, `tech-lead` |
| `writing` | `writing-style` |
