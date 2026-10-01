# Presets: named skill clusters

Large buckets (`php` — dozens of skills), and a project usually needs a subset: one -
Filament-admin, the other is a package, the third is pure API. **Preset** — named group
skills referred to by the project `.swissknifeman/config.json`, not to list
hand skills.

Presets - concept **vendor-channel** (`skiller sync`): they expand in per-skill set.
B `connect` the bucket is atomic, so presets have no effect there.

## Format

`presets/<name>.json` in the registry (next to `profiles/`):

```json
{
  "name": "laravel-admin",
  "description": "Admin on Filament: resources/panels, rights, authorization-attributes, media, settings",
  "extends": ["laravel-core"],
  "include": ["laravel-filament/filament", "laravel-auth/laravel-permissions", "laravel-auth/attribute-authorization",
              "laravel-extras/medialibrary", "laravel-extras/spatie-settings"]
}
```

- `name` — kebab-case, is the same as the file name.
- `extends` — list of parent presets (are expanded recursively, loops are not allowed).
- `include` — skills by `"bucket/rel"` (exactly) or by `"name"`.
- `buckets` — (opt.) entire buckets inside a preset.

## How to use

In the design `.swissknifeman/config.json`:

```json
{ "mode": "vendor", "presets": ["laravel-admin"], "exclude": ["laravel-extras/medialibrary"] }
```

Final set = **(presets ∪ buckets ∪ include) − exclude**. Presets are expanded to
`buckets`/`include` BEFORE subtraction, then `skiller sync` reaches `requires` and writes
`skills-lock.json`. `exclude` hits both the preset and the dependency (with warning).

```bash
skiller sync --dry-run    # plan: what will unfold from the preset
skiller sync              # apply → .claude/skills/ + skills-lock.json
```

## Available presets

> **PHP and Frontend are divided into thin buckets.** PHP: core `php` + `laravel-{testing,filament,livewire,
> data-layer,auth,architecture,extras}` (+ `php-packages`). Frontend: core `frontend` + `frontend-{vue,
> nuxt,tailwind,naive-ui,reka,vite,linting,animations,figma,wayfinder,backend}`. For **one** areas
> take **bucket** (`buckets: ["laravel-filament"]`). Presets below - **end-to-end stacks**, components
> several buckets (often php + frontend).

| Area | Preset | Composition (builds buckets) |
|:--|:--|:--|
| php-stack | `laravel-admin` | php + laravel-filament + laravel-auth + laravel-extras |
| php-stack | `laravel-enterprise` | php + laravel-architecture + laravel-auth |
| php+front | `laravel-inertia` | php + laravel-data-layer + frontend-backend + frontend-wayfinder |
| php+front | `laravel-livewire-stack` | php + laravel-livewire + laravel-data-layer |
| frontend | `vue-spa` | frontend + frontend-vue + frontend-vite + frontend-linting + frontend-tailwind |
| front+arch | `figma-to-frontend` | frontend-figma + architect/figma-mcp-core |
| architect | `agents-eval` · `api-data` · `system-design` · `compliance-security` | agents/rating · API/data · arch./stack/observability · security/compliance |
| pm | `pm-discovery` · `pm-strategy` · `pm-delivery` · `pm-metrics` | BRD/PMF · GTM/monetization · PRD/roadmap · unit-economics |
| general | `agent-context` · `agent-tasks` · `project-conventions` | context-discipline · task setting · project conventions |
| quality | `code-quality` · `testing-quality` | review/refactoring/debt · strategy/mutations/E2E |

## Add preset

1. `presets/<name>.json` (`name` = file, non-empty `description`, valid `extends`/`include`/`buckets`).
2. `bash scripts/validate.sh` — will check that tokens resolve and there are no loops `extends`.
3. `skiller registry` (if indexed) → PR.

See also [Vendor-mode](./vendor-mode) (config and flow sync) and [Profiles](./profiles)
(automatic selection of buckets by project type).
