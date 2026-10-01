---
paths:
  - "**/tests/**"
---

When working with package tests (depth - skill `php-packages:laravel-package-testing`):

- Run only `{{TEST_RUNNER_CMD}}` (project host specifics), not bare `php`.
- Project test framework - `{{TEST_FRAMEWORK}}`: read 1-2 existing tests and mirror their style.
- Infra - Orchestra Testbench: tests inherit batch `TestCase` with `getPackageProviders()`;
  DB - in-memory sqlite (`{{TEST_DB}}`), without external environment.
- Batch test is application independent: none `use App\...` — stubs/models for
  tests live in `tests/` (Workbench/fixtures).
- Matrix sensitive areas (`version_compare`-branches, version checks `illuminate/*`) —
  cases for BOTH branches: CI-matrix PHP×Laravel will execute both, the local run will execute one.
- For changed behavior - test; existing checks should not be weakened.
- **Test fairness:** any workaround/force for the sake of green (force `config(...)`, manual
  registering a binding instead of a provider, sibling-class bypass `final`) — mark
  `[POSSIBLE-DEFECT]` in the report: there is almost always a real bug behind the workaround.
