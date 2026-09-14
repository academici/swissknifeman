---
name: tailwind-conventions
bucket: frontend-tailwind
version: 0.1.1
description: "Use for Tailwind v4 in Laravel/Vue: CSS-first config, theme tokens, classes, and formatting."
risk: write
persona: oss-dev
tags: [tailwind, tailwindcss-v4, css, vue, laravel, dark-mode, design-tokens, prettier]
requires: []
produces_for: []
outputs: []
snippets: [app.css, cn.ts, .prettierrc]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Tailwind CSS conventions

Tailwind CSS **v4** for Laravel + Vue. v4 config lives in CSS, not `tailwind.config.js`; engine via Vite plugin `@tailwindcss/vite`; tokens/theme via `@theme`, `@source`, `@custom-variant`.

Activate when: editing styles in `*.vue`/`*.blade.php` with Tailwind utilities or `*.css` with `@theme`/`@apply`/`@import 'tailwindcss'`; configuring Tailwind build (vite.config with `@tailwindcss/vite`, `tailwind.config.js` → CSS-first migration, PostCSS); configuring Prettier for Tailwind (class sorting, `tailwindFunctions`); working with dark mode (`.dark` class, `dark:*` utilities, theme-toggle composable); writing conditional/dynamic classes needing `cn()`.

**Laravel Boost**: versioned Tailwind basics in Laravel starters = Boost skill `tailwindcss-development`; here = project v4 conventions, tokens, dark mode, class discipline.

## Algorithm

1. **Detect version.** Open input CSS (`resources/css/app.css`). `@import 'tailwindcss'` → **v4**, CSS-first config, no `tailwind.config.js`. Three `@tailwind base/components/utilities` + `tailwind.config.js` → **v3**. Don't mix; new code → v4.

2. **Config + tokens in CSS (v4).** Edit tokens only in `app.css`; don't create `tailwind.config.js` unless needed (see `snippets/app.css`):
   - `@import 'tailwindcss';` — replaces three v3 `@tailwind` directives;
   - `@source '...';` — extra class-scan paths (replaces `content: [...]`);
   - `@theme { --color-*, --spacing-*, --radius-*, --font-* }` — design tokens; prefixed names generate utilities (`--color-brand` → `bg-brand`/`text-brand`/`border-brand`);
   - `@plugin '@tailwindcss/forms';` — replaces `plugins: [require(...)]`.

3. **Tokens semantic, not raw colors.** Define role tokens (`--color-background`, `--color-foreground`, `--color-primary`, `--color-muted`, `--color-border`…) referencing `:root` CSS vars. In markup use semantic utilities (`bg-background`, `text-muted-foreground`, `border-border`), not `bg-white`/`text-gray-900` directly — else dark mode won't apply.

4. **Dark mode via class, not media-query:**
   - CSS: `@custom-variant dark (&:is(.dark *));` — `dark:*` fires when `.dark` is on any ancestor;
   - set token values twice: light in `:root`, dark in `.dark` (same var names, two palettes; utilities not duplicated);
   - `.dark` on `<html>` set/cleared by composable `useAppearance`;
   - prefer semantic tokens over `dark:` variants in markup; theme switch goes through vars, pointwise `dark:bg-…` only for exceptions.

5. **Conditional/dynamic classes only via `cn()`** (see `snippets/cn.ts`):
   - `cn(...inputs)` = `twMerge(clsx(inputs))`; `clsx` builds classes from strings/objects/arrays, `tailwind-merge` resolves utility conflicts (last wins: `px-2 px-4` → `px-4`);
   - never concatenate classes via manual template strings — Tailwind conflicts won't resolve;
   - for overridable components merge base with `props.class` via `cn('base…', props.class)`.

6. **Prettier auto-sorts classes** (see `snippets/.prettierrc`):
   - `plugins: ["prettier-plugin-tailwindcss"]` — canonical-order sorting;
   - `tailwindFunctions: ["clsx", "cn", "cva", "tv"]` — so classes inside `cn(...)`/`cva(...)` sort too;
   - v4: set `tailwindStylesheet` (path to input CSS with `@theme`), not `tailwindConfig`;
   - Tailwind plugin must be last in `plugins`.

7. **Spacing discipline** (see below): spacing between elements via `gap`/`space-*` on container, not child outer `margin`; single `spacing` scale (token-step multiples), no magic `px` values.

