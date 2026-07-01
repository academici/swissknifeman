---
name: naive-ui-theming
bucket: frontend-naive-ui
version: 0.1.0
description: "Naive UI global theme: GlobalThemeOverrides (common + Button/Card/Form/Input/Tag/Tabs…), NConfigProvider at entry point, naive dark theme (darkTheme), tokens wired to Tailwind/CSS-variables. Activate when editing config/naive-ui.ts, Naive theme, themeOverrides, NConfigProvider, primaryColor/borderRadius, dark mode under Naive UI."
risk: write
persona: oss-dev
tags: [naive-ui, vue, theming, design-tokens, dark-mode, tailwind, frontend, components, ui]
requires: [tailwind-conventions]
produces_for: []
outputs: []
snippets: [naive-theme.ts, app.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Naive UI theming

Centralize Naive UI appearance via ONE `GlobalThemeOverrides` object in the root `NConfigProvider` — single source of truth, not per-component inline styles.

Activate when:
- Editing/creating `resources/js/config/naive-ui.ts` (or other Naive theme module), `themeOverrides` / `GlobalThemeOverrides`.
- Changing `primaryColor`, `borderRadius`, `fontFamily`, component heights, state colors (success/info/warning/error) globally.
- Per-component overrides (`Button`, `Card`, `Form`, `Input`, `Tag`, `Tabs`, `Timeline`, etc.).
- Wiring/editing `NConfigProvider` at entry point (`app.ts`/`main.ts`), provider order (modal/message/dialog).
- Naive dark theme (`darkTheme`) or wiring theme to Tailwind/CSS-variables.

NOT this: Tailwind utility classes/design tokens → `frontend-tailwind/tailwind-conventions`; `resources/js/` layering → `frontend-backend/inertia-vue`. Naive UI is NOT part of Laravel Boost, no upstream needed.

## Theming model

Three levels, global→local — pick minimal sufficient:

| Level | Mechanism | When |
|:---|:---|:---|
| Global | `themeOverrides` in `NConfigProvider` | app defaults (this skill) |
| Subtree | nested `NConfigProvider` with own `themeOverrides` | isolated zone (e.g. dark sidebar) |
| Spot | `:theme-overrides` prop on a component | one-off single-component deviation |

`GlobalThemeOverrides` = `{ common, <ComponentName>: {...} }`:
- **`common`** — tokens inherited by all: `primaryColor` (+`Hover`/`Pressed`/`Suppl`), `successColor`/`infoColor`/`warningColor`/`errorColor`, `fontFamily`, `fontSizeMedium`/`Large`, `heightMedium`, `borderRadius`, `borderColor`, `textColorBase`, `bodyColor`. Cheapest way to recolor whole app.
- **Per-component** — key = PascalCase name without `N` (`Button`, `Card`, `Form`, `Input`, `Tag`, `Tabs`). Values = that component's theme variables. Variable names: see `src/<component>/styles/light.ts` in `naive-ui` package, or the "Theme Variables" table on the component doc page.

## Algorithm

1. **One theme module.** Keep theme in one file, e.g. `resources/js/config/naive-ui.ts`; export typed constant. `GlobalThemeOverrides` type is mandatory (autocompletes variable names, catches typos at build):
   ```ts
   import type { GlobalThemeOverrides } from 'naive-ui';
   export const theme: GlobalThemeOverrides = { common: { /* ... */ } };
   ```
2. **`common` first, then components.** Put brand tokens (palette, font, radius, base heights) in `common`. Add per-component blocks only when `common` insufficient — don't duplicate inherited values.
3. **No hardcoded colors in place.** All brand colors in `common`/per-component; no `style="color:#..."` in `.vue`. Repeated color = token (or CSS-variable, see 7).
4. **Mount in root `NConfigProvider`.** At entry point wrap app in `NConfigProvider` with `:theme-overrides="theme"`. Provider order outside→in: `NConfigProvider` → `NModalProvider`/`NDialogProvider` → `NMessageProvider` → `App`. Message/modal providers must be INSIDE config-provider, else their popup nodes won't get the theme.
5. **Locale next to theme.** `NConfigProvider` takes `locale`/`dateLocale` (`ruRU`, `dateRuRU` from `naive-ui`) — set them alongside `themeOverrides`, single global UI-kit config point.
6. **Dark theme — `darkTheme`.** Import `darkTheme` from `naive-ui`, pass to provider `:theme` in dark mode (`:theme="isDark ? darkTheme : null"`). `null` = built-in light. `themeOverrides` applies over both — keep colors valid for both light and dark (or put dark overrides in a separate object swapped on `isDark`).
7. **Wire to Tailwind/CSS-variables (single source of truth).** So Naive and Tailwind don't drift on colors:
   - Declare brand palette as CSS-variables on `:root` (override under `.dark`); reference them in Tailwind config (`colors.primary: 'var(--color-primary)'`).
   - In `GlobalThemeOverrides` use the same variables: `primaryColor: 'var(--color-primary)'`. Then toggling `.dark` on `<html>` switches both Tailwind classes and Naive theme at once.
   - Dark mode usually keyed off `.dark` class on `documentElement` (Tailwind convention); use the same flag to select `darkTheme` for Naive (see 6) — one switch for both layers.
8. **Units & consistency.** Sizes = strings with units (`'14px'`, `'40px'`, `'8px'`); colors = hex/rgb/`var(...)`; numeric weights (`fontWeight`) = numbers or strings per variable type. Don't mix `px` and `rem` for one size family without reason.

## Common per-component variables (cheatsheet)

| Component | Typical variables |
|:---|:---|
| `Button` | `heightMedium`, `paddingMedium`, `fontSizeMedium`, `fontWeight`, `textColorPrimary`, `textColorHoverPrimary` |
| `Card` | `paddingMedium`, `paddingSmall`, `borderRadius`, `titleFontSizeMedium`, `fontSizeMedium` |
| `Form` | `labelTextColor`, `labelFontSizeTopMedium`, `feedbackFontSizeMedium`, `feedbackHeightMedium`, `blankHeightMedium` |
| `Input` | `border`, `borderHover`, `borderFocus`, `color`, `placeholderColor`, `borderRadius` |
| `Tag` | `borderRadius`, `fontSizeMedium`, `heightMedium`, `padding`, `fontWeightStrong` |
| `Tabs` | `tabFontSizeMedium`, `tabTextColorActiveLine`, `barColor`, `tabGapMediumLine`, `panePaddingMedium` |

Exact names and size suffixes (`Small`/`Medium`/`Large`) differ per component — check the component's Theme Variables table, don't guess.

## Which snippet

| Situation | File |
|:---|:---|
| Create/extend theme object (`common` + per-component) | `snippets/naive-theme.ts` |
| Wire theme, locale, dark mode, providers at entry point | `snippets/app.ts` |

## Quality checklist

- [ ] Theme = one typed `GlobalThemeOverrides` in one module (`config/naive-ui.ts`).
- [ ] Brand tokens (palette, font, radius) in `common`; per-component only beyond necessary.
- [ ] No hardcoded colors/inline styles in `.vue` duplicating theme tokens.
- [ ] `NConfigProvider` wraps message/modal/dialog providers (they're inside it); `themeOverrides` and `locale` set there.
- [ ] Dark mode uses Naive `darkTheme`, keyed off the same `.dark` flag as Tailwind.
- [ ] If palette shared with Tailwind — single source of truth via CSS-variables (`var(--color-*)`), not two color lists.
- [ ] Sizes = strings with units; variable names verified against component's Theme Variables table.

## Links

- https://www.naiveui.com/en-US/os-theme/docs/customize-theme
- https://www.naiveui.com/en-US/os-theme/docs/theme — theme model and `darkTheme`
- Component variables: `node_modules/naive-ui/es/<component>/styles/light.ts`
- Related skills: `frontend-tailwind/tailwind-conventions` (tokens/CSS-variables, `.dark` flag), `frontend-backend/inertia-vue` (where `config/naive-ui.ts` lives), `frontend-vue/vue-composition-api`, `frontend-tailwind/dark-mode` (same `.dark` flag selects `darkTheme`), `frontend-reka/reka-ui-cva` (alternative: own UI-kit on headless primitives instead of Naive)

<!-- ru-source-sha256: 96d9609e2182fedfe32ac997873b08ca22c24e6fd9c34890008355d541c8db3d -->
