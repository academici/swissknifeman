---
paths:
  - "**/*.spec.ts"
  - "**/*.test.ts"
  - "tests/**"
---

Tests (depth - skills `frontend:vitest`, `frontend:vitest-vue`,
`frontend:vue-testing-best-practices`):

- Run only `{{TEST_RUNNER_CMD}}`.
- Vitest + @vue/test-utils; test behavior (render by props, emitters, status store),
  not private details.
- The network is getting wet (`vi.mock`/MSW), without actual requests.
- For changed behavior - test; existing checks should not be weakened.
