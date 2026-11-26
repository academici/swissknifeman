---
name: vue-composition-api
bucket: frontend-vue
version: 0.2.1
description: "Use for project ref-first/composable conventions; Vue API syntax belongs to the vue skill."
risk: write
persona: oss-dev
tags: [vue, frontend, composable, patterns]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Vue Composition API — project conventions

Delta skill. Base syntax (`<script setup>`, `defineProps`/`defineEmits`, reactivity, built-ins) → `vue`. Workflow + component architecture → `vue-best-practices`. Load all three together.

## Convention 1: ref-first
- Default to **`ref`** for any data (primitives, objects, arrays); access via `.value`.
- `reactive` — only for an object never reassigned wholesale (else reactivity is lost).

## Convention 2: composables
- Reuse logic across components in `use*` functions (`composables/`).
- Signal: same reactive state + methods needed in 2+ components.

```javascript
// composables/useFetch.js — composable takes a ref arg and refetches itself
import { ref, isRef, unref, watchEffect } from 'vue'

export function useFetch(url) {
  const data = ref(null), error = ref(null), isPending = ref(false)
  const run = async () => {
    isPending.value = true; data.value = null; error.value = null
    try {
      const res = await fetch(unref(url))
      if (!res.ok) throw new Error('Loading error')
      data.value = await res.json()
    } catch (e) { error.value = e.message } finally { isPending.value = false }
  }
  isRef(url) ? watchEffect(run) : run()
  return { data, error, isPending }
}
```

## Related skills
- `vue` (frontend) — API reference (base, load together); `vue-best-practices` (frontend) — workflow + architecture.
- `frontend-vue/pinia-stores` — global state when composable `ref` is no longer enough.
- `frontend-backend/inertia-vue` — where `composables/` live in project layers.
- `frontend-tailwind/dark-mode` — real composable example; `frontend-reka/reka-ui-cva`, `frontend-vue/vue-dynamic-icons` — `<script setup>` components.
