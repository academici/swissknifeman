---
paths:
  - "test/**"
  - "**/*_test.dart"
---

Tests Flutter (depth - skill `quality:test-strategy`):

- Run only `{{TEST_RUNNER_CMD}}`.
- widget + unit; golden — for UI-heavy screens; test behavior, not private details.
- Isolation: mock repositories/services, without real peripherals/network.
- For changed behavior - test; existing checks should not be weakened.
