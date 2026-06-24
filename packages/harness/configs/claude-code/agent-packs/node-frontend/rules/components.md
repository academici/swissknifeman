---
paths:
  - "**/*.vue"
  - "src/components/**"
  - "resources/js/**"
---

Компоненты Vue (глубина — скиллы `frontend:vue-best-practices`, `frontend:vue-composition-api`):

- `<script setup lang="ts">`, Composition API; props/emits типизированы, без `any`.
- Компонент тонкий: без бизнес-логики и прямых API-вызовов в шаблоне — выноси в
  composable/store.
- Не мутируй props; для `v-for` — стабильные `:key`.
- Стили — Tailwind по конвенциям проекта; доступность (фокус/aria) на интерактиве.
