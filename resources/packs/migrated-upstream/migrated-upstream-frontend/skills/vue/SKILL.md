---
name: vue
description: "Use for Vue 3 APIs: SFC macros, reactivity, watchers, and built-in components."
---

# Vue

> Based on Vue 3.5. Always use Composition API with `<script setup lang="ts">`.

## Preferences

- Prefer TypeScript over JavaScript
- Prefer `<script setup lang="ts">` over `<script>`
- For performance, prefer `shallowRef` over `ref` if deep reactivity is not needed
- Always use Composition API over Options API
- Discourage using Reactive Props Destructure

## Core

| Topic | Description | Reference |
|-------|-------------|-----------|
| Script Setup & Macros | `<script setup>`, defineProps, defineEmits, defineModel, defineExpose, defineOptions, defineSlots, generics | [script-setup-macros](references/script-setup-macros.md) |
| Reactivity & Lifecycle | ref, shallowRef, computed, watch, watchEffect, effectScope, lifecycle hooks, composables | [core-new-apis](references/core-new-apis.md) |

## Features

| Topic | Description | Reference |
|-------|-------------|-----------|
| Built-in Components & Directives | Transition, Teleport, Suspense, KeepAlive, v-memo, custom directives | [advanced-patterns](references/advanced-patterns.md) |

## Quick Reference

### Component Template

```vue
<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'

const props = defineProps<{
  title: string
  count?: number
}>()

const emit = defineEmits<{
  update: [value: string]
}>()

const model = defineModel<string>()

const doubled = computed(() => (props.count ?? 0) * 2)

watch(() => props.title, (newVal) => {
  console.log('Title changed:', newVal)
})

onMounted(() => {
  console.log('Component mounted')
})
</script>

<template>
  <div>{{ title }} - {{ doubled }}</div>
</template>
```

### Key Imports

```ts
// Reactivity
import { ref, shallowRef, computed, reactive, readonly, toRef, toRefs, toValue } from 'vue'

// Watchers
import { watch, watchEffect, watchPostEffect, onWatcherCleanup } from 'vue'

// Lifecycle
import { onMounted, onUpdated, onUnmounted, onBeforeMount, onBeforeUpdate, onBeforeUnmount } from 'vue'

// Utilities
import { nextTick, defineComponent, defineAsyncComponent } from 'vue'
```

## Related Skills

- **`vue-best-practices`** — architectural patterns (when composable, when store, SSR, TypeScript): **load along with this skill for any Vue-development**
- **`pinia`** — state management; complements this skill for complex domain logic
- **`vue-router-best-practices`** — if the task affects routing

## Related Skills

- **[vue-best-practices](.agents/skills/vue-best-practices/SKILL.md)** — architectural patterns: when composable, when store, SSR-rules, TypeScript in Vue. Load **always together** with `vue` for real-life problems
- **[pinia](.agents/skills/pinia/SKILL.md)** — state management
- **[vue-router-best-practices](.agents/skills/vue-router-best-practices/SKILL.md)** — routing and navigation
- **[vue-testing-best-practices](.agents/skills/vue-testing-best-practices/SKILL.md)** — testing Vue-components
