# Trust Matrix Laravel Boost

**Politics.** Laravel Boost — trusted source of version-specific skills and guidelines: it comes with packages, knows installed versions (`boost:update`) and is updated along with the ecosystem. Our registry **is not a duplicate** Boost, a **complements** its architecture, design conventions and practices, which Boost no. Version-specific theme → Boost; architecture/processes/infrastructure → swissknifeman.

Revision date: 2026-06-15.

> **Next step.** There are projects where Boost want to leave **just like MCP**, and distribution
> local `.ai/` content on providers (CLAUDE.md/AGENTS.md/Cursor) take to skiller — see
> [Local distribution `.ai/` to providers (dev-plan)](./multi-provider-distribution).

**Where does he live? Boost:**

- Repository: https://github.com/laravel/boost — skills/guidelines in [`/.ai/`](https://github.com/laravel/boost/tree/main/.ai) (`*/core.blade.php` and `*/skill/*/SKILL.blade.php` by package and version); documentation: https://laravel.com/docs/boost
- In the installed project: `vendor/laravel/boost/.ai/` (are updated from composer-package); selection - `boost.json` project; render in CLAUDE.md/AGENTS.md — `php artisan boost:update`
- Third-party guidelines come from the packages themselves via `boost.json::packages` (filament/filament, spatie/laravel-medialibrary, …)
- Source card in the registry: [references/laravel-boost.md](https://github.com/academici/swissknifeman/blob/main/references/laravel-boost.md)

## Table 1. Trusted Boost-skills/guidelines

| Boost-skill / guideline | What is this | Status |
|:---|:---|:---|
| laravel core + 11/12 | basic and versioned rules of the framework | trusted |
| php/8.2–8.5 | version features and rules PHP | trusted |
| pest 3/4 (core + skill) | syntax and techniques Pest by version | trusted |
| inertia-laravel + inertia-vue 1/2 | server and Vue-part Inertia by version | trusted |
| inertia-react / inertia-svelte | React/Svelte-adapters Inertia | trusted, are not used in our stacks |
| livewire 2/3/4 | version rules Livewire | trusted |
| tailwindcss 3/4 | version rules Tailwind CSS | trusted |
| wayfinder | generation of typed routes | trusted |
| volt | single-file Livewire-components | trusted |
| folio | file-based routing | trusted |
| pennant | feature flags | trusted |
| fluxui free/pro | UI-components Flux | trusted |
| mcp | Laravel MCP (servers, tools) | trusted |
| herd | local environment Herd | trusted |
| sail | Docker-environment Sail | trusted |
| pint | code style fixer | trusted |
| foundation/enforce-tests | change test requirement | trusted |
| third-party: filament/filament | guidelines Filament from package | trusted |
| third-party: spatie/laravel-medialibrary | guidelines medialibrary from package | trusted |
| third-party: spatie/guidelines-skills | code guidelines Spatie from package | trusted |

## Table 2. Our skills × Boost

### use-boost — our duplicates have been removed from the registry (2026-06-12)

| Was our skill | Use it instead |
|:---|:---|
| `php/livewire` | Boost livewire 2/3/4 |
| `frontend/tailwindcss` | Boost tailwindcss 3/4 |
| `general/mcp-development` | Boost mcp |

### complementary — Boost gives a versioned base, our skill gives a delta

| Our skill | Boost-source | Our delta |
|:---|:---|:---|
| `php/laravel-best-practices` | laravel-best-practices (Boost) | complete summary for projects **without** Boost; with Boost — use Boost-version |
| `frontend-backend/inertia-vue` | inertia-vue-development | layered organization `resources/js/`, design file placement conventions |
| `frontend-wayfinder/wayfinder` | wayfinder-development | ESLint-import boundaries, layer actions/composables |
| `laravel-filament/filament` | filament/filament (third-party) | resource structure, admin panel design patterns |
| `laravel-extras/medialibrary` | spatie/laravel-medialibrary (third-party) | self-contained option for projects without Boost |
| `laravel-testing/laravel-testing` | pest-testing | test database isolation, environment detection, coverage gate |
| `frontend-tailwind/tailwind-conventions` | tailwindcss 3/4 | v4 CSS-first: tokens `@theme`, dark theme `.dark`+`useAppearance`, `cn()` (clsx+tailwind-merge), class sorting Prettier, indentation discipline |
| `laravel-data-layer/laravel-data` | spatie/laravel-data (third-party) | author's pattern on top of the versioned one API: nested `DataCollection`, casts, `from(request)`, return to Inertia/API, `#[TypeScript]` |
| `laravel-extras/spatie-settings` | spatie/laravel-settings (third-party) | is self-sufficient for projects without Boost; form binding (Filament) to settings class |
| `laravel-livewire/livewire-blade-attributes` | livewire 2/3/4 | delta gochises: attributes Blade-components (no `@if`/`@js()` in the attribute list, `ComponentAttributeBag`) |

### ours-only — analogue in Boost no

`php/laravel-structure`, `php/repositories`, `php/dependency-injection`, `azguard/azguard`, `php/database`, `laravel-architecture/enum-attributes`, `laravel-data-layer/laravel-broadcasting`, `laravel-testing/laravel-dusk`, `php/code-style-spatie`, `php/static-analysis`, `php/laravel`, `laravel-auth/laravel-permissions`, `php/php-patterns`, `laravel-architecture/modular-architecture`, `botkit/botkit`, all `php/laravel-package-*` (scaffold, testing, docs, release, service-provider, compatibility, generate-skill, expressive) and `php-packages/laravel-packages`, `laravel-testing/test-isolation-guard`, `laravel-auth/attribute-authorization`, `laravel-testing/health-checks`, all `devops/docker-*` (and `devops/ci-cd`, `devops/gitops`, `devops/makefile`, `devops/node-pnpm-preflight`, `devops/db-test-preflight`), `frontend-vite/vite-multi-build`, `frontend-vite/vite-module-loader`, `frontend-vue/vitest`, `frontend-linting/js-code-style`, `frontend-vue/vue-composition-api`, `frontend-backend/backend-type-sync`, `frontend-linting/eslint-flat-config`, `frontend-reka/reka-ui-cva`, `frontend-tailwind/dark-mode`, `frontend-naive-ui/naive-ui-theming`, `frontend-backend/laravel-echo-client`, `frontend/filepond-upload`, `frontend-vue/vue-dynamic-icons`, `frontend-vue/pinia-stores`, and all not-Laravel entire buckets: `architect/*`, `blender/*`, `founder/*`, `general/*`, `imported/*`, `operator/*`, `oss-dev/*`, `pm/*`, `python/*`, `quality/*`, `roles/*`.

## How to use

At startup Laravel-project with Boost:

1. Install Boost-skills as is (`boost.json`, `php artisan boost:update`) — they are version specific and priority.
2. Ours **complementary**-connect skills for the sake of their delta (structure, boundaries, database isolation, etc.) — each contains a border line «**Laravel Boost**: …» in section «Context», explaining the division.
3. **use-boost**-skills are not installed - they have already been deleted from the registry.
4. In projects **without** Boost complementary-skills work independently.

Source priorities and task routing - see. [routing](/routing).
