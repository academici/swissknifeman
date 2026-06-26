---
name: dark-mode
bucket: frontend-tailwind
version: 0.1.0
description: "Dark theme light|dark|system on Vue 3: useDarkMode composable (matchMedia prefers-color-scheme, localStorage + cookie for SSR, toggle .dark class on documentElement, change listener for system), pre-mount init without theme flash, mini toggle. Activate when adding theme switching, fighting light-theme flash (FOUC), syncing theme with system, or restoring theme under SSR."
risk: write
persona: oss-dev
tags: [dark-mode, theme, vue, composable, ssr, tailwind, matchmedia, localstorage]
requires: [tailwind-conventions]
produces_for: []
outputs: []
snippets: [useDarkMode.ts, bootstrap-init.ts, no-flash-init.html, ThemeToggle.vue]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Dark theme (light | dark | system)

Three states: `light`, `dark`, `system` (follow OS). Dark = `.dark` class on root `<html>` (`document.documentElement`); Tailwind/tokens react to it (see `frontend-tailwind/tailwind-conventions`). User choice persists across reload.

Activate when:
- adding a theme toggle / "appearance" setting;
- fighting light-theme flash on load (FOUC);
- theme must follow system and react to live OS theme change;
- setting up theme restore under SSR (correct class from first byte);
- replacing hand-rolled `matchMedia('(prefers-color-scheme: dark)')` + manual `classList.add('dark')`.

Two layers, both mandatory:
1. Runtime (Vue) — composable: reactive state, switching, persist to `localStorage` + `cookie`, subscribe to system theme.
2. Boot (pre-mount) — synchronous `.dark` init BEFORE first render. Client: call `initializeTheme()` in entry point. SSR: short inline script in page template reading cookie/system. Without layer 2 the composable is useless — browser already painted the light frame by Vue mount.

## State model

| Concept | Type / value | Lives in |
|:---|:---|:---|
| `Appearance` | `'light' \| 'dark' \| 'system'` | user choice, stored |
| `ResolvedAppearance` | `'light' \| 'dark'` | what's actually on screen (`system` → resolved via matchMedia) |
| `.dark` class | present ⟺ resolved === `'dark'` | `document.documentElement` |
| Storage key | one string name, e.g. `'appearance'` | `localStorage` **and** `cookie` |

Rules:
- Never store `ResolvedAppearance`. Store only `Appearance` incl. literal `'system'` — else "follow system" intent is lost.
- `localStorage` = client source of truth. `cookie` = server copy (localStorage unavailable to server). Write both on every change, same value.
- Module must be SSR-safe: every `window`/`document`/`localStorage` access guarded by `typeof window === 'undefined'` (or `document`) — else SSR build fails.

## Algorithm

1. Define types `Appearance`, `ResolvedAppearance`. State `appearance` = module-level `ref<Appearance>('system')`, default `'system'` (new user follows OS).
2. `updateTheme(value)` — pure class-application, no storage side effect:
   - SSR guard first (`typeof window === 'undefined' → return`);
   - if `value === 'system'` — resolve via `matchMedia('(prefers-color-scheme: dark)').matches`;
   - `document.documentElement.classList.toggle('dark', isDark)` — `toggle` with 2nd arg, not add/remove pair.
3. Persistence — on every change write both stores, same value:
   - `localStorage.setItem(KEY, value)` (client);
   - cookie `KEY=value;path=/;max-age=<year>;SameSite=Lax` (server). Both under SSR guard.
4. `initializeTheme()` (client boot, called from entry point BEFORE/near mount):
   - read saved value from `localStorage`, default `'system'`;
   - `updateTheme(saved)` — set class immediately;
   - subscribe: `matchMedia(...).addEventListener('change', handler)`, `handler` re-reads saved value and calls `updateTheme` — OS change affects screen only while `'system'` selected.
