> 🌐 Перевод для человека. Агент использует SKILL.md, не этот файл.

---
name: pinia
description: Pinia official Vue state management library, type-safe and extensible. Use when defining stores, working with state/getters/actions, or implementing store patterns in Vue apps.
metadata:
  author: Anthony Fu
  version: "2026.1.28"
  source: Generated from https://github.com/vuejs/pinia, scripts located at https://github.com/antfu/skills
---

# Pinia

Pinia — официальная библиотека управления состоянием для Vue, спроектированная так, чтобы быть интуитивной и типобезопасной. Она поддерживает оба стиля — Options API и Composition API, с первоклассной поддержкой TypeScript и интеграцией с devtools.

> Скилл основан на Pinia v3.0.4, сгенерирован 2026-01-28.

## Базовые справочники (Core References)

| Тема | Описание | Справочник |
|-------|-------------|-----------|
| Stores (хранилища) | Определение хранилищ, state, getters, actions, storeToRefs, подписки | [core-stores](references/core-stores.md) |

## Возможности (Features)

### Расширяемость (Extensibility)

| Тема | Описание | Справочник |
|-------|-------------|-----------|
| Plugins (плагины) | Расширение хранилищ кастомными свойствами, состоянием и поведением | [features-plugins](references/features-plugins.md) |

### Композируемость (Composability)

| Тема | Описание | Справочник |
|-------|-------------|-----------|
| Composables | Использование Vue composables внутри хранилищ (VueUse и т. п.) | [features-composables](references/features-composables.md) |
| Composing Stores (композиция хранилищ) | Взаимодействие хранилище-к-хранилищу, избегание циклических зависимостей | [features-composing-stores](references/features-composing-stores.md) |

## Лучшие практики (Best Practices)

| Тема | Описание | Справочник |
|-------|-------------|-----------|
| Testing (тестирование) | Unit-тестирование с @pinia/testing, mocking, stubbing | [best-practices-testing](references/best-practices-testing.md) |
| Outside Components (вне компонентов) | Использование хранилищ в navigation guards, плагинах, middlewares | [best-practices-outside-component](references/best-practices-outside-component.md) |

## Продвинутое (Advanced)

| Тема | Описание | Справочник |
|-------|-------------|-----------|
| SSR | Server-side rendering (серверный рендеринг), гидратация состояния | [advanced-ssr](references/advanced-ssr.md) |
| Nuxt | Интеграция с Nuxt, авто-импорты, лучшие практики SSR | [advanced-nuxt](references/advanced-nuxt.md) |
| HMR | Hot module replacement (горячая замена модулей) для разработки | [advanced-hmr](references/advanced-hmr.md) |

## Ключевые рекомендации

- **Предпочитайте Setup Stores** для сложной логики, composables и watchers
- **Используйте `storeToRefs()`** при деструктуризации state/getters, чтобы сохранить реактивность
- **Actions можно деструктурировать напрямую** — они привязаны к хранилищу
- **Вызывайте хранилища внутри функций**, а не на уровне модуля, особенно для SSR
- **Добавляйте поддержку HMR** в каждое хранилище для более удобной разработки
- **Используйте `@pinia/testing`** для тестов компонентов с замоканными хранилищами