8. **Organize long class lists** (see below): group order, move repeated static classes to `@apply`/component, dynamic → `cn()`.

## Dark mode & useAppearance

`.dark` managed by composable; tokens switch automatically.

- State type: `'light' | 'dark' | 'system'`. `system` reads `matchMedia('(prefers-color-scheme: dark)')`.
- `updateAppearance(value)`: saves choice to `localStorage` (client) + cookie (SSR), then calls `updateTheme(value)`.
- `updateTheme(value)`: set/clear `dark` on `document.documentElement` (`<html>`) — `classList.toggle('dark', isDark)`.
- On `system`: attach `change` listener on media-query so theme follows OS.
- `initializeTheme` called before app mount (SSR: from cookie) to avoid wrong-theme flash.
- In components never touch `document.documentElement.classList` directly — only via `useAppearance().updateAppearance()`. Colors from semantic tokens, so toggling `.dark` repaints UI without per-class `dark:` utilities.

## Spacing discipline

- **Spacing between elements on container, not children.** Inside flex/grid use `gap-*` (`flex gap-4`, `grid gap-6`); vertical stacks without flex → `space-y-*`. Avoid child outer `margin` (`mt-*`/`mb-*`) — causes collapse and order dependency.
- **Single spacing scale.** Only token-scale values (`p-2`, `p-4`, `gap-6`…). Arbitrary `p-[13px]`/`mt-[7px]` only as deliberate exception; repeated value → `--spacing-*` token.
- **Padding on container, gap for gaps.** Section `padding` makes the outer frame, `gap` the inter-element distance. Don't conflate both roles into `margin`.

## Organizing long class lists

- **Group order** (Prettier plugin canonicalizes automatically — keep logical order while writing): layout/positioning → display/flex/grid → box (w/h/p/m/gap) → typography → visual (bg/border/rounded/shadow) → states (`hover:`/`focus:`/`dark:`) → animations.
- **Repeated static set → component or `@apply`.** If the same long set is copied in 3+ places — extract to a Vue component (button, card) or `@layer components { .btn { @apply … } }`. Don't proliferate copies.
- **Static and dynamic separate.** Constant classes inline in template; conditional via `cn()` object. Don't mix ternaries into the class string.
- **Variants via `cva`/`tv`** (if used in project): they're in `tailwindFunctions`, inner classes sort too.

## Quality checklist

- [ ] Version detected: v4 → `@import 'tailwindcss'`, config in CSS, no superfluous `tailwind.config.js`
- [ ] Colors/radii/fonts as `@theme` tokens; markup uses semantic utilities, not raw `bg-white`/`text-gray-*`
- [ ] Dark mode: `@custom-variant dark (&:is(.dark *))`, values in `:root` and `.dark`, class set by `useAppearance` (not manual `classList`)
- [ ] Conditional/dynamic classes via `cn()` (twMerge+clsx), not string concat
- [ ] `.prettierrc`: `prettier-plugin-tailwindcss` last in `plugins`, `tailwindFunctions` includes `cn`/`clsx`/`cva`/`tv`, v4 sets `tailwindStylesheet`
- [ ] Spacing between elements via `gap`/`space-*` on container, not child outer `margin`; values from single spacing scale
- [ ] Repeated long class set extracted to component/`@apply`, not copied
- [ ] Classes sorted by Prettier (including inside `cn(...)`/`cva(...)`)

## References

- snippets/app.css — v4 CSS-first config: tokens, dark mode, v4↔v3 differences
- snippets/cn.ts — `cn()` utility (clsx + tailwind-merge)
- snippets/.prettierrc — Prettier with plugin and `tailwindFunctions`
- https://tailwindcss.com/docs/upgrade-guide — v3 → v4 migration guide
- https://tailwindcss.com/docs/theme — `@theme` directive and tokens
- Related skills: `frontend-tailwind/dark-mode` (three-mode `useAppearance` composable, FOUC-free boot, SSR — owner of `.dark` state), `frontend-backend/inertia-vue`, `frontend-vue/vue-composition-api`, `frontend-linting/js-code-style`, `frontend-linting/eslint-flat-config` (where the Prettier-plugin chain is declared), `frontend-reka/reka-ui-cva` (`cn()` and tokens in UI-kit components), `frontend-naive-ui/naive-ui-theming` (shared color source-of-truth via CSS vars)
