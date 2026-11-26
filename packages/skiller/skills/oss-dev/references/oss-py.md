---
name: oss-py
description: Python-specifics for OSS-projects: pyproject.toml, uv/poetry, ruff, mypy, pytest, PyPI, tox/nox
type: reference
parent: oss-development
---

# Reference: OSS Python

Loaded in addition to `.ai/skills/oss-dev/oss-development.md` when the project language is Python (CLI-tools, libraries on PyPI, ML-packages).

---

### pyproject.toml minimum (PEP 621)

```toml
[project]
name = "package-name"
version = "0.1.0"
description = "One line (for PyPI listing)"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "Vendor", email = "user@example.com" }]
keywords = []
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
]
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1",
    "ruff>=0.4",
    "mypy>=1.10",
]

[project.urls]
Homepage = "https://github.com/vendor/repo"
Repository = "https://github.com/vendor/repo"
Issues = "https://github.com/vendor/repo/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Naming convention:** PyPI name - `kebab-case` or `snake_case`, Latin, globally unique on pypi.org. Imported package name (`src/<name>/`) — strictly `snake_case`.

### Package Manager / Build Backend

| Tool | When | Lockfile |
|:---|:---|:---|
| **uv** | Default for new projects (fastest, Rust-based, unifies pip + venv + lock) | `uv.lock` |
| poetry | If already on poetry or dependency group features are needed | `poetry.lock` |
| pip + pip-tools | Minimalism / CI-only scripts | `requirements.txt` (compiled) |
| hatch / pdm | Alternative modern build backends | theirs |

**Build backend** in `[build-system]`: `hatchling` (default for new), `setuptools` (legacy/compatibility), `poetry-core` (if already on poetry).

One lockfile in the repo. Commit **required**.

### src/ layout (required for libraries)

```
package_name/
├── src/
│   └── package_name/
│       ├── __init__.py
│       └── core.py
├── tests/
├── pyproject.toml
└── README.md
```

`src/` layout prevents accidental import from cwd instead of the installed package - critical for tests.

### Static Analysis & Lint

```bash
# Ruff — lint + format in one tool (replaces flake8 + isort + black)
uvx ruff check src tests
uvx ruff format src tests

# mypy — strict required for public API
uvx mypy --strict src
```

`pyproject.toml` section:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]
# E/F: pycodestyle/pyflakes, I: isort, N: naming, UP: pyupgrade, B: bugbear, SIM: simplify

[tool.mypy]
python_version = "3.10"
strict = true
warn_unreachable = true
```

### Python Version Support Matrix

```
Python 3.10 — minimum (match statements, parametrized generics in stdlib)
Python 3.11 — recommended (exception groups, faster)
Python 3.12 — latest stable (type parameter syntax)
Python 3.13 — latest

Rule: Maintain 3 active minor versions Python (Python sunset schedule — 5 years, 1 version per year).
```

### pytest structure

```
tests/
├── unit/           # Pure logic without IO
├── integration/    # With real dependencies
└── conftest.py     # General fixtures
```

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = "-ra -q --strict-markers --strict-config"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
fail_under = 80
exclude_lines = ["pragma: no cover", "raise NotImplementedError"]
```

```bash
uvx pytest --cov=src --cov-report=term-missing
```

### tox / nox for multi-version testing

`nox` (recommended - config in Python) to run tests on multiple versions Python:

```python
# noxfile.py
import nox

@nox.session(python=["3.10", "3.11", "3.12", "3.13"])
def tests(session):
    session.install(".[dev]")
    session.run("pytest", "--cov=src")
```

`tox` (legacy, INI-config) — only if already in use.

### PyPI Publishing

```bash
# 1. Build (creates wheel + sdist in dist/)
uv build  # or python -m build

# 2. Check package (metadata sanity)
uvx twine check dist/*

# 3. Upload on TestPyPI (recommended first time)
uvx twine upload --repository testpypi dist/*

# 4. Real publication on PyPI
uvx twine upload dist/*
```

**Trusted Publishing (preferred):** configure OIDC in GitHub Actions → PyPI without storage API tokens. See PyPI docs «Trusted Publishers».

### .github/workflows/ci.yml for Python

```yaml
- Python versions: ["3.10", "3.11", "3.12", "3.13"]
- OS: [ubuntu-latest] (+ macos/windows if available platform-specific code)
- uv sync --all-extras --dev
- uvx ruff check src tests
- uvx ruff format --check src tests
- uvx mypy --strict src
- uvx pytest --cov=src --cov-report=xml
- uv build  # checking that the package is being built
```

### Type stubs / py.typed

For a library with type hints — add empty marker `src/package_name/py.typed` and in `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/package_name"]

[tool.hatch.build]
include = ["src/package_name/py.typed"]
```

Without `py.typed` mypy in downstream-projects **will not see** your annotations.

---
