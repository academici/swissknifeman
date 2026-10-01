---
paths:
  - "**/*.vue"
  - "src/components/**"
  - "resources/js/**"
---

Components Vue (depth - skills `frontend:vue-best-practices`, `frontend:vue-composition-api`):

- `<script setup lang="ts">`, Composition API; props/emits typed, without `any`.
- The component is thin: without business logic and direct API-calls in the template - place them in
  composable/store.
- Don't mutate props; for `v-for` — stable `:key`.
- Styles - Tailwind according to project conventions; availability (focus/aria) on the interactive.
