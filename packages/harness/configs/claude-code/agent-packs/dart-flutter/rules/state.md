---
paths:
  - "lib/**"
---

Status ({{STATE_MGMT}}):

- General status - through {{STATE_MGMT}}; naked setState — just for the trivial
  local UI.
- The source of truth is one; do not duplicate state between providers/blocks.
- Side effects (repositories/network/peripherals) — out `build()`; for pos-embedded don't block
  main isolate.
