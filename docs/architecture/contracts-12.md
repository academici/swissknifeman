# Agent navigation and preflight

These test and development tools do not add product contracts.

| File | Contract | Owner |
|---|---|---|
| `tools/check_touched.py` | Read-only checks for committed, staged, unstaged and untracked changes | Development tooling |
| `tests/unit/tools/test_check_touched.py` | Git change selection and preflight command coverage | Development tooling regression tests |
| `tests/unit/tools/test_codebase_map.py` | Navigation map matches all 14 executable module manifests | Architecture navigation |
