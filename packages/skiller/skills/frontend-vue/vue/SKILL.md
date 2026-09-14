---
version: 0.1.1
name: vue
description: "Use for Vue 3 APIs: SFC macros, reactivity, watchers, and built-in components."
metadata:
  author: Anthony Fu
  version: "2026.1.31"
  source: Generated from https://github.com/vuejs/docs, scripts at https://github.com/antfu/skills
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

- **`vue-best-practices`** — архитектурные паттерны (когда composable, когда store, SSR, TypeScript): **загружать вместе с этим скиллом для любой Vue-разработки**
- **`pinia`** — управление состоянием; дополняет этот скилл для сложной доменной логики
- **`vue-router-best-practices`** — если задача затрагивает маршрутизацию

## Related Skills

- **[vue-best-practices](.agents/skills/vue-best-practices/SKILL.md)** — архитектурные паттерны: когда composable, когда store, SSR-правила, TypeScript в Vue. Загружать **всегда вместе** с `vue` для реальных задач
- **[pinia](.agents/skills/pinia/SKILL.md)** — state management
- **[vue-router-best-practices](.agents/skills/vue-router-best-practices/SKILL.md)** — маршрутизация и навигация
- **[vue-testing-best-practices](.agents/skills/vue-testing-best-practices/SKILL.md)** — тестирование Vue-компонентов
