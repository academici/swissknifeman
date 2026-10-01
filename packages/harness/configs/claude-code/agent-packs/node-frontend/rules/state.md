---
paths:
  - "**/stores/**"
  - "**/*.store.ts"
  - "src/composables/**"
---

Status (depth - skill `frontend:pinia`):

- General condition - Pinia store; local - `ref`/`reactive` in the component/composable.
- Don't throw state through globals; Don't duplicate the source of truth between sites.
- Actions store typed; side effects (API) in actions, not in getters.
- Network calls - via typed API-client/composable, not from the template.
