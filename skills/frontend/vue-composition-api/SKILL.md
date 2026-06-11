---
name: vue-composition-api
bucket: frontend
version: 0.1.0
description: "Vue Composition API паттерны: синтаксис <script setup> как стандарт написания компонентов"
risk: write
persona: oss-dev
tags: [vue, frontend]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Vue Composition API Паттерны

Composition API (особенно синтаксис `<script setup>`) — это стандарт написания Vue компонентов. Options API (`data`, `methods`, `computed` внутри объекта экспорта) считается устаревшим.

## Базовый Синтаксис (`<script setup>`)

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'

// 1. Состояние (State)
const count = ref(0)
const user = ref({ name: 'John', age: 30 })

// 2. Вычисляемые свойства (Computed)
const doubleCount = computed(() => count.value * 2)

// 3. Методы
const increment = () => {
  count.value++
}

// 4. Хуки Жизненного Цикла
onMounted(() => {
  console.log('Component mounted')
})
</script>

<template>
  <button @click="increment">Счет: {{ count }} (Двойной: {{ doubleCount }})</button>
</template>
```

## `ref` против `reactive`

-   **Всегда используйте `ref`** по умолчанию для любых типов данных (примитивов, объектов, массивов). Это более универсальный подход. Обращение к значению в скрипте всегда через `.value`.
-   Используйте `reactive` только когда вам нужен объект, который не будет переназначаться целиком (иначе реактивность сломается).

## Composables (Хуки)

Composables — это функции, которые инкапсулируют логику с использованием Composition API для её переиспользования в разных компонентах. Обычно начинаются с префикса `use`.

### Пример: `useFetch.js`

```javascript
// src/composables/useFetch.js
import { ref, isRef, unref, watchEffect } from 'vue'

export function useFetch(url) {
  const data = ref(null)
  const error = ref(null)
  const isPending = ref(false)

  const fetchData = async () => {
    isPending.value = true
    data.value = null
    error.value = null

    try {
      // unref достает значение, если url - это ref, или возвращает как есть
      const response = await fetch(unref(url)) 
      if (!response.ok) throw new Error('Ошибка загрузки')
      data.value = await response.json()
    } catch (err) {
      error.value = err.message
    } finally {
      isPending.value = false
    }
  }

  // Если url - это ref, мы хотим перезапрашивать данные при его изменении
  if (isRef(url)) {
    watchEffect(fetchData)
  } else {
    fetchData()
  }

  return { data, error, isPending }
}
```

### Использование в компоненте:

```vue
<script setup>
import { ref } from 'vue'
import { useFetch } from '@/composables/useFetch'

const userId = ref(1)
// Передаем ref, запрос будет автоматически повторяться при изменении userId
const { data: user, isPending, error } = useFetch(() => `https://api.example.com/users/${userId.value}`)
</script>
```

## Пропсы и Эмиты (Props & Emits)

Для объявления пропсов и эмитов используются макросы компилятора `defineProps` и `defineEmits`.

```vue
<script setup>
const props = defineProps({
  title: {
    type: String,
    required: true
  },
  items: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update', 'delete'])

const handleDelete = (id) => {
  emit('delete', id)
}
</script>
```
