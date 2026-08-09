---
name: reka-ui-cva
bucket: frontend-reka
version: 0.1.0
description: "UI component library on Reka UI headless primitives + class-variance-authority (cva) variants. Activate when adding/editing a component in components/ui/, defining cva variants, wrapping a reka-ui primitive in your own component, building composite Root/Trigger/Content (Dialog/Dropdown/Tooltip), merging classes via cn(), or wiring to Tailwind."
risk: write
persona: oss-dev
tags: [reka-ui, cva, vue, tailwind, headless, components, variants, design-system, ui, frontend]
requires: [tailwind-conventions]
produces_for: []
outputs: []
snippets: [button-variants.ts, Button.vue, dialog-composite.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: UI components on Reka UI + cva

Each component = thin wrapper over a Reka UI headless primitive: behavior/a11y/ARIA/`data-[state]` from Reka UI, look from cva variants + Tailwind, class merge via `cn()` (clsx + tailwind-merge).

## Activate when
- adding/editing a component in `components/ui/<name>/` (Button, Badge, Dialog, Dropdown, …)
- defining a cva variant set (`variant`, `size`, …) + `VariantProps` type
- wrapping a `reka-ui` primitive in your Vue component (`Primitive`/`asChild`, prop forwarding)
- composing from `Root`/`Trigger`/`Content` parts (Dialog, Popover, Tooltip, DropdownMenu)
- merging utility + user classes via `cn()`

**Laravel Boost**: Boost = server Blade components with built-in look (Boost-UI/Flux); Reka UI = client unstyled Vue primitives, look via cva + Tailwind. **ours-only** skill: Reka UI is NOT in Laravel Boost (no `.ai/` dir), no Boost boundary, no upstream — pattern described fully.

## Inputs
- Stack: Vue 3, Tailwind; deps `reka-ui`, `class-variance-authority`, `clsx`, `tailwind-merge` in `package.json`.
- `cn()` util (usually `@/lib/utils`); create if absent (step 1).
- Existing `components/ui/` components as convention sample (data-slot, forwarding, folder structure).

## Steps

1. **`cn()` util** — single class-merge point. clsx collects conditional classes; tailwind-merge resolves Tailwind conflicts (last `px-*` wins):
   ```ts
   import { clsx, type ClassValue } from "clsx"
   import { twMerge } from "tailwind-merge"
   export function cn(...inputs: ClassValue[]) {
     return twMerge(clsx(inputs))
   }
   ```
   Route ALL component classes through `cn()` only; never concatenate strings by hand.

2. **Component structure** — folder per component `components/ui/<name>/`:
   - `index.ts` — re-export component(s) + (if variants) cva set + `VariantProps` type
   - `<Name>.vue` — primitive wrapper
   - composite: one file per part (`Dialog.vue`, `DialogTrigger.vue`, `DialogContent.vue`, …)

3. **cva variants** (`index.ts`) — `cva(base, { variants, defaultVariants })`:
   - first arg = **base**: classes common to all instances (layout, typography, `disabled:`, `focus-visible:`, `aria-invalid:`)
   - `variants` — axis maps (`variant`, `size`): key = prop value, value = Tailwind classes
   - `defaultVariants` — default per axis
   - export the set (`export const buttonVariants = cva(...)`) and the derived type `export type ButtonVariants = VariantProps<typeof buttonVariants>` — gives strictly-typed props without manual literal lists

4. **Primitive wrapper** (`<Name>.vue`) — for interactive leaf elements use `Primitive` from `reka-ui`:
   - props extend `PrimitiveProps` (gives `as`, `asChild`) + variant axes (`variant?: ButtonVariants["variant"]`) + `class?: HTMLAttributes["class"]`
   - `withDefaults(defineProps<Props>(), { as: "button" })` — default tag
   - template `:class="cn(buttonVariants({ variant, size }), props.class)"` — computed variants first, user `class` last (overrides via tailwind-merge)
   - set `data-slot="<name>"` for CSS/test addressing; pass content via `<slot />`

5. **`asChild` / polymorphism** — `Primitive` renders the `as` tag (default own); `:as-child="asChild"` merges behavior/classes into the single child instead of wrapping. Gives "a button that is actually a link": `<Button as-child><Link .../></Button>` → `<Link>` gets button styles. Same for `Trigger` parts.

6. **Prop forwarding in composites** — Reka UI parts (`DialogRoot`, `DialogContent`, …) take own props/emits; forward transparently:
   - pure forward without classes — `useForwardPropsEmits(props, emits)` (or `useForwardProps` without emits), then `v-bind="forwarded"`
   - if the part has own `class`, **exclude** it from forward: `const delegated = reactiveOmit(props, "class")`, merge separately `:class="cn('<base>', props.class)"` — else `class` reaches the primitive twice
   - portal/overlay parts: set `inheritAttrs: false`, pass `{ ...$attrs, ...forwarded }`

7. **Root/Trigger/Content composition** — composite built from parts, each wrapped separately and re-exported from `index.ts`:
   - `Root` (`Dialog.vue`) — open control, prop/emit forward, slot
   - `Trigger` — thin `DialogTrigger` wrapper, usually `asChild` for own button
   - `Content` — portal + overlay + container with cva/base classes and `data-[state=open]:` states for animation
   - structural parts (`Header`, `Footer`, `Title`, `Description`) — plain `div`/primitives with `cn('<base>', props.class)`
   - Usage: `<Dialog> <DialogTrigger as-child>...</DialogTrigger> <DialogContent>...</DialogContent> </Dialog>`

8. **Tailwind wiring** — all variants/base are Tailwind utilities; tokens (`bg-primary`, `text-foreground`, `ring-ring`) come from Tailwind theme, so theme change needs no component edits. Primitive states read via `data-[state=open]:`, `data-[side=top]:`, `aria-invalid:` — Reka UI sets these attrs itself.

9. **Re-export** — each folder's `index.ts` re-exports public API (`export { default as Button } from "./Button.vue"` + `export const buttonVariants`/`export type ...`) so imports come from `@/components/ui/<name>`, not individual files.

## Snippet routing

| Situation | File |
|:---|:---|
| Define cva variant set (`variant`/`size`) + `VariantProps` type, re-export | `snippets/button-variants.ts` |
| Wrap primitive `Primitive`/`asChild`, merge `cn()`, default tag | `snippets/Button.vue` |
| Build composite Root/Trigger/Content with forwarding + `reactiveOmit(class)` | `snippets/dialog-composite.md` |

## Quality checklist
- [ ] Component = thin Reka UI primitive wrapper; behavior/a11y not hand-built
- [ ] All classes merged via `cn()`, user `class` is the **last** arg
- [ ] cva: `base` + `variants` + `defaultVariants`; set and `VariantProps` type exported
- [ ] Variant props typed via `ButtonVariants["variant"]`, not manual string literals
- [ ] `Primitive` + `asChild`/`as` for polymorphic/interactive elements
- [ ] In composite parts with own `class`, it is excluded from forward (`reactiveOmit`) to avoid duplication
- [ ] Prop/emit forwarding via `useForwardPropsEmits`/`useForwardProps`, not manual iteration
- [ ] `data-slot` set; `index.ts` re-exports folder public API
- [ ] Colors/radii from Tailwind theme tokens, not hardcoded

## Links
- https://reka-ui.com/
- https://cva.style/docs
- https://github.com/dcastil/tailwind-merge
- Related skills: `frontend-tailwind/tailwind-conventions` (`cn()`, design tokens, `cva` in `tailwindFunctions`), `frontend-backend/inertia-vue` (where `components/ui/` lives), `frontend-linting/js-code-style`, `frontend-vue/vue-composition-api` (`<script setup>` components), `frontend-naive-ui/naive-ui-theming` (alternative: ready Naive UI kit instead of own on primitives)
