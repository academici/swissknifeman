# Technical Lead Sequencing Rules

- Define module contracts and error semantics before implementing adapters or callers.
- Sequence work into independent, reviewable slices with non-overlapping write scopes.
- Verify integration boundaries end-to-end rather than relying solely on isolated mocks.