5. `useDarkMode()` (component composable):
   - in `onMounted` sync module `ref` with `localStorage` (for SSR hydration where module init'd on server);
   - `resolvedAppearance` = `computed<ResolvedAppearance>`: for `'system'` return `prefersDark() ? 'dark' : 'light'`, else the value itself;
   - `updateAppearance(value)`: write `ref`, persist to localStorage + cookie (step 3), call `updateTheme(value)`;
   - return `{ appearance, resolvedAppearance, updateAppearance }`.
6. Boot without flash — critical, see below. Client: `initializeTheme()` in entry point pre-mount. SSR: inline script in `<head>`.
7. Markup reacts to `.dark` via semantic tokens / Tailwind `dark:*` — that's `frontend-tailwind/tailwind-conventions`; here we only toggle the class.

## No-flash init (FOUC)

Flash = browser paints a light frame before JS adds `.dark`. Fix: set class synchronously, as early as possible, before first render.

Client (SPA, no SSR): call `initializeTheme()` in entry point (`app.ts`) before/right around mount — `updateTheme` runs before Vue paints content. Enough for pure client render: empty `#app` doesn't flash light.

SSR: server must emit correct class in HTML, else flash returns between page delivery and JS start. Two paired techniques:
- server puts saved `Appearance` from cookie into page (Blade/template): `<html class="dark">` immediately if cookie === `dark`;
- if cookie === `system` (or empty), server can't set class — system known only to browser. Then **synchronous inline script** in `<head>` (before bundle and content) reads `matchMedia` and sets `.dark` before first frame. Optional inline `<style>` with `html`/`html.dark` background so even the page background doesn't flash.

Principle: cookie covers explicit `light`/`dark` on server, inline script covers `system` on client pre-mount. Exposed: `app.ts` (client) and template fragment (SSR) — both in snippets.

## Tailwind link

Laravel Boost: versioned dark-theme foundations from the Tailwind/Inertia starter kit (base `useAppearance`, init) come from Boost skills `tailwindcss-development` / `inertia-vue`; here = the authored three-mode composable, no-flash boot, SSR init via cookie. Package: https://github.com/laravel/boost (skills — `vendor/laravel/boost/.ai/`).

This skill owns only the `.dark` class and state. How `.dark` affects colors → `frontend-tailwind/tailwind-conventions`:
- Tailwind v4: `@custom-variant dark (&:is(.dark *));` — `dark:*` utilities/tokens fire on ancestor `.dark`.
- Prefer semantic tokens (var values overridden in `.dark`) over inline `dark:bg-…`.
- Class name (`dark`) and "class on `<html>`" contract — shared by both skills; don't diverge.

## Which snippet to open

| Situation | File |
|:---|:---|
| The composable: types, updateTheme, persist, initializeTheme, useDarkMode | `snippets/useDarkMode.ts` |
| Wire init in entry point (app.ts), client | `snippets/bootstrap-init.ts` |
| Kill SSR flash: class from cookie + inline script in template | `snippets/no-flash-init.html` |
| Ready mini light/dark/system toggle | `snippets/ThemeToggle.vue` |

## Quality checklist

- [ ] State `'light' | 'dark' | 'system'`; default `'system'`; store only choice, not resolved
- [ ] Class set via `documentElement.classList.toggle('dark', isDark)`, not add/remove pair
- [ ] Value written to `localStorage` and `cookie` simultaneously (SameSite=Lax, long max-age)
- [ ] Every `window`/`document`/`localStorage` access under SSR guard — SSR build doesn't fail
- [ ] `initializeTheme()` called in entry point BEFORE mount — no client flash
- [ ] Under SSR class comes from cookie + inline script in `<head>` covers `system` — no server flash
- [ ] `matchMedia change` subscription updates theme only when `system` selected
- [ ] Class name and `.dark`-on-`<html>` contract match `frontend-tailwind/tailwind-conventions`; colors not hardcoded, via tokens/`dark:*`

## Links

- https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme
- https://developer.mozilla.org/en-US/docs/Web/API/Window/matchMedia
- https://vuejs.org/guide/reusability/composables
- Related skills: `frontend-tailwind/tailwind-conventions` (how `.dark` affects colors/tokens), `frontend-backend/inertia-vue` (where the composable lives in layers), `frontend-vue/vue-composition-api` (composable pattern), `frontend-naive-ui/naive-ui-theming` (same `.dark` flag selects Naive `darkTheme`)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 603eefd7d53d415e9dbdee762c75f74383df8837ab75de97bc683e7b44bae70f -->
