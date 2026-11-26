---
name: figma-to-vue
bucket: frontend-figma
version: 0.1.0
description: "Map Figma Dev Mode MCP design to Vue + Tailwind v4: Auto-layout → flexbox/grid, tokens.json → @theme tokens (CSS-first), Variants → class-variance-authority (cva), Variable Modes → dark theme (.dark), component reuse via Code Connect. Activate when building Vue screens/components from Figma; runs on top of figma-mcp-core."
risk: write
persona: oss-dev
tags: [figma, vue, tailwind, tailwindcss-v4, cva, design-tokens, dark-mode, auto-layout]
requires: [figma-mcp-core]
produces_for: [tailwind-conventions, reka-ui-cva, naive-ui-theming, dark-mode]
outputs: ["src/assets/theme.css"]
snippets: [theme.css, variant-component.vue, auto-layout-mapping.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Figma → Vue + Tailwind

Map Figma Dev Mode MCP design into **Vue 3 + Tailwind CSS v4**. Figma data extraction (tools, tokens, no-screenshot discipline) lives in `figma-mcp-core`; here = structure/token → Vue + Tailwind conversion.

Activate when:
- building a Vue screen/component from a Figma selection via connected MCP;
- porting `tokens.json` (from `figma-mcp-core`) into Tailwind v4 `@theme`;
- mapping Figma Variants → component variants via `cva`;
- mapping Variable Modes (light/dark) → `.dark` dark theme.

Tailwind v4, cva, dark-theme conventions live in `tailwind-conventions`, `reka-ui-cva`, `naive-ui-theming`, `dark-mode`.

## Algorithm

1. **Figma data.** Run `figma-mcp-core`: `get_metadata` (structure), `get_variable_defs` (tokens → `tokens.json`), `get_code_connect_map` (ready components).
2. **Tokens → `@theme`.** Port `tokens.json` to Tailwind v4 CSS-first `@theme` (see `snippets/theme.css`): prefixed names generate utilities (`--color-primary` → `bg-primary`). Do NOT create `tailwind.config.js` — tokens live in CSS (see `tailwind-conventions`).
3. **Structure → markup.** Map Auto-layout → flexbox/grid per `snippets/auto-layout-mapping.md`. Do not hardcode spacing — use spacing utilities from tokens.
4. **Variants → cva.** Figma Component Set (Default/Hover/Active/Disabled) → `cva` variants (see `snippets/variant-component.vue`), classes via `cn()`.
5. **Modes → dark theme.** Variable Modes light/dark → token values under `.dark` in `@theme`, `dark:*` utilities (see `dark-mode`).
6. **Verify.** One `get_screenshot` — visually compare result; fix discrepancies via tokens.

## Auto-layout → Tailwind/flexbox mapping

Full table — `snippets/auto-layout-mapping.md`. Brief: `layoutMode: HORIZONTAL/VERTICAL` → `flex flex-row/flex-col`; `itemSpacing` → `gap-*`; `padding*` → `p*`; `primaryAxisSizingMode: FILL` → `flex-1`; `AUTO` → `w-fit`; axis alignment → `justify-*` / `items-*`.

## Quality checklist

- [ ] Tokens ported to `@theme` (CSS-first), no `tailwind.config.js`.
- [ ] Spacing/colors via token utilities, no magic numbers.
- [ ] Auto-layout mapped to flex/grid per table, not by eye.
- [ ] Variants via `cva` + `cn()`, not duplicated components.
- [ ] Variable Modes light/dark mapped to `.dark`/`dark:*`.
- [ ] Existing components from `get_code_connect_map` reused.

## Links

- snippets/theme.css — Tailwind v4 `@theme` from tokens.json (+ `.dark` modes).
- snippets/variant-component.vue — component with cva variants and cn().
- snippets/auto-layout-mapping.md — Figma Auto-layout → Tailwind table.
- Related skills: `figma-mcp-core`, `tailwind-conventions`, `reka-ui-cva`, `naive-ui-theming`, `dark-mode`.
