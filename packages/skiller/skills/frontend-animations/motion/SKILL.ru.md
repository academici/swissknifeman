> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: motion
description: Use when adding animations with Motion Vue (motion-v) - provides motion component API, gesture animations, scroll-linked effects, layout transitions, and composables for Vue 3/Nuxt
license: MIT
---

# Motion Vue (motion-v)

Библиотека анимаций для Vue 3 и Nuxt. Готовые к продакшену, аппаратно-ускоренные анимации с минимальным размером бандла.

**Текущая стабильная версия:** motion-v 1.x — Vue-порт Motion (ранее Framer Motion)

## Обзор

Прогрессивный справочник по анимациям Motion Vue. Загружай только те файлы, что относятся к текущей задаче (~200 токенов базово, 500–1500 на под-файл).

## Когда использовать

**Используй Motion Vue для:**

- Простых декларативных анимаций (fade, slide, scale)
- Жестовых взаимодействий (hover, tap, drag)
- Анимаций, привязанных к скроллу
- Анимаций раскладки (layout) и переходов общих элементов (shared element transitions)
- Анимаций на пружинной физике (spring)

**Рассмотри альтернативы:**

- **GSAP** — сложные таймлайны, морфинг SVG, последовательности, запускаемые скроллом
- **@vueuse/motion** — более простой API, меньше возможностей, меньший бандл
- **CSS-анимации** — простые переходы без JS

## Установка

```bash
# Vue 3
pnpm add motion-v

# Nuxt 3
pnpm add motion-v @vueuse/nuxt
```

```ts
// nuxt.config.ts - Nuxt 3 setup
export default defineNuxtConfig({
  modules: ['motion-v/nuxt'],
})
```

## Быстрый справочник

| Работаешь над...             | Загрузи файл              |
| ---------------------------- | ------------------------- |
| Motion component, gestures   | references/components.md  |
| useMotionValue, useScroll    | references/composables.md |
| Animation examples, patterns | references/examples.md    |

## Загрузка файлов

**Рассмотри загрузку этих справочных файлов в зависимости от задачи:**

- [ ] [references/components.md](references/components.md) — если используешь Motion component, жесты (gestures) или анимации раскладки (layout)
- [ ] [references/composables.md](references/composables.md) — если используешь useMotionValue, useScroll, useSpring или animate()
- [ ] [references/examples.md](references/examples.md) — если ищешь паттерны анимаций или вдохновение

**НЕ загружай все файлы сразу.** Загружай только то, что относится к твоей текущей задаче.

## Ключевые концепции

### Motion Component

Рендерит любой HTML/SVG-элемент с возможностями анимации:

```vue
<script setup lang="ts">
import { motion } from 'motion-v'
</script>

<template>
  <motion.div
    :initial="{ opacity: 0, y: 20 }"
    :animate="{ opacity: 1, y: 0 }"
    :exit="{ opacity: 0, y: -20 }"
    :transition="{ duration: 0.3 }"
  >
    Animated content
  </motion.div>
</template>
```

### Жестовые анимации (Gesture Animations)

```vue
<motion.button
  :whileHover="{ scale: 1.05 }"
  :whilePress="{ scale: 0.95 }"
  :transition="{ type: 'spring', stiffness: 400 }"
>
  Click me
</motion.button>
```

### Анимации при скролле (Scroll Animations)

```vue
<motion.div
  :initial="{ opacity: 0 }"
  :whileInView="{ opacity: 1 }"
  :viewport="{ once: true, margin: '-100px' }"
>
  Appears on scroll
</motion.div>
```

## Доступные руководства

**[references/components.md](references/components.md)** — варианты Motion component, props анимаций, props жестов, анимации раскладки (layout), конфигурация переходов (transition)

**[references/composables.md](references/composables.md)** — useMotionValue, useSpring, useTransform, useScroll, useInView, animate()

**[references/examples.md](references/examples.md)** — внешние ресурсы, библиотеки компонентов, паттерны анимаций и вдохновение
