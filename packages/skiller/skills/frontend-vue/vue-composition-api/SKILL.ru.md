---
name: vue-composition-api
bucket: frontend-vue
version: 0.2.0
description: "Проектные конвенции Composition API: ref-first и паттерн composables. НЕ справочник API (`<script setup>`, defineProps/Emits, reactivity) — база в `vue`; НЕ общий workflow — в `vue-best-practices`. Здесь только дельта-решения и куда дальше."
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

# Vue Composition API — конвенции проекта

Дельта-скилл: только наши решения по Composition API. Базовый синтаксис `<script setup>`,
`defineProps`/`defineEmits`, reactivity и встроенные компоненты — в скилле `vue` (API-референс);
рабочий workflow и архитектура компонентов — в `vue-best-practices`. Грузить эту тройку вместе.

## Конвенция 1: ref-first

- По умолчанию — **`ref`** для любых данных (примитивы, объекты, массивы): единообразно, доступ через `.value`.
- `reactive` — только для объекта, который не переназначается целиком (иначе теряется реактивность).

## Конвенция 2: composables

Логика, переиспользуемая между компонентами, выносится в `use*`-функции (`composables/`).
Сигнал к composable: одно и то же реактивное состояние + методы нужны в 2+ компонентах.

```javascript
// composables/useFetch.js — composable принимает ref-аргумент и сам перезапрашивает
import { ref, isRef, unref, watchEffect } from 'vue'

export function useFetch(url) {
  const data = ref(null), error = ref(null), isPending = ref(false)
  const run = async () => {
    isPending.value = true; data.value = null; error.value = null
    try {
      const res = await fetch(unref(url))
      if (!res.ok) throw new Error('Ошибка загрузки')
      data.value = await res.json()
    } catch (e) { error.value = e.message } finally { isPending.value = false }
  }
  isRef(url) ? watchEffect(run) : run()
  return { data, error, isPending }
}
```

## Связанные скиллы

- `vue` (frontend) — справочник API (база, грузить вместе); `vue-best-practices` (frontend) — workflow и архитектура.
- `frontend-vue/pinia-stores` — глобальное состояние, когда `ref` в composable уже мало.
- `frontend-backend/inertia-vue` — где живут `composables/` в слоях проекта.
- `frontend-tailwind/dark-mode` — пример боевого composable; `frontend-reka/reka-ui-cva`, `frontend-vue/vue-dynamic-icons` — компоненты на `<script setup>`.
