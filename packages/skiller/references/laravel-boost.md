# laravel/boost

- **URL:** https://github.com/laravel/boost
- **Packagist:** https://packagist.org/packages/laravel/boost
- **Documentation:** https://laravel.com/docs/boost
- **Status:** trusted (versioned - trusted locally; clean generic — extract pointwise)
- **Checked:** 2026-06-13

**Upstream-tracking:**
- `skills/php/laravel-best-practices/upstream.json` (strategy=notify, 21 file:
  SKILL.md + 20 rules `rules/*.md` ↔ ours `references/*.md`).
- `skills/php/pennant-development/upstream.json` (strategy=notify, SKILL.md) —
  extracted to the registry (see «What's retrieved»).

CI/`./scripts/update-upstreams.sh --check` will report when Boost will change
monitored files; merge - manually.

Official package Laravel for AI-agents: supplies version-specific
skills/guidelines, MCP-server and root generator CLAUDE.md/AGENTS.md.

## Where are the skills physically located? Boost

- **In the package repository:** [`/.ai/`](https://github.com/laravel/boost/tree/main/.ai) —
  guidelines (`*/core.blade.php` by package and version) and skills (`*/skill/*/SKILL.blade.php`).
- **In the installed project:** `vendor/laravel/boost/.ai/` (are updated from composer-package);
  selection - in `boost.json` project (arrays `skills`, `packages`); render to root
  files - `php artisan boost:update`.
- **Third-party guidelines** come from the packages themselves via `boost.json::packages`
  (for example `filament/filament`, `spatie/laravel-medialibrary`, `spatie/guidelines-skills`).

## What we extract and what we don’t (criterion)

Skill extraction Boost to the registry is only valid if it simultaneously:

1. **Static markdown without Blade** — `SKILL.md`, and not `SKILL.blade.php`; without
   directives `@php`, `@if`, `@foreach`, `@boostsnippet`, `{{ $assist->… }}`.
   Blade-skills are rendered only through `boost:update` in the context of the project -
   they cannot be taken as statics (import a broken template from
   unrendered `{{ … }}`).
2. **Version-stable** — without version-branches in `.ai/<pkg>/<N>/` (stable
   API without forking according to package versions).
3. **Generic and complementary** — no intersection with an existing registry skill
   (Step 0 skill-authoring) and there is no rule conflict.

If at least one point is not completed - **not extractable**, policy in effect
trust (below).

### What's retrieved (2026-06-13)

- `pennant-development` → `skills/php/pennant-development/` (static `.md`,
  stable API, there was no analogue in the registry). upstream.json strategy=notify.

### What we DO NOT extract

- **Versional** (`laravel/11|12`, `php/8.x`, `pest/3|4`, `inertia-*/1|2`,
  `livewire/2|3|4`, `tailwindcss/3|4`) — renders to actual versions
  packages; import would freeze the version and create a third copy of the truth
  (vendor → registry → project).
- **Blade-templates** (`folio-routing`, `volt-development`, `mcp-development`,
  guidelines `foundation`/`php-core`/`enforce-tests` `*.blade.php`) — require
  render-context Boost. Manual de-Blade-recycling is possible, but this is already
  authoring a new skill, not extracting it; made separately upon request.
- **Outside our stacks** (`fluxui-*` — paid UI Flux).

## Trust Policy (for the unbearable)

B Boost-projects are version-specific and Blade-related topics give away Boost,
our registry **complements** its architecture, structure and practices. Conflict
rules decided by priority: project > Boost > registry.

## Registry Links

- Confidence matrix and verdicts on our skills - [docs/boost-compatibility.md](../docs/boost-compatibility.md)
- Source priority (project > Boost > registry) — [docs/routing.md](../docs/routing.md)
- Hub integration with `boost:update` — `scripts/generate-hub.sh` (mode Boost writes
  `.ai/guidelines/swissknifeman-hub.md`)
- Device SSOT around Boost — skill `general/skills-ssot`
- Deleted takes (2026-06-12): `php/livewire`, `frontend/tailwindcss`,
  `general/mcp-development`; marked complementary: `php/laravel-best-practices`,
  `frontend/inertia-vue`, `frontend/wayfinder`, `php/filament`, `php/medialibrary`,
  `php/laravel-testing`
- Extracted to registry (2026-06-13): `php/pennant-development` (static `.md`, notify)
