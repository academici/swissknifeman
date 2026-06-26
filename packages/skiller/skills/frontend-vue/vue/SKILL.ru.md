> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: vue
description: Vue 3 Composition API, script setup macros, reactivity system, and built-in components. Use when writing Vue SFCs, defineProps/defineEmits/defineModel, watchers, or using Transition/Teleport/Suspense/KeepAlive.
metadata:
  author: Anthony Fu
  version: "2026.1.31"
  source: Generated from https://github.com/vuejs/docs, scripts at https://github.com/antfu/skills
---

# Vue

> На основе Vue 3.5. Всегда используйте Composition API с `<script setup lang="ts">`.

## Предпочтения

- Предпочитайте TypeScript, а не JavaScript
- Предпочитайте `<script setup lang="ts">`, а не `<script>`
- Ради производительности предпочитайте `shallowRef` вместо `ref`, если глубокая реактивность не нужна
- Всегда используйте Composition API, а не Options API
- Не поощряйте использование Reactive Props Destructure (деструктуризации реактивных пропсов)

## Ядро

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Script Setup и макросы | `<script setup>`, defineProps, defineEmits, defineModel, defineExpose, defineOptions, defineSlots, дженерики | [script-setup-macros](references/script-setup-macros.md) |
| Реактивность и жизненный цикл | ref, shallowRef, computed, watch, watchEffect, effectScope, хуки жизненного цикла, composables | [core-new-apis](references/core-new-apis.md) |

## Возможности

| Тема | Описание | Справка |
|-------|-------------|-----------|
| Встроенные компоненты и директивы | Transition, Teleport, Suspense, KeepAlive, v-memo, кастомные директивы | [advanced-patterns](references/advanced-patterns.md) |

## Краткая справка

### Шаблон компонента

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

### Ключевые импорты

```ts
// Реактивность
import { ref, shallowRef, computed, reactive, readonly, toRef, toRefs, toValue } from 'vue'

// Наблюдатели (watchers)
import { watch, watchEffect, watchPostEffect, onWatcherCleanup } from 'vue'

// Жизненный цикл
import { onMounted, onUpdated, onUnmounted, onBeforeMount, onBeforeUpdate, onBeforeUnmount } from 'vue'

// Утилиты
import { nextTick, defineComponent, defineAsyncComponent } from 'vue'
```

## Связанные скиллы

- **`vue-best-practices`** — архитектурные паттерны (когда composable, когда store, SSR, TypeScript): **загружать вместе с этим скиллом для любой Vue-разработки**
- **`pinia`** — управление состоянием; дополняет этот скилл для сложной доменной логики
- **`vue-router-best-practices`** — если задача затрагивает маршрутизацию

## Связанные скиллы

- **[vue-best-practices](.agents/skills/vue-best-practices/SKILL.md)** — архитектурные паттерны: когда composable, когда store, SSR-правила, TypeScript в Vue. Загружать **всегда вместе** с `vue` для реальных задач
- **[pinia](.agents/skills/pinia/SKILL.md)** — state management
- **[vue-router-best-practices](.agents/skills/vue-router-best-practices/SKILL.md)** — маршрутизация и навигация
- **[vue-testing-best-practices](.agents/skills/vue-testing-best-practices/SKILL.md)** — тестирование Vue-компонентов
