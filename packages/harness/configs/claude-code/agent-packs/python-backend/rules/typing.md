---
paths:
  - "**/*.py"
---

Typing:

- Public functions/methods are annotated (arguments + return); without untyped transfer
  `dict`.
- `# type: ignore` — only with the reason in the comment.
- Not «leak» `Any` across module boundaries; prefer exact types/Protocol.
- Deep analysis of type errors - subagent `type-checker`.
