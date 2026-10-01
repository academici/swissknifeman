---
paths:
  - "**/tests/**"
  - "**/database/factories/**"
---

When working with tests (depth - skills `php:laravel-testing`, `php:test-isolation-guard`):

- Run only `{{TEST_RUNNER_CMD}}` (project host specifics), not bare `php`.
- Project test framework - `{{TEST_FRAMEWORK}}`: read 1-2 existing tests and mirror their style (PHPUnit — classes `extends TestCase`; Pest — `it()/test()`-functions).
- Insulation: `RefreshDatabase` + test database `{{TEST_DB}}` + existing factories.
- For changed behavior - test; existing checks should not be weakened.
- **Test fairness:** any workaround/force config for green (force `config(...)`, stamping
  `timestamp` before pagination, sibling-class bypass `final`) — mark `[POSSIBLE-DEFECT]` in the report:
  behind the workaround is almost always a real bug (on chatom >60% hits).
- `ShouldQueue`-job: if the test calls `handle()` directly - check «queue-semantics (release/backoff/
  competitive workers) not covered», so that the reviewer checks it separately.
