---
name: vue-dynamic-icons
bucket: frontend-vue
version: 0.1.0
description: "Vue: one icon component rendering SVG by string name from a set (lucide-vue-next etc.) via <component :is>; activate on dynamic icon, icon by name, component is icon, passing size/strokeWidth/color, type-safe icon name, swapping icon set."
risk: write
persona: oss-dev
tags: [vue, icons, dynamic-component, lucide, typescript, frontend]
requires: []
produces_for: []
outputs: []
snippets: [Icon.vue, icon-name.type.ts]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skill: Vue dynamic icon component

One reusable `<Icon name="...">` rendering an SVG by string name from a set (`lucide-vue-next`, `@heroicons/vue`, own registry), forwarding `size` / `strokeWidth` / `color` / `class`, no per-icon manual import per page.

## Activate when
- Template needs icon "by name from data/config" (`type`, `status`, `category` arrive as string from backend).
- Scattered `import { Plus, Trash, ... } from 'lucide-vue-next'` across many components — centralize.
- "dynamic icon", "icon by name", "`<component :is>` for icon", "type-safe icon name", "how to swap icon set".

Pattern is set-agnostic: a set = any module exporting Vue icon components by name. Swap set = change one `import * as icons` and (optionally) the union-type source.

## Algorithm
1. Create single component `components/shared/Icon.vue` (`<script setup lang="ts">`). All other places use only it, never import icons directly.
2. Import set as namespace: `import * as icons from '<icon-set>'` → dict `{ IconName: Component }`. Only binding point to the set.
3. Props via `defineProps<Props>` + `withDefaults`:
   - `name: IconName` — icon name (type-safe union, see step 6; `string` allowed at start);
   - `size?: number | string` (default e.g. `16`), `strokeWidth?: number | string` (default `2`), `color?: string`, `class?: string`.
4. Normalize name to the set's convention. `lucide-vue-next` exports PascalCase (`ArrowRight`); data is often kebab/lower (`arrow-right`, `plus`). Cast case in `computed`, not in template. Snippet shows the simplest case (lower → first-letter Pascal); for kebab-case convert each segment.
5. Resolve component lazily via `computed` — recomputes only on `name` change:
   ```ts
   const icon = computed(() => (icons as Record<string, Component>)[normalize(props.name)]);
   ```
   No `if/switch` over names — the set dict is the map.
6. Make name type-safe. Derive union from the set (`keyof typeof icons`) or declare explicit `IconName` for the used subset (see `snippets/icon-name.type.ts`). Gives autocomplete and catches typos at build time, not runtime.
7. Handle miss. If `icons[name]` not found, `<component :is>` with `undefined` renders nothing. Optionally: return fallback icon (`HelpCircle`/`Square`) or `console.warn` in dev. Type-safe `name` (step 6) removes most misses upfront.
8. Forward props into `<component :is="icon">`: `:size`, `:stroke-width`, `:color`, `:class`. Merge `class` with base classes (`cn(...)` / `clsx` / manual concat) so caller can extend, not overwrite, style.
9. Use uniformly everywhere: `<Icon :name="row.icon" :size="20" class="text-muted" />`. Name may come from props/store/API response.

## Swapping the icon set
Switch sets by editing **only Icon.vue**; the `<Icon name size ...>` contract stays:

| Step | Change |
|:---|:---|
| Set import | `import * as icons from '@heroicons/vue/24/outline'` instead of `lucide-vue-next` |
| Name normalization | to the new set's convention (suffix `Icon`, kebab→Pascal, etc.) |
| Name union type | `IconName = keyof typeof icons` recomputes itself, or update the explicit list |
| Forwarded props | sets have different APIs (lucide — `strokeWidth`; heroicons — none): forward what the set supports |

## Quality checklist
- [ ] Icons imported manually nowhere except the single `Icon.vue` (`import * as icons`)
- [ ] Component selection is lazy `computed` by `name`, no `if/switch` chains
- [ ] Name cast to set convention in `computed`/function, not in template
- [ ] `name` is type-safe (`IconName` from `keyof typeof icons` or explicit union), not bare `string`
- [ ] `size`, `strokeWidth`, `color` forwarded with defaults via `withDefaults`
- [ ] `class` merged with base classes, caller can extend style
- [ ] Miss strategy exists (fallback icon or dev-warn)
- [ ] Set swap touches only `Icon.vue`, `<Icon>` contract unchanged

## Links
- https://vuejs.org/guide/essentials/component-basics#dynamic-components
- https://lucide.dev/guide/packages/lucide-vue-next
- `snippets/Icon.vue`, `snippets/icon-name.type.ts`
- Related skills: `frontend/inertia-vue` (where `components/shared/Icon.vue` lives), `frontend/vue-composition-api` (`<script setup>`, `computed`), `frontend/tailwind-conventions` (`cn()` for merging icon classes), `frontend/reka-ui-cva` (icons inside UI-kit components)

<!-- ru-source-sha256: PENDING -->

<!-- ru-source-sha256: 45b1af001da556716221728506dab2c2af8a2676cc4afeb65a268c024db83208 -->
