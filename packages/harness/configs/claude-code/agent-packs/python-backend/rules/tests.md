---
paths:
  - "tests/**"
  - "**/test_*.py"
  - "**/*_test.py"
---

Tests (depth - skill `quality:test-strategy`):

- Run only `{{TEST_RUNNER_CMD}}` (venv-aware, `{{PY_BIN}}`).
- pytest; for {{WEB_FRAMEWORK}} — TestClient/httpx or django test client; test
  endpoint behavior (codes/validation/errors/side effects in the database).
- Fittings/`tmp_path`, isolated DB; mock external services; without a real network.
- For changed behavior - test; existing checks should not be weakened.
