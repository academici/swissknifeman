---
paths:
  - "**/*.spec.ts"
  - "**/*.test.ts"
  - "tests/**"
---

Тесты (глубина — скиллы `frontend:vitest`, `frontend:vitest-vue`,
`frontend:vue-testing-best-practices`):

- Прогон только `{{TEST_RUNNER_CMD}}`.
- Vitest + @vue/test-utils; тестируй поведение (рендер по props, эмиты, состояние store),
  не приватные детали.
- Сеть мокается (`vi.mock`/MSW), без реальных запросов.
- На изменённое поведение — тест; существующие проверки не ослаблять.
