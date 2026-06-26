---
name: vite-multi-build
bucket: frontend-vite
version: 0.1.0
description: "Two independent Vite builds in one Laravel project: main app + Filament admin, with separate Vite/Tailwind configs, hotfiles and build dirs."
risk: write
persona: oss-dev
tags: [vite, laravel, filament, tailwind, build, multi-config, frontend]
requires: [vite-module-loader]
produces_for: []
outputs: []
snippets: [vite.config.js, vite.admin.config.js, tailwind.config.js, tailwind-admin.config.js, package-scripts.json]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Vite multi-build (app + Filament admin)

One Laravel project, two isolated frontends: main Inertia/Vue app + Filament admin. Filament has a rigid Tailwind preset; merging it with the app theme breaks both. Solution: fully separate Vite+Tailwind config pairs, separate build dirs and hotfiles.

Apply when: adding Filament with a custom theme to a Laravel project, OR any second isolated frontend bundle (widget, embed, landing).

## Algorithm

1. **Main build** — `vite.config.js`: inputs `resources/js/app.ts` + sass/tailwind css; default output `public/build`, hotfile `public/hot`. Plugins: `wayfinder()`, `laravel()`, `vue()`, `tailwindcss()`. Read `APP_URL` and `VITE_PORT` via `loadEnv(mode, process.cwd(), '')` (CORS/HMR in Docker).
2. **Admin build** — `vite.admin.config.js`: single input `resources/filament/admin/theme.sass`; in `laravel()` set `buildDirectory: 'filament'` (output `public/filament`) and `hotFile: 'public/filament.hot'` — else both builds overwrite the same hotfile.
3. **Two Tailwind configs**: `tailwind.config.js` — app custom theme (content: blade + vue, own fonts/colors, plugin forms); `tailwind-admin.config.js` — `presets: [filament preset]`, content only Filament files. In admin vite config set `tailwindcss({ config: './tailwind-admin.config.js' })`.
4. **package.json scripts**: `dev`/`build` → main; `dev:admin`/`build:admin` → with `--config vite.admin.config.js`. CI/deploy runs both build commands.
5. **Blade side**: main — plain `@vite([...])`; admin registers theme via Filament (`->viteTheme('resources/filament/admin/theme.sass', 'filament')` or equivalent) specifying buildDirectory.

## Do NOT apply when

- Second bundle needs no style isolation (shared theme) — just add an input to the existing config.
- SPA without Laravel — hotfile/buildDirectory pattern is laravel-vite-plugin specific.

## Which snippet to open

| Situation | File |
|:---|:---|
| Main build: inputs, loadEnv, HMR/CORS for Docker, aliases | `snippets/vite.config.js` |
| Admin build: hotFile, buildDirectory, separate tailwind config | `snippets/vite.admin.config.js` |
| App Tailwind theme | `snippets/tailwind.config.js` |
| Tailwind with Filament preset for admin | `snippets/tailwind-admin.config.js` |
| dev/build scripts for both builds | `snippets/package-scripts.json` |

## Quality checklist

- [ ] Admin build has own `hotFile` (`public/filament.hot`) and `buildDirectory` (`public/filament`) — builds don't overwrite each other
- [ ] Tailwind configs don't overlap in `content` (app theme doesn't scan Filament and vice versa)
- [ ] Admin vite config explicitly points to `tailwind-admin.config.js`
- [ ] `APP_URL`/`VITE_PORT` read via `loadEnv`, not hardcoded
- [ ] package.json has all four scripts: `dev`, `build`, `dev:admin`, `build:admin`
- [ ] CI/deploy runs both build commands; `public/filament` lands in the artifact

## Links

- https://laravel.com/docs/vite
- https://filamentphp.com/docs (custom themes / vite theme section)
- Related skills: `frontend/vite-module-loader` (base Vite config: aliases, chunks, laravel-vite-plugin), `frontend/wayfinder` (plugin in main build), `frontend/tailwind-conventions` (app theme on Tailwind v4), `devops/docker-vite` (Vite dev server in compose, HMR in Docker); Tailwind version guidelines — Boost skill `tailwindcss` (v3/v4)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 7a5a0a618003380be54eecb37e57473b52793a505cbe4e261f35a0ffdd03ee12 -->
